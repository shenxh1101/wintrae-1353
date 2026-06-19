import os
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime
from .config import AppConfig


@dataclass
class PhotoItem:
    path: Path
    filename: str
    size: int
    created_time: datetime
    modified_time: datetime
    is_selected: bool = False


@dataclass
class ProjectItem:
    name: str
    source_dir: Optional[Path] = None
    client_name: str = ""
    shoot_date: str = ""
    photos: List[PhotoItem] = field(default_factory=list)
    cover_path: Optional[Path] = None

    @property
    def photo_count(self):
        return len(self.photos)

    @property
    def total_size(self):
        return sum(p.size for p in self.photos)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "source_dir": str(self.source_dir) if self.source_dir else "",
            "client_name": self.client_name,
            "shoot_date": self.shoot_date,
            "cover_path": str(self.cover_path) if self.cover_path else "",
            "photos": [
                {
                    "path": str(p.path),
                    "filename": p.filename,
                    "size": p.size,
                    "created_time": p.created_time.strftime("%Y-%m-%d %H:%M:%S") if isinstance(p.created_time, datetime) else str(p.created_time),
                    "modified_time": p.modified_time.strftime("%Y-%m-%d %H:%M:%S") if isinstance(p.modified_time, datetime) else str(p.modified_time),
                    "is_selected": p.is_selected,
                }
                for p in self.photos
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ProjectItem':
        project = cls(
            name=data.get("name", ""),
            source_dir=Path(data["source_dir"]) if data.get("source_dir") else None,
            client_name=data.get("client_name", ""),
            shoot_date=data.get("shoot_date", ""),
            cover_path=Path(data["cover_path"]) if data.get("cover_path") else None,
        )
        for p_data in data.get("photos", []):
            try:
                ct = datetime.strptime(p_data["created_time"], "%Y-%m-%d %H:%M:%S") if isinstance(p_data.get("created_time"), str) else p_data.get("created_time")
                mt = datetime.strptime(p_data["modified_time"], "%Y-%m-%d %H:%M:%S") if isinstance(p_data.get("modified_time"), str) else p_data.get("modified_time")
            except Exception:
                ct = datetime.now()
                mt = datetime.now()
            project.photos.append(PhotoItem(
                path=Path(p_data["path"]),
                filename=p_data.get("filename", ""),
                size=p_data.get("size", 0),
                created_time=ct,
                modified_time=mt,
                is_selected=p_data.get("is_selected", False),
            ))
        return project


class FileScanner:
    def __init__(self):
        self.source_dir: Optional[Path] = None
        self.projects: List[ProjectItem] = []
        self.recognize_mode = "prefix"

    def set_source_directory(self, dir_path: str):
        self.source_dir = Path(dir_path)
        if not self.source_dir.exists():
            raise FileNotFoundError(f"目录不存在: {dir_path}")

    def set_recognize_mode(self, mode: str):
        self.recognize_mode = mode

    def scan(self) -> List[ProjectItem]:
        if not self.source_dir:
            raise ValueError("请先设置源目录")

        self.projects = []
        all_photos = self._scan_photos(self.source_dir)

        if self.recognize_mode == "date":
            self.projects = self._group_by_date(all_photos)
        elif self.recognize_mode == "client":
            self.projects = self._group_by_client(all_photos)
        else:
            self.projects = self._group_by_prefix(all_photos)

        for project in self.projects:
            if project.photos:
                project.cover_path = project.photos[0].path

        return self.projects

    def _scan_photos(self, directory: Path) -> List[PhotoItem]:
        photos = []
        exts = AppConfig.SUPPORTED_IMAGE_EXTENSIONS | AppConfig.SUPPORTED_RAW_EXTENSIONS

        for root, _, files in os.walk(directory):
            for filename in files:
                ext = Path(filename).suffix.lower()
                if ext in exts:
                    filepath = Path(root) / filename
                    stat = filepath.stat()
                    photo = PhotoItem(
                        path=filepath,
                        filename=filename,
                        size=stat.st_size,
                        created_time=datetime.fromtimestamp(stat.st_ctime),
                        modified_time=datetime.fromtimestamp(stat.st_mtime)
                    )
                    photos.append(photo)

        photos.sort(key=lambda p: p.filename)
        return photos

    def _group_by_date(self, photos: List[PhotoItem]) -> List[ProjectItem]:
        groups: Dict[str, List[PhotoItem]] = {}

        for photo in photos:
            date_str = photo.modified_time.strftime("%Y-%m-%d")
            if date_str not in groups:
                groups[date_str] = []
            groups[date_str].append(photo)

        projects = []
        for date_str, photo_list in sorted(groups.items()):
            project = ProjectItem(
                name=date_str,
                source_dir=self.source_dir,
                shoot_date=date_str,
                photos=photo_list
            )
            projects.append(project)

        return projects

    def _group_by_client(self, photos: List[PhotoItem]) -> List[ProjectItem]:
        groups: Dict[str, List[PhotoItem]] = {}
        pattern = re.compile(r'^([A-Za-z\u4e00-\u9fa5]+)[_\-\s]')

        for photo in photos:
            match = pattern.match(photo.filename)
            if match:
                client = match.group(1)
            else:
                client = "未分类"

            if client not in groups:
                groups[client] = []
            groups[client].append(photo)

        projects = []
        for client, photo_list in sorted(groups.items()):
            dates = set(p.modified_time.strftime("%Y-%m-%d") for p in photo_list)
            shoot_date = sorted(dates)[0] if dates else ""

            project = ProjectItem(
                name=client,
                source_dir=self.source_dir,
                client_name=client,
                shoot_date=shoot_date,
                photos=photo_list
            )
            projects.append(project)

        return projects

    def _group_by_prefix(self, photos: List[PhotoItem]) -> List[ProjectItem]:
        groups: Dict[str, List[PhotoItem]] = {}

        for photo in photos:
            stem = photo.path.stem
            prefix_parts = re.split(r'[_\-\s]', stem)
            if prefix_parts and prefix_parts[0]:
                prefix = prefix_parts[0]
            else:
                prefix = "未分类"

            if prefix not in groups:
                groups[prefix] = []
            groups[prefix].append(photo)

        projects = []
        for prefix, photo_list in sorted(groups.items()):
            dates = set(p.modified_time.strftime("%Y-%m-%d") for p in photo_list)
            shoot_date = sorted(dates)[0] if dates else ""

            project = ProjectItem(
                name=prefix,
                source_dir=self.source_dir,
                shoot_date=shoot_date,
                photos=photo_list
            )
            projects.append(project)

        return projects

    def get_project_by_name(self, name: str) -> Optional[ProjectItem]:
        for project in self.projects:
            if project.name == name:
                return project
        return None

    def rescan_project(self, source_dir: str, project_name: str) -> Optional[ProjectItem]:
        old_source = self.source_dir
        try:
            self.set_source_directory(source_dir)
            all_photos = self._scan_photos(self.source_dir)

            if not all_photos:
                return None

            project = None
            for mode_func in [self._group_by_prefix, self._group_by_client, self._group_by_date]:
                test_projects = mode_func(all_photos)
                for p in test_projects:
                    if p.name == project_name:
                        project = p
                        break
                if project:
                    break

            if not project:
                project = ProjectItem(
                    name=project_name,
                    source_dir=self.source_dir,
                    photos=all_photos
                )
                dates = set(p.modified_time.strftime("%Y-%m-%d") for p in all_photos)
                project.shoot_date = sorted(dates)[0] if dates else ""

            if project.photos:
                project.cover_path = project.photos[0].path

            return project
        except Exception:
            return None
        finally:
            self.source_dir = old_source
