import os
import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Dict, Optional
from enum import Enum


class LogLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"


class LogType(Enum):
    SCAN = "scan"
    PROCESS = "process"
    SKIP = "skip"
    PACKAGE = "package"
    SYSTEM = "system"


@dataclass
class LogEntry:
    timestamp: str
    level: str
    type: str
    message: str
    details: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PackageRecord:
    record_id: str
    project_name: str
    client_name: str
    shoot_date: str
    package_path: str
    timestamp: str
    status: str = "success"
    total_photos: int = 0
    processed: int = 0
    skipped: int = 0
    failed: int = 0
    skip_reasons: Dict[str, int] = field(default_factory=dict)
    failed_files: List[dict] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProcessingStats:
    total_files: int = 0
    processed_files: int = 0
    skipped_files: int = 0
    failed_files: int = 0
    skip_reasons: Dict[str, int] = field(default_factory=dict)
    failed_files_list: List[dict] = field(default_factory=list)
    start_time: Optional[str] = None
    end_time: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class Logger:
    def __init__(self):
        self.entries: List[LogEntry] = []
        self.stats = ProcessingStats()
        self.log_dir: Optional[Path] = None
        self.auto_save = True

    def set_log_directory(self, dir_path: str):
        self.log_dir = Path(dir_path)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def reset_stats(self):
        self.stats = ProcessingStats()
        self.stats.start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def add_log(self, level: LogLevel, log_type: LogType, message: str, details: Dict = None):
        entry = LogEntry(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            level=level.value,
            type=log_type.value,
            message=message,
            details=details or {}
        )
        self.entries.append(entry)

    def log_scan(self, message: str, details: Dict = None):
        self.add_log(LogLevel.INFO, LogType.SCAN, message, details)

    def log_process(self, message: str, details: Dict = None):
        self.add_log(LogLevel.INFO, LogType.PROCESS, message, details)

    def log_skip(self, reason: str, filename: str, details: Dict = None):
        full_details = {"filename": filename, "reason": reason}
        if details:
            full_details.update(details)
        self.add_log(LogLevel.WARNING, LogType.SKIP, f"跳过文件: {filename} - {reason}", full_details)
        self.stats.skipped_files += 1
        self.stats.skip_reasons[reason] = self.stats.skip_reasons.get(reason, 0) + 1

    def log_failure(self, filename: str, error: str, details: Dict = None):
        full_details = {"filename": filename, "error": error}
        if details:
            full_details.update(details)
        self.add_log(LogLevel.ERROR, LogType.PROCESS, f"处理失败: {filename} - {error}", full_details)
        self.stats.failed_files += 1
        self.stats.failed_files_list.append({
            "filename": filename,
            "error": error,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    def log_success(self, message: str, details: Dict = None):
        self.add_log(LogLevel.SUCCESS, LogType.PACKAGE, message, details)

    def log_system(self, message: str, details: Dict = None):
        self.add_log(LogLevel.INFO, LogType.SYSTEM, message, details)

    def increment_processed(self):
        self.stats.processed_files += 1

    def finish_processing(self):
        self.stats.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if self.auto_save and self.log_dir:
            self.save_logs()

    def save_logs(self) -> Optional[Path]:
        if not self.log_dir:
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self.log_dir / f"log_{timestamp}.json"
        summary_file = self.log_dir / f"summary_{timestamp}.txt"

        log_data = {
            "summary": self.stats.to_dict(),
            "entries": [e.to_dict() for e in self.entries]
        }

        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)

        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(self._generate_summary_text())

        return log_file

    def _generate_summary_text(self) -> str:
        lines = []
        lines.append("=" * 60)
        lines.append("处理日志汇总")
        lines.append("=" * 60)
        lines.append(f"开始时间: {self.stats.start_time}")
        lines.append(f"结束时间: {self.stats.end_time}")
        lines.append("")
        lines.append(f"文件总数: {self.stats.total_files}")
        lines.append(f"成功处理: {self.stats.processed_files}")
        lines.append(f"跳过文件: {self.stats.skipped_files}")
        lines.append(f"失败文件: {self.stats.failed_files}")
        lines.append("")

        if self.stats.skip_reasons:
            lines.append("跳过原因统计:")
            for reason, count in self.stats.skip_reasons.items():
                lines.append(f"  - {reason}: {count} 个文件")
            lines.append("")

        if self.stats.failed_files_list:
            lines.append("失败文件列表:")
            for item in self.stats.failed_files_list:
                lines.append(f"  - {item['filename']}: {item['error']}")
            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)

    def get_logs_by_type(self, log_type: LogType) -> List[LogEntry]:
        return [e for e in self.entries if e.type == log_type.value]

    def get_logs_by_level(self, level: LogLevel) -> List[LogEntry]:
        return [e for e in self.entries if e.level == level.value]


class PackageHistory:
    def __init__(self):
        self.records: List[PackageRecord] = []
        self.history_dir: Optional[Path] = None

    def set_history_directory(self, dir_path: str):
        self.history_dir = Path(dir_path)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self._load_from_disk()

    def add_record(self, record: PackageRecord):
        self.records.append(record)
        self._save_record(record)

    def create_record_from_stats(
        self,
        project_name: str,
        client_name: str,
        shoot_date: str,
        package_path: str,
        stats: ProcessingStats,
        status: str = "success"
    ) -> PackageRecord:
        now = datetime.now()
        record = PackageRecord(
            record_id=now.strftime("%Y%m%d_%H%M%S_") + project_name,
            project_name=project_name,
            client_name=client_name,
            shoot_date=shoot_date,
            package_path=package_path,
            timestamp=now.strftime("%Y-%m-%d %H:%M:%S"),
            status=status,
            total_photos=stats.total_files,
            processed=stats.processed_files,
            skipped=stats.skipped_files,
            failed=stats.failed_files,
            skip_reasons=dict(stats.skip_reasons),
            failed_files=list(stats.failed_files_list)
        )
        self.add_record(record)
        return record

    def get_records_by_project(self, project_name: str) -> List[PackageRecord]:
        return [r for r in self.records if r.project_name == project_name]

    def get_all_projects(self) -> List[str]:
        projects = set()
        for r in self.records:
            projects.add(r.project_name)
        return sorted(projects)

    def get_records_by_date_range(self, start_date: str, end_date: str) -> List[PackageRecord]:
        return [
            r for r in self.records
            if start_date <= r.timestamp[:10] <= end_date
        ]

    def _save_record(self, record: PackageRecord):
        if not self.history_dir:
            return
        filename = f"{record.record_id}.json"
        path = self.history_dir / filename
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(record.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_from_disk(self):
        if not self.history_dir or not self.history_dir.exists():
            return
        self.records = []
        for file in sorted(self.history_dir.glob("*.json")):
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                record = PackageRecord(**data)
                self.records.append(record)
            except Exception:
                pass
        self.records.sort(key=lambda r: r.timestamp, reverse=True)
