import os
import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Dict, Optional


@dataclass
class BatchProjectResult:
    project_name: str = ""
    client_name: str = ""
    shoot_date: str = ""
    status: str = "success"
    total_photos: int = 0
    processed: int = 0
    skipped: int = 0
    failed: int = 0
    skip_reasons: Dict[str, int] = field(default_factory=dict)
    failed_files: List[dict] = field(default_factory=list)
    package_path: str = ""
    error_message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'BatchProjectResult':
        result = cls()
        for key, value in data.items():
            if hasattr(result, key):
                setattr(result, key, value)
        return result

    def get_summary(self) -> str:
        lines = []
        lines.append(f"项目: {self.project_name}")
        lines.append(f"状态: {'成功' if self.status == 'success' else '失败'}")
        lines.append(f"照片: {self.total_photos} 张")
        lines.append(f"成功: {self.processed} 张")
        lines.append(f"跳过: {self.skipped} 张")
        lines.append(f"失败: {self.failed} 张")
        if self.package_path:
            lines.append(f"输出: {self.package_path}")
        if self.error_message:
            lines.append(f"错误: {self.error_message}")
        return "\n".join(lines)


@dataclass
class BatchRecord:
    batch_id: str = ""
    profile_id: str = ""
    profile_name: str = ""
    output_dir: str = ""
    make_zip: bool = True
    timestamp: str = ""
    start_time: str = ""
    end_time: str = ""
    status: str = "completed"
    total_projects: int = 0
    completed_projects: int = 0
    failed_projects: int = 0
    skipped_projects: int = 0
    total_photos: int = 0
    total_processed: int = 0
    total_skipped: int = 0
    total_failed: int = 0
    project_results: List[BatchProjectResult] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        data["project_results"] = [r.to_dict() for r in self.project_results]
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'BatchRecord':
        record = cls()
        for key, value in data.items():
            if key == "project_results":
                record.project_results = [BatchProjectResult.from_dict(r) for r in value]
            elif hasattr(record, key):
                setattr(record, key, value)
        return record

    def add_project_result(self, result: BatchProjectResult):
        self.project_results.append(result)
        self.total_projects += 1
        if result.status == "success":
            self.completed_projects += 1
        elif result.status == "failed":
            self.failed_projects += 1
        elif result.status == "skipped":
            self.skipped_projects += 1
        self.total_photos += result.total_photos
        self.total_processed += result.processed
        self.total_skipped += result.skipped
        self.total_failed += result.failed

    def calculate_duration(self) -> str:
        if not self.start_time or not self.end_time:
            return ""
        try:
            start = datetime.strptime(self.start_time, "%Y-%m-%d %H:%M:%S")
            end = datetime.strptime(self.end_time, "%Y-%m-%d %H:%M:%S")
            delta = end - start
            seconds = int(delta.total_seconds())
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            secs = seconds % 60
            if hours > 0:
                return f"{hours}小时{minutes}分{secs}秒"
            elif minutes > 0:
                return f"{minutes}分{secs}秒"
            else:
                return f"{secs}秒"
        except Exception:
            return ""

    def get_summary(self) -> str:
        lines = []
        lines.append(f"批次号: {self.batch_id}")
        lines.append(f"时间: {self.timestamp}")
        lines.append(f"方案: {self.profile_name}")
        lines.append(f"输出目录: {self.output_dir}")
        lines.append(f"总项目数: {self.total_projects}")
        lines.append(f"成功: {self.completed_projects} 个")
        lines.append(f"失败: {self.failed_projects} 个")
        if self.skipped_projects > 0:
            lines.append(f"跳过: {self.skipped_projects} 个")
        lines.append(f"总照片数: {self.total_photos} 张")
        lines.append(f"成功处理: {self.total_processed} 张")
        lines.append(f"跳过: {self.total_skipped} 张")
        lines.append(f"失败: {self.total_failed} 张")
        duration = self.calculate_duration()
        if duration:
            lines.append(f"耗时: {duration}")
        return "\n".join(lines)

    def get_report_text(self) -> str:
        lines = []
        lines.append("=" * 60)
        lines.append("批量交付报告")
        lines.append("=" * 60)
        lines.append("")
        lines.append(self.get_summary())
        lines.append("")
        lines.append("-" * 60)
        lines.append("各项目详情")
        lines.append("-" * 60)
        lines.append("")

        for i, pr in enumerate(self.project_results, 1):
            lines.append(f"[{i}] {pr.project_name}")
            lines.append(f"    状态: {'✓ 成功' if pr.status == 'success' else '✗ 失败'}")
            lines.append(f"    统计: {pr.processed} 成功 / {pr.skipped} 跳过 / {pr.failed} 失败 / {pr.total_photos} 总计")
            if pr.package_path:
                lines.append(f"    输出: {pr.package_path}")
            if pr.error_message:
                lines.append(f"    错误: {pr.error_message}")

            if pr.skip_reasons:
                lines.append(f"    跳过原因:")
                for reason, count in pr.skip_reasons.items():
                    lines.append(f"      • {reason}: {count} 个")

            if pr.failed_files:
                lines.append(f"    失败文件:")
                for f in pr.failed_files:
                    lines.append(f"      ❌ {f.get('filename', '?')}: {f.get('error', '?')}")

            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)


class BatchHistory:
    def __init__(self):
        self.records: List[BatchRecord] = []
        self.history_dir: Optional[Path] = None

    def set_history_directory(self, dir_path: str):
        self.history_dir = Path(dir_path)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self._load_from_disk()

    def _load_from_disk(self):
        if not self.history_dir or not self.history_dir.exists():
            return
        self.records = []
        for file in sorted(self.history_dir.glob("batch_*.json"), reverse=True):
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                record = BatchRecord.from_dict(data)
                self.records.append(record)
            except Exception:
                pass

    def _save_record(self, record: BatchRecord):
        if not self.history_dir:
            return
        filename = f"batch_{record.batch_id}.json"
        path = self.history_dir / filename
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(record.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add_record(self, record: BatchRecord):
        self.records.insert(0, record)
        self._save_record(record)

    def create_record_from_batch(
        self,
        batch_id: str,
        profile_name: str,
        output_dir: str,
        make_zip: bool,
        start_time: str,
        project_results: List[BatchProjectResult],
        status: str = "completed",
        notes: str = ""
    ) -> BatchRecord:
        now = datetime.now()
        record = BatchRecord(
            batch_id=batch_id,
            profile_name=profile_name,
            output_dir=output_dir,
            make_zip=make_zip,
            timestamp=now.strftime("%Y-%m-%d %H:%M:%S"),
            start_time=start_time,
            end_time=now.strftime("%Y-%m-%d %H:%M:%S"),
            status=status,
            notes=notes
        )
        for pr in project_results:
            record.add_project_result(pr)
        self.add_record(record)
        return record

    def get_record(self, batch_id: str) -> Optional[BatchRecord]:
        for r in self.records:
            if r.batch_id == batch_id:
                return r
        return None

    def get_records_by_date_range(self, start_date: str, end_date: str) -> List[BatchRecord]:
        return [
            r for r in self.records
            if start_date <= r.timestamp[:10] <= end_date
        ]

    def get_all_batch_ids(self) -> List[str]:
        return [r.batch_id for r in self.records]

    def delete_record(self, batch_id: str) -> bool:
        for i, r in enumerate(self.records):
            if r.batch_id == batch_id:
                del self.records[i]
                if self.history_dir:
                    try:
                        (self.history_dir / f"batch_{batch_id}.json").unlink()
                    except Exception:
                        pass
                return True
        return False
