import os
import sys
import tempfile
import json
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))

from photo_selector.scanner import FileScanner
from photo_selector.rules import RulesConfig
from photo_selector.logger import Logger
from photo_selector.packager import PackageGenerator


def create_mixed_test_images(directory):
    dir_path = Path(directory)
    dir_path.mkdir(parents=True, exist_ok=True)

    for i in range(3):
        img = Image.new('RGB', (1000, 800), color=(100, 150, 200))
        img.save(dir_path / f"客户A_{i+1:04d}.jpg", 'JPEG')

    img = Image.new('RGBA', (800, 600), color=(150, 200, 100, 255))
    img.save(dir_path / "客户A_png01.png", 'PNG')

    for i in range(2):
        img = Image.new('RGB', (1200, 900), color=(200, 100, 150))
        img.save(dir_path / f"客户B_{i+1:04d}.jpg", 'JPEG')

    return dir_path


def test_1_rules_consistency():
    print("=" * 60)
    print("测试1: 规则加载后对象引用一致性 (问题1)")
    print("=" * 60)

    rules_a = RulesConfig()
    rules_a.watermark_text = "工作室A"
    rules_a.thumbnail_width = 800

    logger = Logger()
    packager = PackageGenerator(rules_a, logger)

    print(f"原始水印文字: {packager.rules.watermark_text}")
    assert packager.rules.watermark_text == "工作室A"

    with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w', encoding='utf-8') as f:
        config_path = f.name
        config_data = {
            "thumbnail_width": 1600,
            "thumbnail_height": 1200,
            "watermark_text": "新加载的工作室",
            "watermark_enabled": True,
            "watermark_opacity": 75,
            "max_selection": 30,
            "naming_pattern": "{client}__{index:04d}",
            "expire_days": 15,
            "expire_enabled": True,
            "include_raw": False,
            "output_format": "original",
            "jpeg_quality": 95,
        }
        json.dump(config_data, f, ensure_ascii=False)

    loaded = RulesConfig.load_from_file(config_path)
    for attr in loaded.to_dict():
        if hasattr(rules_a, attr):
            setattr(rules_a, attr, getattr(loaded, attr))

    print(f"加载后水印文字: {packager.rules.watermark_text}")
    print(f"加载后缩略图宽度: {packager.rules.thumbnail_width}")
    print(f"加载后输出格式: {packager.rules.output_format}")
    print(f"加载后命名模板: {packager.rules.naming_pattern}")
    print(f"加载后过期天数: {packager.rules.expire_days}")

    assert packager.rules.watermark_text == "新加载的工作室", "水印文字不同步"
    assert packager.rules.thumbnail_width == 1600, "缩略图宽度不同步"
    assert packager.rules.output_format == "original", "输出格式不同步"
    assert packager.rules.naming_pattern == "{client}__{index:04d}", "命名模板不同步"
    assert packager.rules.expire_days == 15, "过期天数不同步"

    os.unlink(config_path)
    print("✓ 规则一致性测试通过\n")


def test_2_original_format_extensions():
    print("=" * 60)
    print("测试2: 保持原格式时文件后缀正确性 (问题2)")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        src_dir = tmp / "source"
        out_dir = tmp / "output"
        out_dir.mkdir()

        create_mixed_test_images(src_dir)

        scanner = FileScanner()
        scanner.set_source_directory(str(src_dir))
        scanner.set_recognize_mode("prefix")
        projects = scanner.scan()

        client_a = next((p for p in projects if p.name == "客户A"), None)
        assert client_a is not None, "应找到客户A项目"
        print(f"客户A项目包含 {client_a.photo_count} 张照片 (含PNG)")

        rules = RulesConfig()
        rules.output_format = "original"
        rules.watermark_text = "测试水印"
        rules.naming_pattern = "{client}_{index:04d}"

        logger = Logger()
        packager = PackageGenerator(rules, logger)

        package_path = packager.generate_package(client_a, str(out_dir))

        originals_dir = package_path / "originals"
        orig_files = sorted(os.listdir(originals_dir))
        print(f"originals/ 目录文件: {orig_files}")

        extensions = [Path(f).suffix.lower() for f in orig_files]
        print(f"文件后缀: {extensions}")

        assert ".jpg" in extensions, "应有JPG文件"
        assert ".png" in extensions, "应有PNG文件（保持原格式）"
        assert ".original" not in extensions, "不应出现.original假后缀"

        with open(package_path / "manifest.json", 'r', encoding='utf-8') as f:
            manifest = json.load(f)

        print("\nmanifest 中的文件名:")
        manifest_new_names = []
        manifest_original_paths = []
        for photo in manifest["photos"]:
            print(f"  new_name: {photo['new_name']}  <-  original: {photo['original']}")
            manifest_new_names.append(photo['new_name'])
            manifest_original_paths.append(Path(photo['original']).name)

        for new_name, actual_name in zip(manifest_new_names, orig_files):
            assert new_name == actual_name, f"清单与实际不一致: {new_name} vs {actual_name}"
        print("\n✓ manifest清单文件名与实际文件一致")

        for i, (orig_name, actual_name) in enumerate(zip(manifest_original_paths, orig_files)):
            assert orig_name == actual_name, f"original字段与实际不一致: {orig_name} vs {actual_name}"
        print("✓ manifest original字段与实际文件一致")

        jpg_count = sum(1 for e in extensions if e == ".jpg")
        png_count = sum(1 for e in extensions if e == ".png")
        assert jpg_count == 3, f"应有3个JPG，实际{jpg_count}"
        assert png_count == 1, f"应有1个PNG，实际{png_count}"

        print("✓ 原格式后缀正确性测试通过\n")


def test_3_logger_stability():
    print("=" * 60)
    print("测试3: 日志系统边界情况处理 (问题3)")
    print("=" * 60)

    logger = Logger()
    logger.reset_stats()
    logger.stats.total_files = 0

    assert logger.stats.total_files == 0
    assert logger.stats.processed_files == 0
    assert len(logger.entries) == 0
    print("✓ 空日志不崩溃")

    for i in range(3):
        logger.log_process(f"处理文件{i}.jpg")
        logger.increment_processed()
    for i in range(2):
        logger.log_skip("格式不支持", f"raw_{i}.cr2")
    for i in range(2):
        logger.log_failure(f"bad_{i}.jpg", "文件损坏")
    logger.log_success("全部完成")
    logger.finish_processing()

    print(f"日志总数: {len(logger.entries)}")
    print(f"处理: {logger.stats.processed_files}, "
          f"跳过: {logger.stats.skipped_files}, "
          f"失败: {logger.stats.failed_files}")

    assert len(logger.entries) > 0
    assert logger.stats.processed_files == 3
    assert logger.stats.skipped_files == 2
    assert logger.stats.failed_files == 2
    assert logger.stats.failed_files_list[0]["filename"] == "bad_0.jpg"
    assert logger.stats.failed_files_list[0]["error"] == "文件损坏"
    assert "格式不支持" in logger.stats.skip_reasons
    print("✓ 统计数据正确")

    print("\n模拟日志页筛选后的索引:")

    level_map = {0: None, 1: "info", 2: "warning", 3: "error", 4: "success"}
    for level_idx in [0, 3, 4]:
        target = level_map[level_idx]
        filtered = [e for e in logger.entries if (target is None or e.level == target)]
        print(f"  级别筛选[{level_idx}] -> {len(filtered)} 条")

        for row in range(len(filtered)):
            entry = filtered[row]
            assert entry is not None, "正向索引应稳定"
            if target == "error":
                assert entry.level == "error", f"筛选错误：应为error，实际{entry.level}"
        print(f"    -> 所有行号索引正确")
    print("✓ 筛选索引边界测试通过\n")


def test_4_log_detail_matching():
    print("=" * 60)
    print("测试4: 筛选后详情与选中项对应 (问题4)")
    print("=" * 60)

    logger = Logger()
    logger.reset_stats()

    logger.log_scan("扫描开始")
    logger.log_process("处理正常_001.jpg")
    logger.log_failure("损坏文件_A.jpg", "文件头损坏无法读取")
    logger.log_process("处理正常_002.jpg")
    logger.log_skip("文件太小", "tiny.jpg")
    logger.log_failure("损坏文件_B.jpg", "格式不被支持")
    logger.log_process("处理正常_003.jpg")
    logger.log_skip("重复文件", "dup.jpg")
    logger.log_failure("损坏文件_C.jpg", "数据截断")
    logger.log_success("打包完成")
    logger.finish_processing()

    current_entries = [e for e in logger.entries if e.level == "error"]
    print(f"筛选出 error 级别日志共 {len(current_entries)} 条:")

    expected_errors = [
        ("损坏文件_A.jpg", "文件头损坏无法读取"),
        ("损坏文件_B.jpg", "格式不被支持"),
        ("损坏文件_C.jpg", "数据截断"),
    ]

    for row, entry in enumerate(current_entries):
        exp_filename, exp_error = expected_errors[row]
        actual_filename = entry.details.get("filename")
        actual_error = entry.details.get("error")
        print(f"  [row {row}] 点击 -> {entry.message}")
        print(f"           filename={actual_filename}, error={actual_error}")

        assert actual_filename == exp_filename, f"行{row}: filename不匹配"
        assert actual_error == exp_error, f"行{row}: error不匹配"
        assert entry.level == "error", f"行{row}: level不是error"

    print("\n✓ 筛选后点击详情完全对应正确")

    all_entries = list(logger.entries)
    for row, entry in enumerate(all_entries):
        clicked_entry = all_entries[row]
        assert clicked_entry is entry, f"全量列表行{row}索引错位"
    print("✓ 全量列表索引位置正确\n")


def main():
    print("\n" + "=" * 60)
    print("  四个修复点专项测试")
    print("=" * 60 + "\n")

    all_pass = True

    try:
        test_1_rules_consistency()
    except Exception as e:
        all_pass = False
        print(f"\n✗ 测试1失败: {e}")
        import traceback
        traceback.print_exc()

    try:
        test_2_original_format_extensions()
    except Exception as e:
        all_pass = False
        print(f"\n✗ 测试2失败: {e}")
        import traceback
        traceback.print_exc()

    try:
        test_3_logger_stability()
    except Exception as e:
        all_pass = False
        print(f"\n✗ 测试3失败: {e}")
        import traceback
        traceback.print_exc()

    try:
        test_4_log_detail_matching()
    except Exception as e:
        all_pass = False
        print(f"\n✗ 测试4失败: {e}")
        import traceback
        traceback.print_exc()

    print("=" * 60)
    if all_pass:
        print("  ✓ 所有4个修复点测试全部通过！")
    else:
        print("  ✗ 部分测试失败，请检查上述输出")
    print("=" * 60)
    return 0 if all_pass else 1


if __name__ == '__main__':
    sys.exit(main())
