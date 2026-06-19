import os
import zipfile
import json
import shutil
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timedelta

from .scanner import ProjectItem, PhotoItem
from .rules import RulesConfig
from .image_processor import ImageProcessor
from .logger import Logger
from .config import AppConfig


class PackageGenerator:
    def __init__(self, rules: RulesConfig, logger: Logger):
        self.rules = rules
        self.logger = logger
        self.image_processor = ImageProcessor()

    def generate_package(
        self,
        project: ProjectItem,
        output_dir: str,
        selected_photos: Optional[List[PhotoItem]] = None
    ) -> Path:
        self.logger.reset_stats()
        self.logger.stats.total_files = project.photo_count

        output_path = Path(output_dir)
        package_name = self._generate_package_name(project)
        package_dir = output_path / package_name

        if package_dir.exists():
            shutil.rmtree(package_dir)

        package_dir.mkdir(parents=True, exist_ok=True)

        photos_to_process = selected_photos if selected_photos else project.photos

        self.logger.log_system(f"开始生成选片包: {package_name}")
        self.logger.log_system(f"输出目录: {package_dir}")

        thumbs_dir = package_dir / "thumbnails"
        originals_dir = package_dir / "originals"
        thumbs_dir.mkdir(exist_ok=True)
        originals_dir.mkdir(exist_ok=True)

        index = 1
        manifest = {
            "project_name": project.name,
            "client_name": project.client_name,
            "shoot_date": project.shoot_date,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_photos": len(photos_to_process),
            "photos": []
        }

        if self.rules.expire_enabled:
            expire_date = datetime.now() + timedelta(days=self.rules.expire_days)
            manifest["expire_date"] = expire_date.strftime("%Y-%m-%d")

        for photo in photos_to_process:
            try:
                ext = photo.path.suffix.lower()
                is_raw = ext in AppConfig.SUPPORTED_RAW_EXTENSIONS

                if is_raw and not self.rules.include_raw:
                    self.logger.log_skip("RAW文件未启用包含，按规则跳过", photo.filename)
                    continue

                if not self.image_processor.is_valid_image(photo.path) and not is_raw:
                    self.logger.log_failure(photo.filename, "文件损坏或格式不支持")
                    continue

                new_filename = self._generate_filename(project, photo, index)

                thumb_filename = Path(new_filename).stem + ".jpg"
                thumb_path = thumbs_dir / thumb_filename

                if is_raw:
                    thumb_ok = False
                    try:
                        watermark_text = self.rules.watermark_text if self.rules.watermark_enabled else ""
                        thumb_ok = self.image_processor.generate_thumbnail(
                            photo.path,
                            thumb_path,
                            self.rules.thumbnail_size,
                            quality=self.rules.jpeg_quality,
                            watermark_text=watermark_text,
                            watermark_opacity=self.rules.watermark_opacity
                        )
                    except Exception:
                        thumb_ok = False
                    if not thumb_ok:
                        self.logger.log_skip("RAW文件无法生成缩略图，已跳过", photo.filename)
                        continue
                else:
                    watermark_text = self.rules.watermark_text if self.rules.watermark_enabled else ""
                    success = self.image_processor.generate_thumbnail(
                        photo.path,
                        thumb_path,
                        self.rules.thumbnail_size,
                        quality=self.rules.jpeg_quality,
                        watermark_text=watermark_text,
                        watermark_opacity=self.rules.watermark_opacity
                    )

                    if not success:
                        self.logger.log_failure(photo.filename, "缩略图生成失败")
                        continue

                if self.rules.include_raw and is_raw:
                    orig_path = originals_dir / (Path(new_filename).stem + ext)
                else:
                    orig_ext = self._resolve_extension(photo)
                    orig_path = originals_dir / (Path(new_filename).stem + orig_ext)
                shutil.copy2(photo.path, orig_path)

                manifest["photos"].append({
                    "original_name": photo.filename,
                    "new_name": new_filename,
                    "thumbnail": f"thumbnails/{thumb_filename}",
                    "original": f"originals/{orig_path.name}",
                    "size": photo.size,
                    "is_raw": is_raw
                })

                self.logger.increment_processed()
                index += 1

            except Exception as e:
                self.logger.log_failure(photo.filename, str(e))

        self._generate_manifest(package_dir, manifest)
        self._generate_readme(package_dir, project, manifest)
        self._generate_selection_form(package_dir, project, manifest)
        self._generate_cover(package_dir, project)

        self.logger.finish_processing()
        self.logger.log_success(f"选片包生成完成: {package_name}")

        return package_dir

    def generate_zip(self, package_dir: Path) -> Path:
        zip_path = package_dir.parent / f"{package_dir.name}.zip"

        if zip_path.exists():
            zip_path.unlink()

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(package_dir):
                for file in files:
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(package_dir.parent)
                    zipf.write(file_path, arcname)

        self.logger.log_success(f"压缩包生成完成: {zip_path.name}")
        return zip_path

    def _generate_package_name(self, project: ProjectItem) -> str:
        date_str = project.shoot_date or datetime.now().strftime("%Y%m%d")
        name = project.client_name or project.name
        return f"{date_str}_{name}_选片包"

    def _resolve_extension(self, photo: PhotoItem) -> str:
        fmt = self.rules.output_format
        if fmt == "original" or not fmt:
            return photo.path.suffix.lower()
        else:
            return f".{fmt}"

    def _generate_filename(self, project: ProjectItem, photo: PhotoItem, index: int) -> str:
        try:
            name = self.rules.naming_pattern.format(
                client=project.client_name or "client",
                date=project.shoot_date or "unknown",
                index=index,
                original=photo.path.stem
            )
        except Exception:
            name = f"{project.client_name or 'photo'}_{index:04d}"

        ext = self._resolve_extension(photo)
        return name + ext

    def _generate_manifest(self, package_dir: Path, manifest: dict):
        manifest_path = package_dir / "manifest.json"
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

    def _generate_readme(self, package_dir: Path, project: ProjectItem, manifest: dict):
        readme_path = package_dir / "客户说明.txt"

        lines = []
        lines.append("=" * 60)
        lines.append("尊敬的客户，您好！")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"客户姓名: {project.client_name or '待填写'}")
        lines.append(f"拍摄日期: {project.shoot_date or '待填写'}")
        lines.append(f"照片总数: {manifest['total_photos']} 张")
        lines.append("")
        lines.append("-" * 60)
        lines.append("目录说明:")
        lines.append("  thumbnails/  - 缩略图（带水印，用于选片）")
        lines.append("  originals/   - 原片（高清无水印，入选后交付）")
        lines.append("")
        lines.append("-" * 60)
        lines.append("选片说明:")
        lines.append(f"  1. 请从 {manifest['total_photos']} 张照片中选择您喜欢的照片")
        lines.append(f"  2. 入选上限: {self.rules.max_selection} 张")
        lines.append("  3. 请将选中照片的编号填写在『回传清单.xlsx』或『回传清单.txt』中")
        lines.append("  4. 选片完成后请将清单回传给我们")
        lines.append("")

        if self.rules.expire_enabled:
            expire_date = manifest.get("expire_date", "")
            lines.append("-" * 60)
            lines.append(f"⚠  过期提示:")
            lines.append(f"   本选片包将于 {expire_date} 过期")
            lines.append(f"   请在此日期前完成选片，逾期将自动删除")
            lines.append("")

        lines.append("-" * 60)
        lines.append("联系方式:")
        lines.append("  微信: 待填写")
        lines.append("  电话: 待填写")
        lines.append("")
        lines.append("感谢您的选择，期待为您服务！")
        lines.append("=" * 60)

        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))

    def _generate_selection_form(self, package_dir: Path, project: ProjectItem, manifest: dict):
        form_path = package_dir / "回传清单.txt"

        lines = []
        lines.append("=" * 60)
        lines.append("选片回传清单")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"客户姓名: {project.client_name or '_______________'}")
        lines.append(f"联系电话: _______________")
        lines.append(f"选片日期: _______________")
        lines.append("")
        lines.append("-" * 60)
        lines.append(f"照片总数: {manifest['total_photos']} 张")
        lines.append(f"入选上限: {self.rules.max_selection} 张")
        lines.append("")
        lines.append("请在您选中的照片编号前打 √ 或填写选中的编号:")
        lines.append("")

        lines.append("选中的照片编号:")
        lines.append("")
        for i, photo in enumerate(manifest["photos"], 1):
            lines.append(f"  [ ] {i:04d}. {photo['new_name']}")

        lines.append("")
        lines.append("-" * 60)
        lines.append("备注:")
        lines.append("  _______________________________________________")
        lines.append("  _______________________________________________")
        lines.append("")
        lines.append("=" * 60)

        with open(form_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))

    def _generate_cover(self, package_dir: Path, project: ProjectItem):
        if project.cover_path and project.cover_path.exists():
            cover_dst = package_dir / "cover.jpg"
            self.image_processor.generate_thumbnail(
                project.cover_path,
                cover_dst,
                (1200, 800),
                quality=90,
                watermark_text=self.rules.watermark_text if self.rules.watermark_enabled else "",
                watermark_opacity=self.rules.watermark_opacity
            )
