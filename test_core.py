import os
import sys
import tempfile
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))

from photo_selector.scanner import FileScanner
from photo_selector.rules import RulesConfig
from photo_selector.image_processor import ImageProcessor
from photo_selector.logger import Logger
from photo_selector.packager import PackageGenerator


def create_test_images(directory, count=10, prefix="test"):
    dir_path = Path(directory)
    dir_path.mkdir(parents=True, exist_ok=True)

    for i in range(count):
        img = Image.new('RGB', (1920, 1280), color=(73, 109, 137))
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(img)
        draw.text((100, 100), f"Test Photo {i+1}", fill=(255, 255, 255))

        if i < 5:
            filename = f"clientA_{i+1:04d}.jpg"
        else:
            filename = f"clientB_{i+1:04d}.jpg"

        img.save(dir_path / filename, 'JPEG', quality=85)

    return dir_path


def test_scanner():
    print("=" * 50)
    print("测试1: 文件扫描模块")
    print("=" * 50)

    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = create_test_images(tmpdir, count=10)

        scanner = FileScanner()
        scanner.set_source_directory(str(test_dir))
        scanner.set_recognize_mode("prefix")

        projects = scanner.scan()
        print(f"扫描到 {len(projects)} 个项目")
        for project in projects:
            print(f"  - {project.name}: {project.photo_count} 张照片")

        assert len(projects) >= 1, "至少应该识别到1个项目"
        print("✓ 扫描测试通过\n")
        return scanner


def test_rules():
    print("=" * 50)
    print("测试2: 规则配置模块")
    print("=" * 50)

    rules = RulesConfig()
    print(f"默认缩略图尺寸: {rules.thumbnail_size}")
    print(f"默认水印文字: {rules.watermark_text}")
    print(f"默认入选上限: {rules.max_selection}")
    print(f"默认命名模板: {rules.naming_pattern}")
    print(f"默认过期天数: {rules.expire_days}")

    rules.thumbnail_width = 1024
    rules.watermark_text = "测试工作室"
    rules.max_selection = 100

    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
        config_path = f.name

    rules.save_to_file(config_path)
    print(f"配置已保存到: {config_path}")

    loaded_rules = RulesConfig.load_from_file(config_path)
    assert loaded_rules.thumbnail_width == 1024
    assert loaded_rules.watermark_text == "测试工作室"
    assert loaded_rules.max_selection == 100
    print("✓ 规则配置测试通过\n")

    os.unlink(config_path)
    return rules


def test_image_processor():
    print("=" * 50)
    print("测试3: 图像处理模块")
    print("=" * 50)

    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir)
        src_img = test_dir / "test.jpg"

        img = Image.new('RGB', (1920, 1280), color=(73, 109, 137))
        img.save(src_img, 'JPEG', quality=95)

        processor = ImageProcessor()
        thumb_path = test_dir / "thumb.jpg"

        success = processor.generate_thumbnail(
            src_img,
            thumb_path,
            size=(400, 300),
            quality=80,
            watermark_text="测试水印",
            watermark_opacity=50
        )

        assert success, "缩略图生成失败"
        assert thumb_path.exists(), "缩略图文件不存在"

        with Image.open(thumb_path) as thumb:
            width, height = thumb.size
            print(f"生成缩略图尺寸: {width}x{height}")
            assert width <= 400 and height <= 300, "缩略图尺寸超过限制"

        print("✓ 图像处理测试通过\n")


def test_logger():
    print("=" * 50)
    print("测试4: 日志模块")
    print("=" * 50)

    logger = Logger()
    logger.reset_stats()
    logger.stats.total_files = 10

    logger.log_scan("开始扫描目录")
    logger.log_process("处理图片1.jpg")
    logger.log_skip("文件格式不支持", "raw_file.cr2")
    logger.log_skip("文件太小", "tiny.jpg")
    logger.log_failure("bad.jpg", "文件损坏")
    logger.log_success("打包完成")

    logger.increment_processed()
    logger.increment_processed()
    logger.increment_processed()

    logger.finish_processing()

    print(f"总文件数: {logger.stats.total_files}")
    print(f"已处理: {logger.stats.processed_files}")
    print(f"已跳过: {logger.stats.skipped_files}")
    print(f"失败: {logger.stats.failed_files}")
    print(f"日志条目数: {len(logger.entries)}")
    print(f"跳过原因: {logger.stats.skip_reasons}")

    assert logger.stats.total_files == 10
    assert logger.stats.processed_files == 3
    assert logger.stats.skipped_files == 2
    assert logger.stats.failed_files == 1
    assert len(logger.entries) == 6

    print("✓ 日志模块测试通过\n")
    return logger


def test_packager():
    print("=" * 50)
    print("测试5: 打包输出模块")
    print("=" * 50)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        src_dir = tmp / "source"
        out_dir = tmp / "output"
        out_dir.mkdir()

        create_test_images(src_dir, count=6)

        scanner = FileScanner()
        scanner.set_source_directory(str(src_dir))
        scanner.set_recognize_mode("prefix")
        projects = scanner.scan()

        rules = RulesConfig()
        rules.watermark_text = "测试工作室"
        rules.watermark_enabled = True

        logger = Logger()
        logger.set_log_directory(str(out_dir / "logs"))

        packager = PackageGenerator(rules, logger)

        project = projects[0]
        print(f"打包项目: {project.name} ({project.photo_count} 张)")

        package_path = packager.generate_package(project, str(out_dir))
        print(f"选片包路径: {package_path}")

        assert package_path.exists(), "选片包目录不存在"

        contents = list(package_path.iterdir())
        print(f"选片包内容:")
        for item in contents:
            print(f"  - {item.name}")

        thumbs = list((package_path / "thumbnails").iterdir())
        originals = list((package_path / "originals").iterdir())
        print(f"缩略图数量: {len(thumbs)}")
        print(f"原片数量: {len(originals)}")

        assert (package_path / "客户说明.txt").exists()
        assert (package_path / "回传清单.txt").exists()
        assert (package_path / "manifest.json").exists()
        assert len(thumbs) == project.photo_count
        assert len(originals) == project.photo_count

        print("✓ 打包输出测试通过\n")


def main():
    print("\n" + "=" * 60)
    print("  选片包生成工具 - 核心模块功能测试")
    print("=" * 60 + "\n")

    try:
        test_scanner()
        test_rules()
        test_image_processor()
        test_logger()
        test_packager()

        print("=" * 60)
        print("  ✓ 所有测试通过！")
        print("=" * 60)
        return 0
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
