import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Tuple
from .config import AppConfig


@dataclass
class RulesConfig:
    thumbnail_width: int = 800
    thumbnail_height: int = 600
    watermark_text: str = "摄影工作室"
    watermark_enabled: bool = True
    watermark_opacity: int = 50
    max_selection: int = 50
    naming_pattern: str = "{client}_{date}_{index:04d}"
    expire_days: int = 30
    expire_enabled: bool = True
    include_raw: bool = False
    output_format: str = "jpg"
    jpeg_quality: int = 90

    @property
    def thumbnail_size(self) -> Tuple[int, int]:
        return (self.thumbnail_width, self.thumbnail_height)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'RulesConfig':
        config = cls()
        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
        return config

    def save_to_file(self, filepath: str):
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load_from_file(cls, filepath: str) -> 'RulesConfig':
        path = Path(filepath)
        if not path.exists():
            return cls()
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)

    def apply_defaults(self):
        self.thumbnail_width = AppConfig.DEFAULT_THUMBNAIL_SIZE[0]
        self.thumbnail_height = AppConfig.DEFAULT_THUMBNAIL_SIZE[1]
        self.watermark_text = AppConfig.DEFAULT_WATERMARK_TEXT
        self.max_selection = AppConfig.DEFAULT_MAX_SELECTION
        self.naming_pattern = AppConfig.DEFAULT_NAMING_PATTERN
        self.expire_days = AppConfig.DEFAULT_EXPIRE_DAYS
        self.watermark_opacity = 50
        self.jpeg_quality = AppConfig.JPEG_QUALITY
