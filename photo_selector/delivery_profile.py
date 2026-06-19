import os
import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Dict, Optional
from enum import Enum


class ClientType(Enum):
    PERSONAL = "个人写真"
    WEDDING = "婚纱摄影"
    FAMILY = "家庭合影"
    COMMERCIAL = "商业摄影"
    EVENT = "活动跟拍"
    CUSTOM = "自定义"


@dataclass
class DeliveryProfile:
    profile_id: str = ""
    name: str = ""
    client_type: str = "个人写真"
    output_dir: str = ""
    naming_pattern: str = "{client}_{date}_{index:04d}"
    make_zip: bool = True
    expire_days: int = 30
    expire_enabled: bool = True
    include_raw: bool = False
    output_format: str = "jpg"
    thumbnail_width: int = 800
    thumbnail_height: int = 600
    watermark_text: str = "摄影工作室"
    watermark_enabled: bool = True
    watermark_opacity: int = 50
    max_selection: int = 50
    jpeg_quality: int = 90
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'DeliveryProfile':
        profile = cls()
        for key, value in data.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        if not profile.profile_id:
            profile.profile_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        return profile

    def apply_to_rules(self, rules):
        rules.naming_pattern = self.naming_pattern
        rules.expire_days = self.expire_days
        rules.expire_enabled = self.expire_enabled
        rules.include_raw = self.include_raw
        rules.output_format = self.output_format
        rules.thumbnail_width = self.thumbnail_width
        rules.thumbnail_height = self.thumbnail_height
        rules.watermark_text = self.watermark_text
        rules.watermark_enabled = self.watermark_enabled
        rules.watermark_opacity = self.watermark_opacity
        rules.max_selection = self.max_selection
        rules.jpeg_quality = self.jpeg_quality

    @classmethod
    def from_rules(cls, rules, name: str = "", client_type: str = "个人写真") -> 'DeliveryProfile':
        now = datetime.now()
        return cls(
            profile_id=now.strftime("%Y%m%d_%H%M%S"),
            name=name or f"方案_{now.strftime('%Y%m%d')}",
            client_type=client_type,
            output_dir="",
            naming_pattern=rules.naming_pattern,
            make_zip=True,
            expire_days=rules.expire_days,
            expire_enabled=rules.expire_enabled,
            include_raw=rules.include_raw,
            output_format=rules.output_format,
            thumbnail_width=rules.thumbnail_width,
            thumbnail_height=rules.thumbnail_height,
            watermark_text=rules.watermark_text,
            watermark_enabled=rules.watermark_enabled,
            watermark_opacity=rules.watermark_opacity,
            max_selection=rules.max_selection,
            jpeg_quality=rules.jpeg_quality,
            created_at=now.strftime("%Y-%m-%d %H:%M:%S"),
            updated_at=now.strftime("%Y-%m-%d %H:%M:%S")
        )

    def get_summary(self) -> str:
        lines = []
        lines.append(f"命名模板: {self.naming_pattern}")
        lines.append(f"输出格式: {self.output_format}")
        lines.append(f"缩略图: {self.thumbnail_width}×{self.thumbnail_height}")
        if self.watermark_enabled:
            lines.append(f"水印: {self.watermark_text} (透明度{self.watermark_opacity}%)")
        else:
            lines.append("水印: 关闭")
        if self.expire_enabled:
            lines.append(f"过期: {self.expire_days} 天后")
        else:
            lines.append("过期: 关闭")
        lines.append(f"入选上限: {self.max_selection} 张")
        lines.append(f"压缩包: {'生成' if self.make_zip else '不生成'}")
        return "\n".join(lines)


class DeliveryProfileManager:
    def __init__(self):
        self.profiles: List[DeliveryProfile] = []
        self.profile_dir: Optional[Path] = None

    def set_profile_directory(self, dir_path: str):
        self.profile_dir = Path(dir_path)
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._load_from_disk()

    def _ensure_defaults(self):
        if not self.profiles:
            defaults = [
                DeliveryProfile(
                    profile_id="default_personal",
                    name="个人写真标准方案",
                    client_type="个人写真",
                    output_dir="",
                    naming_pattern="{client}_{date}_{index:04d}",
                    make_zip=True,
                    expire_days=15,
                    expire_enabled=True,
                    thumbnail_width=1024,
                    thumbnail_height=768,
                    max_selection=30,
                    created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ),
                DeliveryProfile(
                    profile_id="default_wedding",
                    name="婚纱摄影精选方案",
                    client_type="婚纱摄影",
                    output_dir="",
                    naming_pattern="婚纱_{client}_{date}_{index:04d}",
                    make_zip=True,
                    expire_days=30,
                    expire_enabled=True,
                    thumbnail_width=1200,
                    thumbnail_height=800,
                    max_selection=80,
                    watermark_text="婚礼摄影",
                    created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ),
                DeliveryProfile(
                    profile_id="default_family",
                    name="家庭合影温馨方案",
                    client_type="家庭合影",
                    output_dir="",
                    naming_pattern="家庭_{date}_{index:04d}",
                    make_zip=True,
                    expire_days=20,
                    expire_enabled=True,
                    watermark_text="",
                    watermark_enabled=False,
                    max_selection=40,
                    created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ),
            ]
            self.profiles.extend(defaults)
            for p in defaults:
                self._save_profile(p)

    def _load_from_disk(self):
        if not self.profile_dir or not self.profile_dir.exists():
            return
        self.profiles = []
        for file in sorted(self.profile_dir.glob("*.json")):
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                profile = DeliveryProfile.from_dict(data)
                self.profiles.append(profile)
            except Exception:
                pass
        self._ensure_defaults()

    def _save_profile(self, profile: DeliveryProfile):
        if not self.profile_dir:
            return
        profile.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        filename = f"{profile.profile_id}.json"
        path = self.profile_dir / filename
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(profile.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add_profile(self, profile: DeliveryProfile) -> DeliveryProfile:
        if not profile.profile_id:
            profile.profile_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        if not profile.created_at:
            profile.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        profile.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.profiles.append(profile)
        self._save_profile(profile)
        return profile

    def update_profile(self, profile: DeliveryProfile) -> bool:
        for i, p in enumerate(self.profiles):
            if p.profile_id == profile.profile_id:
                profile.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.profiles[i] = profile
                self._save_profile(profile)
                return True
        return False

    def delete_profile(self, profile_id: str) -> bool:
        for i, p in enumerate(self.profiles):
            if p.profile_id == profile_id:
                del self.profiles[i]
                if self.profile_dir:
                    try:
                        (self.profile_dir / f"{profile_id}.json").unlink()
                    except Exception:
                        pass
                return True
        return False

    def get_profile(self, profile_id: str) -> Optional[DeliveryProfile]:
        for p in self.profiles:
            if p.profile_id == profile_id:
                return p
        return None

    def get_profiles_by_type(self, client_type: str) -> List[DeliveryProfile]:
        return [p for p in self.profiles if p.client_type == client_type]

    def get_all_types(self) -> List[str]:
        return [t.value for t in ClientType]

    def get_all_profile_names(self) -> List[tuple]:
        return [(p.profile_id, p.name, p.client_type) for p in self.profiles]
