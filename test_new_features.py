import os
import sys
import tempfile
import json
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))

from photo_selector.scanner import FileScanner
from photo_selector.rules import RulesConfig
from photo_selector.logger import Logger, PackageHistory, PackageRecord, ProcessingStats
from photo_selector.packager import PackageGenerator
from photo_selector.image_processor import ImageProcessor


def create_test_images(directory, projects=2, per_project=5):
    dir_path = Path(directory)
    dir_path.mkdir(parents=True, exist_ok=True)

    for p in range(projects):
        for i in range(per_project):
            img = Image.new('RGB', (1600, 1200), color=(100 + p * 50, 150, 200))
            from PIL import ImageDraw
            draw = ImageDraw.Draw(img)
            draw.text((50, 50), f"Project{p+1}_{i+1:04d}", fill=(255, 255, 255))
            img.save(dir_path / f"项目{p+1}_{i+1:04d}.jpg", 'JPEG', quality=85)

    return dir_path


def test_1_image_processor_render():
    print("=" * 60)
    print("测试1: ImageProcessor 渲染预览图 (功能1基础)")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "test.jpg"
        Image.new('RGB', (1920, 1280), color=(100, 150, 200)).save(src, 'JPEG')

        processor = ImageProcessor()

        pil_img = processor.render_thumbnail_image(
            src,
            size=(800, 600),
            watermark_text="测试水印",
            watermark_opacity=50
        )

        assert pil_img is not None, "渲染失败"
        assert pil_img.width <= 800 and pil_img.height <= 600, f"尺寸超了: {pil_img.size}"
        print(f"渲染尺寸: {pil_img.width} × {pil_img.height}")

        pil_img_no_wm = processor.render_thumbnail_image(
            src, size=(400, 300), watermark_text="", watermark_opacity=0
        )
        assert pil_img_no_wm is not None
        assert pil_img_no_wm.width <= 400
        print("无水印渲染正常")

        data = pil_img.tobytes()
        assert len(data) > 0
        print("图像数据有效")

    print("✓ ImageProcessor 渲染测试通过\n")


def test_2_package_history():
    print("=" * 60)
    print("测试2: PackageHistory 打包历史记录 (功能4基础)")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        hist_dir = Path(tmpdir) / "history"
        history = PackageHistory()
        history.set_history_directory(str(hist_dir))

        stats1 = ProcessingStats()
        stats1.total_files = 10
        stats1.processed_files = 8
        stats1.skipped_files = 1
        stats1.failed_files = 1
        stats1.skip_reasons = {"格式不支持": 1}
        stats1.failed_files_list = [{"filename": "bad.jpg", "error": "损坏"}]

        record1 = history.create_record_from_stats(
            project_name="项目A",
            client_name="客户A",
            shoot_date="2026-06-01",
            package_path="/output/项目A_选片包",
            stats=stats1,
            status="success"
        )

        stats2 = ProcessingStats()
        stats2.total_files = 5
        stats2.processed_files = 5
        stats2.skipped_files = 0
        stats2.failed_files = 0

        record2 = history.create_record_from_stats(
            project_name="项目B",
            client_name="客户B",
            shoot_date="2026-06-05",
            package_path="/output/项目B_选片包",
            stats=stats2,
            status="success"
        )

        print(f"记录总数: {len(history.records)}")
        assert len(history.records) == 2

        projects = history.get_all_projects()
        print(f"项目列表: {projects}")
        assert "项目A" in projects and "项目B" in projects

        proj_a_records = history.get_records_by_project("项目A")
        assert len(proj_a_records) == 1
        assert proj_a_records[0].total_photos == 10
        assert proj_a_records[0].processed == 8
        print(f"项目A记录: {proj_a_records[0].processed} 成功, {proj_a_records[0].skipped} 跳过")

        import time
        time.sleep(0.1)
        history2 = PackageHistory()
        history2.set_history_directory(str(hist_dir))
        assert len(history2.records) == 2, "磁盘加载失败"
        print("✓ 磁盘持久化加载成功")

        date_records = history.get_records_by_date_range("2026-06-01", "2026-12-31")
        assert len(date_records) >= 1
        print("✓ 日期范围筛选正常")

    print("✓ PackageHistory 测试通过\n")


def test_3_delivery_check_logic():
    print("=" * 60)
    print("测试3: 交付检查逻辑 (功能2基础)")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        src_dir = Path(tmpdir) / "source"
        create_test_images(src_dir, projects=3, per_project=4)

        scanner = FileScanner()
        scanner.set_source_directory(str(src_dir))
        scanner.set_recognize_mode("prefix")
        projects = scanner.scan()

        print(f"扫描到 {len(projects)} 个项目")
        assert len(projects) == 3

        rules = RulesConfig()
        rules.watermark_text = "测试工作室"
        rules.watermark_enabled = True
        rules.max_selection = 10
        rules.expire_enabled = True
        rules.expire_days = 30
        rules.output_format = "original"

        from datetime import datetime, timedelta
        expire = datetime.now() + timedelta(days=rules.expire_days)
        print(f"过期日期: {expire.strftime('%Y-%m-%d')}")

        processor = ImageProcessor()
        for project in projects:
            print(f"\n▶ {project.name}")
            print(f"   照片数: {project.photo_count}")
            print(f"   客户名: {project.client_name or '未识别'}")
            print(f"   拍摄日期: {project.shoot_date or '未识别'}")

            corrupted = 0
            raw_count = 0
            for photo in project.photos:
                ext = photo.path.suffix.lower()
                if ext in {'.raw', '.cr2'}:
                    raw_count += 1
                if not processor.is_valid_image(photo.path):
                    corrupted += 1

            print(f"   损坏文件: {corrupted}")
            print(f"   RAW文件: {raw_count}")

            sample_names = []
            for i, photo in enumerate(project.photos[:3], 1):
                try:
                    base = rules.naming_pattern.format(
                        client=project.client_name or "client",
                        date=project.shoot_date or "unknown",
                        index=i,
                        original=photo.path.stem
                    )
                except Exception:
                    base = f"photo_{i:04d}"
                if rules.output_format == "original":
                    ext = photo.path.suffix.lower()
                else:
                    ext = f".{rules.output_format}"
                sample_names.append(base + ext)

            print(f"   文件名示例: {sample_names}")

        total_photos = sum(p.photo_count for p in projects)
        total_size = sum(p.total_size for p in projects) / (1024 * 1024)
        print(f"\n汇总: {len(projects)} 个项目, {total_photos} 张照片, {total_size:.1f} MB")

    print("\n✓ 交付检查逻辑测试通过\n")


def test_4_batch_package_logic():
    print("=" * 60)
    print("测试4: 批量生成 + 历史记录整合 (功能3+4)")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        src_dir = tmp / "source"
        out_dir = tmp / "output"
        out_dir.mkdir()
        hist_dir = tmp / "history"
        hist_dir.mkdir()

        create_test_images(src_dir, projects=3, per_project=6)

        scanner = FileScanner()
        scanner.set_source_directory(str(src_dir))
        scanner.set_recognize_mode("prefix")
        projects = scanner.scan()
        print(f"准备 {len(projects)} 个测试项目")

        rules = RulesConfig()
        rules.watermark_text = "批量测试水印"

        logger = Logger()
        history = PackageHistory()
        history.set_history_directory(str(hist_dir))
        packager = PackageGenerator(rules, logger)

        results = []
        for idx, project in enumerate(projects):
            print(f"[{idx+1}/{len(projects)}] 生成 {project.name}...")

            logger.reset_stats()
            logger.stats.total_files = project.photo_count

            package_path = packager.generate_package(project, str(out_dir))
            assert package_path.exists()

            record = history.create_record_from_stats(
                project_name=project.name,
                client_name=project.client_name,
                shoot_date=project.shoot_date,
                package_path=str(package_path),
                stats=logger.stats,
                status="success"
            )

            results.append({
                "project": project.name,
                "processed": record.processed,
                "total": record.total_photos
            })
            print(f"  ✓ 成功: {record.processed}/{record.total_photos}")

        print(f"\n批量完成: {len(results)} 个项目")
        for r in results:
            assert r["processed"] > 0
            print(f"  • {r['project']}: {r['processed']} 张")

        proj_names = history.get_all_projects()
        assert len(proj_names) == len(projects)
        print(f"\n历史记录项目数: {len(proj_names)}")

        for pname in proj_names:
            records = history.get_records_by_project(pname)
            assert len(records) == 1
            assert records[0].processed > 0
            assert records[0].total_photos == 6
            assert records[0].status == "success"
            print(f"  • {pname}: {records[0].total_photos}张, 失败{records[0].failed}张")

        history2 = PackageHistory()
        history2.set_history_directory(str(hist_dir))
        assert len(history2.records) == len(projects)
        print("\n✓ 历史记录磁盘持久化验证通过")

        print("\n✓ 批量生成 + 历史记录测试通过\n")


def test_5_rules_effectiveness():
    print("=" * 60)
    print("测试5: 规则加载后在打包中生效 (问题1回归)")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        src_dir = tmp / "source"
        out_dir = tmp / "output"
        out_dir.mkdir()

        create_test_images(src_dir, projects=1, per_project=3)

        scanner = FileScanner()
        scanner.set_source_directory(str(src_dir))
        projects = scanner.scan()
        project = projects[0]

        rules = RulesConfig()
        rules.watermark_text = "原始水印"
        rules.thumbnail_width = 600
        rules.thumbnail_height = 400

        logger = Logger()
        packager = PackageGenerator(rules, logger)

        logger.reset_stats()
        pkg1 = packager.generate_package(project, str(out_dir / "pkg1"))

        config_path = tmp / "rules.json"
        new_rules = RulesConfig()
        new_rules.watermark_text = "新加载的水印"
        new_rules.thumbnail_width = 1024
        new_rules.thumbnail_height = 768
        new_rules.watermark_opacity = 80
        new_rules.naming_pattern = "NEW_{index:04d}"
        new_rules.save_to_file(str(config_path))

        loaded = RulesConfig.load_from_file(str(config_path))
        for attr in loaded.to_dict():
            if hasattr(rules, attr):
                setattr(rules, attr, getattr(loaded, attr))

        assert packager.rules.watermark_text == "新加载的水印", "水印文字没同步"
        assert packager.rules.thumbnail_width == 1024, "宽度没同步"
        assert packager.rules.naming_pattern == "NEW_{index:04d}", "命名没同步"
        print("✓ 规则加载后 packager 同步生效")

        logger.reset_stats()
        pkg2 = packager.generate_package(project, str(out_dir / "pkg2"))

        orig_files = sorted(os.listdir(pkg2 / "originals"))
        print(f"新文件名: {orig_files}")
        assert all(f.startswith("NEW_") for f in orig_files), "命名模板没生效"

        from PIL import Image as PILImage
        thumb_path = pkg2 / "thumbnails" / orig_files[0]
        with PILImage.open(thumb_path) as thumb:
            print(f"缩略图尺寸: {thumb.size}")
            assert thumb.width <= 1024 and thumb.height <= 768, "缩略图尺寸没生效"

        print("✓ 所有规则在生成中正确生效")

    print("\n✓ 规则有效性测试通过\n")


def main():
    print("\n" + "=" * 60)
    print("  新功能综合测试")
    print("=" * 60 + "\n")

    tests = [
        ("ImageProcessor 渲染预览", test_1_image_processor_render),
        ("PackageHistory 历史记录", test_2_package_history),
        ("交付检查逻辑", test_3_delivery_check_logic),
        ("批量生成 + 历史整合", test_4_batch_package_logic),
        ("规则生效验证", test_5_rules_effectiveness),
    ]

    passed = 0
    failed = 0

    for name, func in tests:
        try:
            func()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"\n✗ 测试 [{name}] 失败: {e}")
            import traceback
            traceback.print_exc()
            print()

    print("=" * 60)
    print(f"  测试结果: {passed} 通过 / {failed} 失败 / {len(tests)} 总计")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
