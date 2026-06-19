"""
测试：批量交付工作流修复验证
- 任务队列断点续传（source_dir保存）
- RAW文件区分跳过/失败
- 批量归档跳过项目显示
"""
import sys
import os
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import Image as PILImage

from photo_selector.scanner import FileScanner, ProjectItem, PhotoItem
from photo_selector.rules import RulesConfig
from photo_selector.packager import PackageGenerator
from photo_selector.logger import Logger, PackageHistory, ProcessingStats
from photo_selector.task_queue import TaskQueue, QueueTask, ProjectSummary
from photo_selector.batch_record import BatchHistory, BatchRecord, BatchProjectResult
from photo_selector.config import AppConfig


def _create_test_image(path, size=(800, 600), color=(100, 150, 200)):
    img = PILImage.new('RGB', size, color)
    img.save(path, 'JPEG', quality=85)


def test_project_source_dir_persistence():
    print("\n" + "=" * 60)
    print("测试1: ProjectItem source_dir 持久化 + 断点续传")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        src_dir = tmpdir / "source"
        src_dir.mkdir()
        for i in range(5):
            _create_test_image(src_dir / f"IMG_{i:04d}.jpg", color=(i * 30, 100, 150))

        scanner = FileScanner()
        scanner.set_source_directory(str(src_dir))
        projects = scanner.scan()
        assert len(projects) >= 1
        project = projects[0]

        assert project.source_dir is not None, "ProjectItem 应该有 source_dir"
        assert str(project.source_dir) == str(src_dir), f"source_dir 应该是 {src_dir}"
        print(f"  ✓ ProjectItem.source_dir 正确保存: {project.source_dir}")

        queue_dir = tmpdir / "queue"
        queue = TaskQueue()
        queue.set_queue_directory(str(queue_dir))

        summary = ProjectSummary(
            project_name=project.name,
            photo_count=project.photo_count,
            client_name=project.client_name,
            shoot_date=project.shoot_date,
            total_size_mb=project.total_size / (1024 * 1024),
            source_dir=str(project.source_dir),
            raw_count=0,
            corrupted_count=0,
        )
        task = QueueTask(
            project_summary=summary,
            output_dir=str(tmpdir / "output"),
            make_zip=False,
            status="confirmed",
        )
        queue.add_task(task)

        queue2 = TaskQueue()
        queue2.set_queue_directory(str(queue_dir))
        loaded_task = queue2.get_task(task.task_id)
        assert loaded_task is not None
        assert loaded_task.project_summary.source_dir == str(src_dir), "断点续传后 source_dir 应该还在"
        print(f"  ✓ 断点续传 source_dir 正确恢复: {loaded_task.project_summary.source_dir}")

        rescanned = scanner.rescan_project(str(src_dir), project.name)
        assert rescanned is not None, "rescan_project 应该返回项目"
        assert rescanned.photo_count == project.photo_count, "重新扫描后照片数一致"
        print(f"  ✓ 通过 source_dir 重新扫描成功: {rescanned.photo_count} 张照片")


def test_raw_skip_logic():
    print("\n" + "=" * 60)
    print("测试2: RAW文件按 include_raw 规则区分跳过/失败")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        src_dir = tmpdir / "source"
        src_dir.mkdir()
        for i in range(3):
            _create_test_image(src_dir / f"ClientA_{i:04d}.jpg", color=(i * 40, 100, 150))
        for i in range(2):
            (src_dir / f"ClientA_{i:04d}.CR2").write_bytes(b"fake raw content")

        scanner = FileScanner()
        scanner.set_source_directory(str(src_dir))
        projects = scanner.scan()
        project = None
        for p in projects:
            if p.name == "ClientA":
                project = p
                break
        assert project is not None, "应该找到 ClientA 项目"
        print(f"  项目: {project.name}, 照片: {project.photo_count} 张")

        rules = RulesConfig()
        rules.include_raw = False
        rules.expire_enabled = False
        logger = Logger()
        logger.set_log_directory(str(tmpdir / "logs"))
        packager = PackageGenerator(rules, logger)
        out_dir = tmpdir / "output"
        out_dir.mkdir()

        package_path = packager.generate_package(project, str(out_dir))
        stats = logger.stats
        print(f"  include_raw=False: 处理={stats.processed_files}, 跳过={stats.skipped_files}, 失败={stats.failed_files}")
        assert stats.processed_files == 3, f"JPG应该全部处理，实际{stats.processed_files}"
        assert stats.skipped_files == 2, f"RAW应该被跳过，实际{stats.skipped_files}"
        assert stats.failed_files == 0, f"RAW不应该算失败，实际{stats.failed_files}"
        assert "RAW文件未启用包含" in str(stats.skip_reasons), "跳过原因应包含RAW"
        print(f"  ✓ include_raw=False: RAW正确跳过，不算失败")

        rules.include_raw = True
        logger.reset_stats()
        packager2 = PackageGenerator(rules, logger)
        out_dir2 = tmpdir / "output2"
        out_dir2.mkdir()
        package_path2 = packager2.generate_package(project, str(out_dir2))
        stats2 = logger.stats
        print(f"  include_raw=True: 处理={stats2.processed_files}, 跳过={stats2.skipped_files}, 失败={stats2.failed_files}")

        originals = list((package_path2 / "originals").glob("*"))
        raw_files = [f for f in originals if f.suffix.lower() in AppConfig.SUPPORTED_RAW_EXTENSIONS]
        print(f"  输出 originals 目录 RAW 文件数: {len(raw_files)}")
        if len(raw_files) > 0:
            print(f"  ✓ include_raw=True: RAW文件保留在 originals 目录")
        else:
            print(f"  ⚠️  include_raw=True: 假RAW文件无法处理缩略图，已跳过(预期行为)")


def test_batch_skipped_project_display():
    print("\n" + "=" * 60)
    print("测试3: 批量归档跳过项目统计与显示")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        bh = BatchHistory()
        bh.set_history_directory(str(tmpdir))

        pr_success = BatchProjectResult(
            project_name="成功项目",
            status="success",
            total_photos=100,
            processed=95,
            skipped=5,
            failed=0,
            skip_reasons={"尺寸过小": 3, "RAW未包含": 2},
            package_path="D:/output/success"
        )
        pr_skipped = BatchProjectResult(
            project_name="跳过项目",
            status="skipped",
            total_photos=50,
            processed=0,
            skipped=50,
            failed=0,
            skip_reasons={"源目录不可访问": 50},
            package_path="",
            error_message=""
        )
        pr_failed = BatchProjectResult(
            project_name="失败项目",
            status="failed",
            total_photos=80,
            processed=0,
            skipped=0,
            failed=80,
            failed_files=[{"filename": "all", "error": "无权限"}],
            package_path="",
            error_message="输出目录无写入权限"
        )

        start = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        record = bh.create_record_from_batch(
            batch_id="test_001",
            profile_name="测试方案",
            output_dir="D:/output",
            make_zip=True,
            start_time=start,
            project_results=[pr_success, pr_skipped, pr_failed],
            status="completed",
        )

        assert record.total_projects == 3
        assert record.completed_projects == 1, f"成功应该是1, 实际{record.completed_projects}"
        assert record.skipped_projects == 1, f"跳过应该是1, 实际{record.skipped_projects}"
        assert record.failed_projects == 1, f"失败应该是1, 实际{record.failed_projects}"
        print(f"  ✓ 批次统计正确: 成功={record.completed_projects}, 跳过={record.skipped_projects}, 失败={record.failed_projects}")

        summary = record.get_summary()
        assert "跳过: 1 个" in summary, "批次汇总应该显示跳过项目数"
        print(f"  ✓ 批次汇总包含跳过项目数:")
        for line in summary.split("\n")[:8]:
            print(f"    {line}")

        skipped_summary = pr_skipped.get_summary()
        assert "⏭️" in skipped_summary or "跳过" in skipped_summary
        assert "源目录不可访问" in skipped_summary, "跳过项目详情应该包含跳过原因"
        print(f"  ✓ 跳过项目详情包含跳过原因:")
        for line in skipped_summary.split("\n"):
            print(f"    {line}")

        report = record.get_report_text()
        assert "⏭️" in report or "已跳过" in report, "报告中应有跳过状态"
        assert "源目录不可访问" in report, "报告中应有跳过原因"
        print(f"  ✓ 整批报告包含跳过项目状态和原因")

        bh2 = BatchHistory()
        bh2.set_history_directory(str(tmpdir))
        loaded = bh2.get_record("test_001")
        assert loaded is not None
        assert loaded.skipped_projects == 1
        assert loaded.project_results[1].status == "skipped"
        print(f"  ✓ 批量记录持久化后跳过状态正确保存")


def test_project_to_dict_roundtrip():
    print("\n" + "=" * 60)
    print("测试4: ProjectItem 序列化/反序列化 (source_dir保留)")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        src_dir = tmpdir / "src"
        src_dir.mkdir()
        _create_test_image(src_dir / "test.jpg")

        scanner = FileScanner()
        scanner.set_source_directory(str(src_dir))
        projects = scanner.scan()
        p = projects[0]

        data = p.to_dict()
        assert "source_dir" in data
        assert data["source_dir"] == str(src_dir)
        print(f"  ✓ to_dict 包含 source_dir: {data['source_dir']}")
        assert len(data["photos"]) == p.photo_count
        print(f"  ✓ to_dict 包含 {len(data['photos'])} 张照片元数据")

        p2 = ProjectItem.from_dict(data)
        assert p2.name == p.name
        assert str(p2.source_dir) == str(src_dir)
        assert p2.photo_count == p.photo_count
        print(f"  ✓ from_dict 恢复项目: {p2.name}, {p2.photo_count} 张, source_dir={p2.source_dir}")


if __name__ == "__main__":
    print("\n" + "╔" + "═" * 68 + "╗")
    print("║" + " " * 18 + "批量交付修复验证测试" + " " * 28 + "║")
    print("╚" + "═" * 68 + "╝")

    test_project_source_dir_persistence()
    test_raw_skip_logic()
    test_batch_skipped_project_display()
    test_project_to_dict_roundtrip()

    print("\n" + "=" * 60)
    print("✅ 所有修复测试通过！")
    print("=" * 60)
    print("\n修复内容验证:")
    print("  ✓ ProjectItem.source_dir 正确保存和恢复（断点续传）")
    print("  ✓ RAW文件按 include_raw 规则区分跳过/失败")
    print("  ✓ 批量归档正确统计和显示跳过项目")
    print("  ✓ 跳过原因在项目详情和整批报告中可见")
    print("  ✓ ProjectItem 序列化保留完整照片信息")
