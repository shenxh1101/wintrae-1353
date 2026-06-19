import os
import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Dict, Optional, Any
from enum import Enum


class TaskStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"
    SKIPPED = "skipped"


@dataclass
class ProjectSummary:
    project_name: str = ""
    photo_count: int = 0
    client_name: str = ""
    shoot_date: str = ""
    total_size_mb: float = 0.0
    cover_path: str = ""
    source_dir: str = ""
    raw_count: int = 0
    corrupted_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'ProjectSummary':
        summary = cls()
        for key, value in data.items():
            if hasattr(summary, key):
                setattr(summary, key, value)
        return summary


@dataclass
class QueueTask:
    task_id: str = ""
    project_summary: Optional[ProjectSummary] = None
    profile_id: str = ""
    profile_name: str = ""
    output_dir: str = ""
    make_zip: bool = True
    status: str = "pending"
    order: int = 0
    error_message: str = ""
    stats: Dict = field(default_factory=dict)
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        if self.project_summary:
            data["project_summary"] = self.project_summary.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'QueueTask':
        task = cls()
        for key, value in data.items():
            if key == "project_summary" and value:
                task.project_summary = ProjectSummary.from_dict(value)
            elif hasattr(task, key):
                setattr(task, key, value)
        return task

    def get_confirmation_text(self) -> str:
        if not self.project_summary:
            return ""
        s = self.project_summary
        lines = []
        lines.append(f"项目: {s.project_name}")
        lines.append(f"照片: {s.photo_count} 张 ({s.total_size_mb:.1f} MB)")
        if s.client_name:
            lines.append(f"客户: {s.client_name}")
        if s.shoot_date:
            lines.append(f"拍摄日期: {s.shoot_date}")
        if s.raw_count > 0:
            lines.append(f"RAW文件: {s.raw_count} 个")
        if s.corrupted_count > 0:
            lines.append(f"⚠️ 可能损坏: {s.corrupted_count} 个")
        lines.append(f"方案: {self.profile_name}")
        lines.append(f"输出: {self.output_dir}")
        lines.append(f"压缩包: {'是' if self.make_zip else '否'}")
        return "\n".join(lines)


class TaskQueue:
    def __init__(self):
        self.tasks: List[QueueTask] = []
        self.queue_dir: Optional[Path] = None
        self.current_batch_id: str = ""

    def set_queue_directory(self, dir_path: str):
        self.queue_dir = Path(dir_path)
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self._load_from_disk()

    def _load_from_disk(self):
        if not self.queue_dir or not self.queue_dir.exists():
            return
        queue_file = self.queue_dir / "task_queue.json"
        if queue_file.exists():
            try:
                with open(queue_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.tasks = [QueueTask.from_dict(t) for t in data.get("tasks", [])]
                self.current_batch_id = data.get("current_batch_id", "")
            except Exception:
                pass
        self._cleanup_completed_old()

    def _save_to_disk(self):
        if not self.queue_dir:
            return
        queue_file = self.queue_dir / "task_queue.json"
        try:
            with open(queue_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "tasks": [t.to_dict() for t in self.tasks],
                    "current_batch_id": self.current_batch_id,
                    "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _cleanup_completed_old(self):
        cutoff = datetime.now().timestamp() - 7 * 24 * 3600
        to_keep = []
        for task in self.tasks:
            if task.status in {"completed", "failed"} and task.finished_at:
                try:
                    ft = datetime.strptime(task.finished_at, "%Y-%m-%d %H:%M:%S")
                    if ft.timestamp() > cutoff:
                        to_keep.append(task)
                except Exception:
                    to_keep.append(task)
            else:
                to_keep.append(task)
        if len(to_keep) != len(self.tasks):
            self.tasks = to_keep
            self._save_to_disk()

    def start_new_batch(self) -> str:
        self.current_batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._save_to_disk()
        return self.current_batch_id

    def add_task(self, task: QueueTask) -> str:
        if not task.task_id:
            task.task_id = datetime.now().strftime("%Y%m%d_%H%M%S_") + str(len(self.tasks)).zfill(3)
        if not task.created_at:
            task.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if task.order == 0:
            max_order = max((t.order for t in self.tasks), default=0)
            task.order = max_order + 1
        self.tasks.append(task)
        self._save_to_disk()
        return task.task_id

    def add_tasks(self, tasks: List[QueueTask]) -> List[str]:
        ids = []
        for t in tasks:
            ids.append(self.add_task(t))
        return ids

    def get_task(self, task_id: str) -> Optional[QueueTask]:
        for t in self.tasks:
            if t.task_id == task_id:
                return t
        return None

    def get_tasks_by_status(self, status: str) -> List[QueueTask]:
        return [t for t in self.tasks if t.status == status]

    def get_pending_tasks(self) -> List[QueueTask]:
        return [t for t in self.tasks if t.status in {"pending", "confirmed", "stopped"}]

    def get_unconfirmed_tasks(self) -> List[QueueTask]:
        return [t for t in self.tasks if t.status == "pending"]

    def get_confirmed_tasks(self) -> List[QueueTask]:
        return [t for t in self.tasks if t.status == "confirmed"]

    def get_incomplete_tasks(self) -> List[QueueTask]:
        return sorted(
            [t for t in self.tasks if t.status in {"pending", "confirmed", "stopped", "processing"}],
            key=lambda t: t.order
        )

    def update_task_status(self, task_id: str, status: str, **kwargs) -> bool:
        task = self.get_task(task_id)
        if not task:
            return False
        task.status = status
        if status == "processing":
            task.started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if status in {"completed", "failed", "stopped"}:
            task.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)
        self._save_to_disk()
        return True

    def confirm_task(self, task_id: str) -> bool:
        return self.update_task_status(task_id, "confirmed")

    def confirm_all_pending(self) -> int:
        count = 0
        for t in self.get_unconfirmed_tasks():
            if self.confirm_task(t.task_id):
                count += 1
        return count

    def remove_task(self, task_id: str) -> bool:
        for i, t in enumerate(self.tasks):
            if t.task_id == task_id:
                del self.tasks[i]
                self._save_to_disk()
                return True
        return False

    def clear_completed(self) -> int:
        to_remove = [t.task_id for t in self.tasks if t.status in {"completed", "failed"}]
        for tid in to_remove:
            self.remove_task(tid)
        return len(to_remove)

    def clear_all(self) -> int:
        count = len(self.tasks)
        self.tasks = []
        self._save_to_disk()
        return count

    def reorder_task(self, task_id: str, new_order: int) -> bool:
        task = self.get_task(task_id)
        if not task:
            return False
        old_order = task.order
        if old_order == new_order:
            return True
        for t in self.tasks:
            if old_order < new_order:
                if old_order < t.order <= new_order:
                    t.order -= 1
            else:
                if new_order <= t.order < old_order:
                    t.order += 1
        task.order = new_order
        self._save_to_disk()
        return True

    def get_next_task(self) -> Optional[QueueTask]:
        pending = [t for t in self.tasks if t.status == "confirmed"]
        if not pending:
            return None
        return sorted(pending, key=lambda t: t.order)[0]

    def get_batch_tasks(self, batch_id: str) -> List[QueueTask]:
        return [t for t in self.tasks if t.task_id.startswith(batch_id)]

    def get_current_batch_tasks(self) -> List[QueueTask]:
        if not self.current_batch_id:
            return []
        return self.get_batch_tasks(self.current_batch_id)

    def has_incomplete(self) -> bool:
        return any(t.status in {"pending", "confirmed", "stopped", "processing"} for t in self.tasks)

    def get_stats(self) -> Dict[str, int]:
        stats = {"total": len(self.tasks)}
        for s in ["pending", "confirmed", "processing", "completed", "failed", "stopped"]:
            stats[s] = sum(1 for t in self.tasks if t.status == s)
        return stats
