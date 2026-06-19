from pathlib import Path
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageOps
from .config import AppConfig


class ImageProcessor:
    def __init__(self):
        pass

    def generate_thumbnail(
        self,
        src_path: Path,
        dst_path: Path,
        size: Tuple[int, int],
        quality: int = 85,
        watermark_text: str = "",
        watermark_opacity: int = 50
    ) -> bool:
        try:
            img = Image.open(src_path)
            img = ImageOps.exif_transpose(img)

            img.thumbnail(size, Image.LANCZOS)

            if img.mode not in ('RGB', 'RGBA'):
                img = img.convert('RGB')

            if watermark_text and watermark_opacity > 0:
                img = self._add_watermark(img, watermark_text, watermark_opacity)

            dst_path.parent.mkdir(parents=True, exist_ok=True)

            if dst_path.suffix.lower() in ('.jpg', '.jpeg'):
                if img.mode == 'RGBA':
                    img = img.convert('RGB')
                img.save(dst_path, 'JPEG', quality=quality, optimize=True)
            elif dst_path.suffix.lower() == '.png':
                img.save(dst_path, 'PNG', optimize=True)
            else:
                img.save(dst_path, quality=quality)

            return True
        except Exception:
            return False

    def _add_watermark(self, img: Image.Image, text: str, opacity: int) -> Image.Image:
        width, height = img.size
        watermark = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(watermark)

        try:
            font_size = max(int(min(width, height) * 0.04), 12)
            font = ImageFont.truetype("arial.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        x = width - text_width - 20
        y = height - text_height - 20

        alpha = int(255 * opacity / 100)
        draw.text((x, y), text, font=font, fill=(255, 255, 255, alpha))

        result = Image.alpha_composite(img.convert('RGBA'), watermark)
        return result

    def get_image_size(self, src_path: Path) -> Optional[Tuple[int, int]]:
        try:
            with Image.open(src_path) as img:
                return img.size
        except Exception:
            return None

    def is_valid_image(self, src_path: Path) -> bool:
        try:
            with Image.open(src_path) as img:
                img.verify()
            return True
        except Exception:
            return False
