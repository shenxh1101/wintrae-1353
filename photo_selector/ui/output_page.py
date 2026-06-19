import os
from pathlib import Path
from datetime import datetime, timedelta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QFileDialog, QGroupBox, QCheckBox, QProgressBar, QMessageBox,
    QListWidget, QListWidgetItem, QTextEdit, QSplitter, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QInputDialog
)
from PySide6.QtCore import Signal, Qt, QThread
from PySide6.QtGui import QColor

from ..scanner import FileScanner, ProjectItem
from ..rules import RulesConfig
from ..packager import PackageGenerator
from ..logger import Logger, PackageHistory, ProcessingStats
from ..image_processor import ImageProcessor
from ..delivery_profile import DeliveryProfile, DeliveryProfileManager, ClientType
from ..task_queue import TaskQueue, QueueTask, ProjectSummary, TaskStatus
from ..batch_record import BatchHistory, BatchRecord, BatchProjectResult


class BatchPackageThread(QThread):
    progress = Signal(int, str)
    project_progress = Signal(int, int, str)
    project_finished = Signal(str, dict)
    all_finished = Signal(list, str, str)
    error = Signal(str)
    task_started = Signal(str)

    def __init__(
        self,
        packager: PackageGenerator,
        history: PackageHistory,
        batch_history: BatchHistory,
        task_queue: TaskQueue,
        scanner: FileScanner,
        task_ids: list,
        output_dir: str,
        make_zip: bool,
        profile_name: str = ""
    ):
        super().__init__()
        self.packager = packager
        self.history = history
        self.batch_history = batch_history
        self.task_queue = task_queue
        self.scanner = scanner
        self.task_ids = task_ids
        self.output_dir = output_dir
        self.make_zip = make_zip
        self.profile_name = profile_name
        self._stop = False
        self._batch_id = task_queue.current_batch_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self._start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._project_results = []

    def stop(self):
        self._stop = True

    def run(self):
        total = len(self.task_ids)
        results = []

        for idx, task_id in enumerate(self.task_ids):
            if self._stop:
                break

            task = self.task_queue.get_task(task_id)
            if not task or not task.project_summary:
                continue

            try:
                self.task_started.emit(task_id)
                self.task_queue.update_task_status(task_id, "processing")
                self.project_progress.emit(idx, total, f"正在处理: {task.project_summary.project_name}")
                overall_pct = int((idx / total) * 100)
                self.progress.emit(overall_pct, f"[{idx+1}/{total}] 正在生成 {task.project_summary.project_name}...")

                project = None
                if self.scanner and self.scanner.projects:
                    project = self.scanner.get_project_by_name(task.project_summary.project_name)
                if not project and task.project_summary.source_dir:
                    project = self.scanner.rescan_project(
                        task.project_summary.source_dir,
                        task.project_summary.project_name
                    )

                if not project:
                    raise RuntimeError(f"无法找到项目照片：{task.project_summary.project_name}，请确认源目录存在")

                self.packager.logger.reset_stats()
                self.packager.logger.stats.total_files = project.photo_count

                package_path = self.packager.generate_package(project, task.output_dir or self.output_dir)

                if self.make_zip:
                    self.progress.emit(overall_pct + 5, f"[{idx+1}/{total}] 正在压缩 {task.project_summary.project_name}...")
                    self.packager.generate_zip(package_path)

                record = self.history.create_record_from_stats(
                    project_name=task.project_summary.project_name,
                    client_name=task.project_summary.client_name,
                    shoot_date=task.project_summary.shoot_date,
                    package_path=str(package_path),
                    stats=self.packager.logger.stats,
                    status="success"
                )

                pr = BatchProjectResult(
                    project_name=task.project_summary.project_name,
                    client_name=task.project_summary.client_name,
                    shoot_date=task.project_summary.shoot_date,
                    status="success",
                    total_photos=project.photo_count,
                    processed=self.packager.logger.stats.processed_files,
                    skipped=self.packager.logger.stats.skipped_files,
                    failed=self.packager.logger.stats.failed_files,
                    skip_reasons=dict(self.packager.logger.stats.skip_reasons),
                    failed_files=list(self.packager.logger.stats.failed_files_list),
                    package_path=str(package_path)
                )
                self._project_results.append(pr)

                result = {
                    "task_id": task_id,
                    "project": task.project_summary.project_name,
                    "status": "success",
                    "total": project.photo_count,
                    "processed": self.packager.logger.stats.processed_files,
                    "skipped": self.packager.logger.stats.skipped_files,
                    "failed": self.packager.logger.stats.failed_files,
                    "path": str(package_path)
                }
                results.append(result)
                self.task_queue.update_task_status(task_id, "completed", stats=result)
                self.project_finished.emit(task.project_summary.project_name, result)

            except Exception as e:
                error_msg = str(e)
                self.task_queue.update_task_status(task_id, "failed", error_message=error_msg)

                self.history.create_record_from_stats(
                    project_name=task.project_summary.project_name,
                    client_name=task.project_summary.client_name,
                    shoot_date=task.project_summary.shoot_date,
                    package_path="",
                    stats=self.packager.logger.stats,
                    status="failed",
                    error_message=error_msg
                )

                pr = BatchProjectResult(
                    project_name=task.project_summary.project_name,
                    client_name=task.project_summary.client_name,
                    shoot_date=task.project_summary.shoot_date,
                    status="failed",
                    total_photos=task.project_summary.photo_count,
                    processed=self.packager.logger.stats.processed_files,
                    skipped=self.packager.logger.stats.skipped_files,
                    failed=self.packager.logger.stats.failed_files or task.project_summary.photo_count,
                    skip_reasons=dict(self.packager.logger.stats.skip_reasons),
                    failed_files=list(self.packager.logger.stats.failed_files_list),
                    package_path="",
                    error_message=error_msg
                )
                self._project_results.append(pr)

                result = {
                    "task_id": task_id,
                    "project": task.project_summary.project_name,
                    "status": "error",
                    "error": error_msg,
                    "total": task.project_summary.photo_count,
                    "processed": self.packager.logger.stats.processed_files,
                    "skipped": self.packager.logger.stats.skipped_files,
                    "failed": self.packager.logger.stats.failed_files or task.project_summary.photo_count,
                    "path": ""
                }
                results.append(result)
                self.project_finished.emit(task.project_summary.project_name, result)

        batch_status = "completed" if not self._stop else "stopped"
        self.batch_history.create_record_from_batch(
            batch_id=self._batch_id,
            profile_name=self.profile_name,
            output_dir=self.output_dir,
            make_zip=self.make_zip,
            start_time=self._start_time,
            project_results=self._project_results,
            status=batch_status
        )

        overall_pct = 100
        self.progress.emit(overall_pct, f"完成 {len(results)}/{total} 个项目")
        self.all_finished.emit(results, self._batch_id, batch_status)


class SaveProfileDialog(QDialog):
    def __init__(self, rules: RulesConfig, parent=None):
        super().__init__(parent)
        self.rules = rules
        self.setWindowTitle("保存交付方案")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("如：个人写真标准方案")
        form.addRow("方案名称:", self.name_edit)

        self.type_combo = QComboBox()
        self.type_combo.addItems([t.value for t in ClientType])
        form.addRow("客户类型:", self.type_combo)

        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText("可选，默认留空")
        form.addRow("输出目录:", self.output_dir_edit)

        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._browse)
        form.addRow("", browse_btn)

        self.zip_checkbox = QCheckBox("同时生成 ZIP 压缩包")
        self.zip_checkbox.setChecked(True)
        form.addRow("", self.zip_checkbox)

        layout.addLayout(form)

        summary = QGroupBox("方案预览")
        summary_layout = QVBoxLayout(summary)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("QLabel { padding: 8px; background: #f5f5f5; }")
        summary_layout.addWidget(self.summary_label)
        layout.addWidget(summary)

        self.name_edit.textChanged.connect(self._update_summary)
        self._update_summary()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if dir_path:
            self.output_dir_edit.setText(dir_path)

    def _update_summary(self):
        profile = DeliveryProfile.from_rules(self.rules, self.name_edit.text(), self.type_combo.currentText())
        profile.output_dir = self.output_dir_edit.text()
        profile.make_zip = self.zip_checkbox.isChecked()
        self.summary_label.setText(profile.get_summary())

    def get_profile(self) -> DeliveryProfile:
        profile = DeliveryProfile.from_rules(self.rules, self.name_edit.text(), self.type_combo.currentText())
        profile.output_dir = self.output_dir_edit.text()
        profile.make_zip = self.zip_checkbox.isChecked()
        return profile


class OutputPage(QWidget):
    batch_finished = Signal()
    rules_changed = Signal()
    profile_applied = Signal()

    def __init__(
        self,
        scanner: FileScanner,
        rules: RulesConfig,
        packager: PackageGenerator,
        logger: Logger,
        history: PackageHistory,
        batch_history: BatchHistory,
        profile_manager: DeliveryProfileManager,
        task_queue: TaskQueue,
        parent=None
    ):
        super().__init__(parent)
        self.scanner = scanner
        self.rules = rules
        self.packager = packager
        self.logger = logger
        self.history = history
        self.batch_history = batch_history
        self.profile_manager = profile_manager
        self.task_queue = task_queue
        self.batch_thread = None
        self.image_processor = ImageProcessor()
        self._init_ui()
        self._refresh_profiles()
        self._refresh_queue()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        profile_bar = QGroupBox("交付方案")
        profile_layout = QHBoxLayout(profile_bar)
        profile_layout.setSpacing(8)

        profile_layout.addWidget(QLabel("客户类型:"))
        self.type_combo = QComboBox()
        self.type_combo.addItem("全部", "")
        for t in ClientType:
            self.type_combo.addItem(t.value, t.value)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        profile_layout.addWidget(self.type_combo)

        profile_layout.addWidget(QLabel("选择方案:"))
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(200)
        self.profile_combo.currentIndexChanged.connect(self._on_profile_selected)
        profile_layout.addWidget(self.profile_combo, 1)

        self.apply_profile_btn = QPushButton("✅ 套用方案")
        self.apply_profile_btn.clicked.connect(self._apply_selected_profile)
        profile_layout.addWidget(self.apply_profile_btn)

        self.save_profile_btn = QPushButton("💾 保存当前为方案")
        self.save_profile_btn.clicked.connect(self._save_as_profile)
        profile_layout.addWidget(self.save_profile_btn)

        self.manage_profiles_btn = QPushButton("⚙️ 管理方案")
        self.manage_profiles_btn.clicked.connect(self._manage_profiles)
        profile_layout.addWidget(self.manage_profiles_btn)

        layout.addWidget(profile_bar)

        main_splitter = QSplitter(Qt.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        project_group = QGroupBox("选择项目 (可多选)")
        project_layout = QVBoxLayout(project_group)

        btn_row = QHBoxLayout()
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.clicked.connect(self._select_all)
        btn_row.addWidget(self.select_all_btn)
        self.select_none_btn = QPushButton("全不选")
        self.select_none_btn.clicked.connect(self._select_none)
        btn_row.addWidget(self.select_none_btn)
        self.invert_btn = QPushButton("反选")
        self.invert_btn.clicked.connect(self._invert_selection)
        btn_row.addWidget(self.invert_btn)
        project_layout.addLayout(btn_row)

        self.project_list = QListWidget()
        self.project_list.setSelectionMode(QAbstractItemView.NoSelection)
        self.project_list.itemChanged.connect(self._on_project_check_changed)
        project_layout.addWidget(self.project_list, 1)

        self.selection_label = QLabel("已选择: 0 个项目")
        self.selection_label.setStyleSheet("QLabel { color: #2196F3; font-weight: bold; }")
        project_layout.addWidget(self.selection_label)

        self.add_to_queue_btn = QPushButton("➕ 添加到任务队列")
        self.add_to_queue_btn.clicked.connect(self._add_selected_to_queue)
        self.add_to_queue_btn.setStyleSheet("QPushButton { background: #4CAF50; color: white; padding: 8px; }")
        project_layout.addWidget(self.add_to_queue_btn)

        left_layout.addWidget(project_group)

        output_group = QGroupBox("输出设置")
        output_layout = QVBoxLayout(output_group)

        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("输出目录:"))
        self.output_dir_input = QLineEdit()
        self.output_dir_input.setPlaceholderText("请选择输出目录...")
        self.output_dir_input.textChanged.connect(lambda _: self.refresh_delivery_check())
        dir_layout.addWidget(self.output_dir_input, 1)
        self.browse_btn = QPushButton("...")
        self.browse_btn.setFixedWidth(40)
        self.browse_btn.clicked.connect(self._browse_output_dir)
        dir_layout.addWidget(self.browse_btn)
        output_layout.addLayout(dir_layout)

        self.zip_checkbox = QCheckBox("同时生成 ZIP 压缩包")
        self.zip_checkbox.setChecked(True)
        output_layout.addWidget(self.zip_checkbox)

        self.log_checkbox = QCheckBox("保存打包历史记录")
        self.log_checkbox.setChecked(True)
        output_layout.addWidget(self.log_checkbox)

        left_layout.addWidget(output_group)

        left_panel.setMinimumWidth(320)
        main_splitter.addWidget(left_panel)

        middle_panel = QWidget()
        middle_layout = QVBoxLayout(middle_panel)
        middle_layout.setContentsMargins(0, 0, 0, 0)
        middle_layout.setSpacing(8)

        queue_group = QGroupBox("📋 任务中心 (队列)")
        queue_layout = QVBoxLayout(queue_group)

        queue_stats_row = QHBoxLayout()
        self.queue_stats_label = QLabel("待处理: 0  |  已确认: 0  |  已完成: 0")
        self.queue_stats_label.setStyleSheet("QLabel { color: #666; }")
        queue_stats_row.addWidget(self.queue_stats_label)
        queue_stats_row.addStretch()
        self.refresh_queue_btn = QPushButton("🔄")
        self.refresh_queue_btn.setFixedWidth(32)
        self.refresh_queue_btn.clicked.connect(self._refresh_queue)
        queue_stats_row.addWidget(self.refresh_queue_btn)
        queue_layout.addLayout(queue_stats_row)

        self.queue_list = QListWidget()
        self.queue_list.itemClicked.connect(self._on_queue_item_clicked)
        queue_layout.addWidget(self.queue_list, 1)

        queue_btn_row = QHBoxLayout()
        self.confirm_all_btn = QPushButton("✅ 全部确认")
        self.confirm_all_btn.clicked.connect(self._confirm_all_tasks)
        queue_btn_row.addWidget(self.confirm_all_btn)
        self.remove_task_btn = QPushButton("🗑️ 移除")
        self.remove_task_btn.clicked.connect(self._remove_selected_task)
        queue_btn_row.addWidget(self.remove_task_btn)
        self.clear_queue_btn = QPushButton("🧹 清空")
        self.clear_queue_btn.clicked.connect(self._clear_queue)
        queue_btn_row.addWidget(self.clear_queue_btn)
        queue_layout.addLayout(queue_btn_row)

        self.selected_queue_detail = QTextEdit()
        self.selected_queue_detail.setReadOnly(True)
        self.selected_queue_detail.setMaximumHeight(140)
        self.selected_queue_detail.setPlaceholderText("点击任务查看确认摘要...")
        queue_layout.addWidget(self.selected_queue_detail)

        confirm_btn_row = QHBoxLayout()
        self.confirm_btn = QPushButton("✅ 确认并开始")
        self.confirm_btn.clicked.connect(self._confirm_and_start)
        self.confirm_btn.setStyleSheet("QPushButton { background: #2196F3; color: white; padding: 12px; font-size: 14px; font-weight: bold; }")
        confirm_btn_row.addWidget(self.confirm_btn, 2)
        self.stop_btn = QPushButton("⏹️ 停止")
        self.stop_btn.clicked.connect(self._stop_batch)
        self.stop_btn.setEnabled(False)
        confirm_btn_row.addWidget(self.stop_btn)
        queue_layout.addLayout(confirm_btn_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        queue_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("就绪")
        self.status_label.setAlignment(Qt.AlignCenter)
        queue_layout.addWidget(self.status_label)

        middle_layout.addWidget(queue_group)

        middle_panel.setMinimumWidth(340)
        main_splitter.addWidget(middle_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()

        check_widget = QWidget()
        check_layout = QVBoxLayout(check_widget)
        check_layout.setContentsMargins(5, 5, 5, 5)

        check_summary = QGroupBox("交付检查汇总")
        check_summary_layout = QVBoxLayout(check_summary)
        self.check_summary_label = QLabel("请选择项目后点击『执行交付检查』")
        self.check_summary_label.setWordWrap(True)
        self.check_summary_label.setStyleSheet("QLabel { padding: 8px; }")
        check_summary_layout.addWidget(self.check_summary_label)
        check_layout.addWidget(check_summary)

        check_detail_group = QGroupBox("详细信息")
        check_detail_layout = QVBoxLayout(check_detail_group)
        self.check_detail = QTextEdit()
        self.check_detail.setReadOnly(True)
        check_detail_layout.addWidget(self.check_detail)
        check_layout.addWidget(check_detail_group, 1)

        self.tabs.addTab(check_widget, "✅ 交付检查")

        result_widget = QWidget()
        result_layout = QVBoxLayout(result_widget)
        result_layout.setContentsMargins(5, 5, 5, 5)

        result_table_group = QGroupBox("批量生成结果")
        result_table_layout = QVBoxLayout(result_table_group)

        self.result_table = QTableWidget()
        self.result_table.setColumnCount(6)
        self.result_table.setHorizontalHeaderLabels(["项目", "状态", "总数", "成功", "跳过", "失败"])
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.result_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.result_table.setAlternatingRowColors(True)
        result_table_layout.addWidget(self.result_table)

        result_layout.addWidget(result_table_group, 1)

        result_detail_group = QGroupBox("选中项目详情")
        result_detail_layout = QVBoxLayout(result_detail_group)
        self.result_detail = QTextEdit()
        self.result_detail.setReadOnly(True)
        self.result_detail.setMaximumHeight(150)
        result_detail_layout.addWidget(self.result_detail)
        result_layout.addWidget(result_detail_group)

        self.result_table.itemClicked.connect(self._on_result_clicked)

        self.tabs.addTab(result_widget, "📊 生成结果")

        right_layout.addWidget(self.tabs)

        main_splitter.addWidget(right_panel)
        main_splitter.setSizes([320, 340, 540])

        layout.addWidget(main_splitter, 1)

    def _refresh_profiles(self):
        current_type = self.type_combo.currentData()
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItem("（不使用方案）", "")

        if current_type:
            profiles = self.profile_manager.get_profiles_by_type(current_type)
        else:
            profiles = self.profile_manager.profiles

        for p in profiles:
            self.profile_combo.addItem(f"[{p.client_type}] {p.name}", p.profile_id)

        self.profile_combo.blockSignals(False)

    def _on_type_changed(self, _idx):
        self._refresh_profiles()

    def _on_profile_selected(self, _idx):
        pass

    def _apply_selected_profile(self):
        profile_id = self.profile_combo.currentData()
        if not profile_id:
            QMessageBox.information(self, "提示", "请先选择一个方案")
            return

        profile = self.profile_manager.get_profile(profile_id)
        if not profile:
            QMessageBox.warning(self, "提示", "方案不存在")
            return

        profile.apply_to_rules(self.rules)
        if profile.output_dir:
            self.output_dir_input.setText(profile.output_dir)
        self.zip_checkbox.setChecked(profile.make_zip)

        self.rules_changed.emit()
        self.profile_applied.emit()
        self.refresh_delivery_check()

        QMessageBox.information(self, "成功", f"已套用方案: {profile.name}\n\n预览和交付检查已按新规则更新。")

    def _save_as_profile(self):
        dialog = SaveProfileDialog(self.rules, self)
        if dialog.exec() == QDialog.Accepted:
            profile = dialog.get_profile()
            if not profile.name:
                QMessageBox.warning(self, "提示", "请输入方案名称")
                return
            self.profile_manager.add_profile(profile)
            self._refresh_profiles()
            idx = self.profile_combo.findData(profile.profile_id)
            if idx >= 0:
                self.profile_combo.setCurrentIndex(idx)
            QMessageBox.information(self, "成功", f"方案已保存: {profile.name}")

    def _manage_profiles(self):
        QMessageBox.information(self, "管理方案", "方案管理功能正在开发中\n\n当前可以在保存方案时覆盖同名方案")

    def _create_summary_for_project(self, project: ProjectItem) -> ProjectSummary:
        raw_count = 0
        corrupted_count = 0
        raw_extensions = {'.raw', '.cr2', '.nef', '.arw', '.dng', '.rw2'}
        for photo in project.photos:
            ext = photo.path.suffix.lower()
            if ext in raw_extensions:
                raw_count += 1
            elif not self.image_processor.is_valid_image(photo.path):
                corrupted_count += 1
        return ProjectSummary(
            project_name=project.name,
            photo_count=project.photo_count,
            client_name=project.client_name or "",
            shoot_date=project.shoot_date or "",
            total_size_mb=project.total_size / (1024 * 1024),
            cover_path=str(project.cover_path) if project.cover_path else "",
            source_dir=str(project.source_dir) if hasattr(project, 'source_dir') and project.source_dir else "",
            raw_count=raw_count,
            corrupted_count=corrupted_count
        )

    def _add_selected_to_queue(self):
        projects = self._get_selected_projects()
        if not projects:
            QMessageBox.information(self, "提示", "请先勾选要添加的项目")
            return

        profile_id = self.profile_combo.currentData()
        profile_name = self.profile_combo.currentText() if profile_id else "默认设置"
        output_dir = self.output_dir_input.text().strip()
        make_zip = self.zip_checkbox.isChecked()

        added = 0
        for project in projects:
            existing = [t for t in self.task_queue.tasks
                        if t.project_summary and t.project_summary.project_name == project.name
                        and t.status in {"pending", "confirmed", "stopped"}]
            if existing:
                continue

            summary = self._create_summary_for_project(project)
            task = QueueTask(
                project_summary=summary,
                profile_id=profile_id or "",
                profile_name=profile_name,
                output_dir=output_dir,
                make_zip=make_zip,
                status="pending"
            )
            self.task_queue.add_task(task)
            added += 1

        self._refresh_queue()
        if added > 0:
            QMessageBox.information(self, "成功", f"已添加 {added} 个项目到任务队列")
        else:
            QMessageBox.information(self, "提示", "所选项目已全部在队列中")

    def _refresh_queue(self):
        self.queue_list.clear()

        stats = self.task_queue.get_stats()
        self.queue_stats_label.setText(
            f"待确认: {stats['pending']}  |  已确认: {stats['confirmed']}  |  "
            f"进行中: {stats['processing']}  |  已完成: {stats['completed']}  |  失败: {stats['failed']}"
        )

        has_incomplete = False
        for task in sorted(self.task_queue.tasks, key=lambda t: t.order):
            if task.status not in {"completed", "failed"}:
                has_incomplete = True

            status_text = {
                "pending": "⏳ 待确认",
                "confirmed": "✅ 已确认",
                "processing": "🔄 处理中",
                "completed": "✓ 已完成",
                "failed": "✗ 失败",
                "stopped": "⏸️ 已停止"
            }.get(task.status, task.status)

            status_color = {
                "pending": "#FF9800",
                "confirmed": "#4CAF50",
                "processing": "#2196F3",
                "completed": "#4CAF50",
                "failed": "#F44336",
                "stopped": "#9E9E9E"
            }.get(task.status, "#333")

            if task.project_summary:
                item_text = f"{status_text} | {task.project_summary.project_name} ({task.project_summary.photo_count}张)"
            else:
                item_text = f"{status_text} | 未知项目"

            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, task.task_id)
            item.setForeground(QColor(status_color))
            if task.status == "completed":
                font = item.font()
                font.setStrikeOut(True)
                item.setFont(font)
            self.queue_list.addItem(item)

        if has_incomplete:
            self.status_label.setText(f"⚠️ 队列中有未完成任务，下次启动可继续")
            self.status_label.setStyleSheet("QLabel { color: #FF9800; }")
        else:
            self.status_label.setText("就绪")
            self.status_label.setStyleSheet("QLabel { color: #333; }")

    def _on_queue_item_clicked(self, item):
        task_id = item.data(Qt.UserRole)
        task = self.task_queue.get_task(task_id)
        if task:
            self.selected_queue_detail.setPlainText(task.get_confirmation_text())

    def _confirm_all_tasks(self):
        count = self.task_queue.confirm_all_pending()
        self._refresh_queue()
        QMessageBox.information(self, "成功", f"已确认 {count} 个任务")

    def _remove_selected_task(self):
        current = self.queue_list.currentItem()
        if not current:
            QMessageBox.information(self, "提示", "请先选择一个任务")
            return
        task_id = current.data(Qt.UserRole)
        if self.task_queue.remove_task(task_id):
            self._refresh_queue()
            self.selected_queue_detail.clear()

    def _clear_queue(self):
        count = self.task_queue.clear_all()
        self._refresh_queue()
        QMessageBox.information(self, "成功", f"已清空 {count} 个任务")

    def _confirm_and_start(self):
        if self.batch_thread and self.batch_thread.isRunning():
            return

        confirmed = self.task_queue.get_confirmed_tasks()
        pending = self.task_queue.get_unconfirmed_tasks()

        if not confirmed and not pending:
            QMessageBox.warning(self, "提示", "队列为空，请先添加项目")
            return

        if pending:
            reply = QMessageBox.question(
                self, "确认任务",
                f"有 {len(pending)} 个任务尚未确认，是否全部确认并开始？\n\n"
                f"已确认: {len(confirmed)} 个\n"
                f"待确认: {len(pending)} 个",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            if reply == QMessageBox.Yes:
                self.task_queue.confirm_all_pending()
            elif reply == QMessageBox.Cancel:
                return

        all_tasks = self.task_queue.get_confirmed_tasks()
        if not all_tasks:
            QMessageBox.warning(self, "提示", "没有可执行的任务")
            return

        batch_id = self.task_queue.start_new_batch()
        task_ids = [t.task_id for t in all_tasks]

        output_dir = self.output_dir_input.text().strip()
        if not output_dir:
            QMessageBox.warning(self, "提示", "请选择输出目录")
            return
        if not Path(output_dir).exists():
            QMessageBox.warning(self, "错误", "输出目录不存在")
            return

        self.tabs.setCurrentIndex(1)
        self._init_result_table([t.project_summary for t in all_tasks if t.project_summary])

        self.confirm_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("开始批量生成...")

        profile_name = self.profile_combo.currentText() if self.profile_combo.currentData() else "默认设置"

        self.batch_thread = BatchPackageThread(
            self.packager,
            self.history,
            self.batch_history,
            self.task_queue,
            self.scanner,
            task_ids,
            output_dir,
            self.zip_checkbox.isChecked(),
            profile_name
        )
        self.batch_thread.progress.connect(self._on_batch_progress)
        self.batch_thread.task_started.connect(self._on_task_started)
        self.batch_thread.project_finished.connect(self._on_project_finished)
        self.batch_thread.all_finished.connect(self._on_batch_all_finished)
        self.batch_thread.error.connect(self._on_batch_error)
        self.batch_thread.start()

    def _stop_batch(self):
        if self.batch_thread and self.batch_thread.isRunning():
            self.batch_thread.stop()
            self.status_label.setText("正在停止...")

    def _on_task_started(self, task_id):
        for i in range(self.queue_list.count()):
            item = self.queue_list.item(i)
            if item.data(Qt.UserRole) == task_id:
                task = self.task_queue.get_task(task_id)
                if task and task.project_summary:
                    item.setText(f"🔄 处理中 | {task.project_summary.project_name}")
                    item.setForeground(QColor("#2196F3"))
                break

    def refresh_projects(self):
        self.project_list.clear()

        for project in self.scanner.projects:
            item = QListWidgetItem(f"📷 {project.name}  ({project.photo_count} 张)")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if len(self.scanner.projects) <= 5 else Qt.Unchecked)
            item.setData(Qt.UserRole, project.name)
            self.project_list.addItem(item)

        self._update_selection_count()
        self.refresh_delivery_check()

    def _select_all(self):
        for i in range(self.project_list.count()):
            self.project_list.item(i).setCheckState(Qt.Checked)

    def _select_none(self):
        for i in range(self.project_list.count()):
            self.project_list.item(i).setCheckState(Qt.Unchecked)

    def _invert_selection(self):
        for i in range(self.project_list.count()):
            item = self.project_list.item(i)
            item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)

    def _on_project_check_changed(self, _item):
        self._update_selection_count()
        self.refresh_delivery_check()

    def _update_selection_count(self):
        count = self._get_selected_count()
        total_photos = self._get_selected_total_photos()
        self.selection_label.setText(f"已选择: {count} 个项目 / 共 {total_photos} 张照片")

    def _get_selected_count(self) -> int:
        count = 0
        for i in range(self.project_list.count()):
            if self.project_list.item(i).checkState() == Qt.Checked:
                count += 1
        return count

    def _get_selected_projects(self) -> list:
        projects = []
        for i in range(self.project_list.count()):
            item = self.project_list.item(i)
            if item.checkState() == Qt.Checked:
                name = item.data(Qt.UserRole)
                project = self.scanner.get_project_by_name(name)
                if project:
                    projects.append(project)
        return projects

    def _get_selected_total_photos(self) -> int:
        return sum(p.photo_count for p in self._get_selected_projects())

    def refresh_delivery_check(self):
        projects = self._get_selected_projects()
        if not projects:
            self.check_summary_label.setText("请勾选要生成的项目")
            self.check_detail.clear()
            return
        self._run_delivery_check()

    def _run_delivery_check(self):
        projects = self._get_selected_projects()
        if not projects:
            QMessageBox.information(self, "提示", "请先勾选要检查的项目")
            return

        output_dir = self.output_dir_input.text().strip()

        total_projects = len(projects)
        total_photos = sum(p.photo_count for p in projects)
        total_size_mb = sum(p.total_size for p in projects) / (1024 * 1024)

        expire_date = ""
        if self.rules.expire_enabled:
            expire = datetime.now() + timedelta(days=self.rules.expire_days)
            expire_date = expire.strftime("%Y-%m-%d")

        wm_text = self.rules.watermark_text if self.rules.watermark_enabled else "（无）"
        thumb_size = f"{self.rules.thumbnail_width} × {self.rules.thumbnail_height}"

        summary_html = f"""
        <b>总项目数:</b> {total_projects} 个<br>
        <b>总照片数:</b> {total_photos} 张<br>
        <b>预计总大小:</b> {total_size_mb * 1.2:.1f} MB（含缩略图）<br>
        <b>输出目录:</b> {output_dir or '（未设置）'}<br>
        <b>缩略图尺寸:</b> {thumb_size} px<br>
        <b>水印文字:</b> {wm_text}<br>
        <b>入选上限:</b> {self.rules.max_selection} 张/项目<br>
        <b>过期日期:</b> {expire_date or '（未启用）'}
        """
        self.check_summary_label.setText(summary_html)

        detail_lines = []
        detail_lines.append("=" * 50)
        detail_lines.append("项目级检查结果")
        detail_lines.append("=" * 50)

        all_missing = []
        all_corrupted = []
        all_raw_count = 0

        for project in projects:
            detail_lines.append("")
            detail_lines.append(f"▶ {project.name}")
            detail_lines.append(f"   客户姓名: {project.client_name or '⚠️ 未识别'}")
            detail_lines.append(f"   拍摄日期: {project.shoot_date or '⚠️ 未识别'}")
            detail_lines.append(f"   照片数量: {project.photo_count} 张")
            detail_lines.append(f"   封  面: {'✓' if project.cover_path else '⚠️ 缺失'}")

            sample_names = self._preview_filenames(project, 3)
            detail_lines.append(f"   文件名示例:")
            for name in sample_names:
                detail_lines.append(f"     • {name}")

            missing = 0
            corrupted = 0
            raw_count = 0
            for photo in project.photos:
                if not photo.path.exists():
                    missing += 1
                    all_missing.append(f"{project.name}/{photo.filename}")
                    continue

                ext = photo.path.suffix.lower()
                if ext in {'.raw', '.cr2', '.nef', '.arw', '.dng', '.rw2'}:
                    raw_count += 1
                    all_raw_count += 1
                    continue

                if not self.image_processor.is_valid_image(photo.path):
                    corrupted += 1
                    all_corrupted.append(f"{project.name}/{photo.filename}")

            if missing > 0:
                detail_lines.append(f"   ⚠️ 缺失文件: {missing} 个")
            if corrupted > 0:
                detail_lines.append(f"   ❌ 损坏文件: {corrupted} 个")
            if raw_count > 0:
                if self.rules.include_raw:
                    detail_lines.append(f"   📄 RAW文件: {raw_count} 个（设置包含，将一并输出）")
                else:
                    detail_lines.append(f"   📄 RAW文件: {raw_count} 个（设置不包含，仅输出普通图片）")
            if missing == 0 and corrupted == 0:
                detail_lines.append(f"   ✓ 文件检查正常")

        detail_lines.append("")
        detail_lines.append("=" * 50)
        detail_lines.append("整体汇总")
        detail_lines.append("=" * 50)
        detail_lines.append(f"缺失文件总数: {len(all_missing)} 个")
        detail_lines.append(f"损坏文件总数: {len(all_corrupted)} 个")
        detail_lines.append(f"RAW 文件总数: {all_raw_count} 个")

        if all_corrupted:
            detail_lines.append("")
            detail_lines.append("损坏文件列表:")
            for f in all_corrupted[:10]:
                detail_lines.append(f"  ❌ {f}")
            if len(all_corrupted) > 10:
                detail_lines.append(f"  ... 还有 {len(all_corrupted) - 10} 个")

        if all_raw_count > 0 and not self.rules.include_raw:
            detail_lines.append("")
            detail_lines.append("ℹ️  RAW文件将在打包时跳过，不视为损坏")

        self.check_detail.setPlainText("\n".join(detail_lines))

    def _preview_filenames(self, project: ProjectItem, count: int = 3) -> list:
        names = []
        for i, photo in enumerate(project.photos[:count], 1):
            try:
                base = self.rules.naming_pattern.format(
                    client=project.client_name or "client",
                    date=project.shoot_date or "unknown",
                    index=i,
                    original=photo.path.stem
                )
            except Exception:
                base = f"photo_{i:04d}"

            fmt = self.rules.output_format
            if fmt == "original" or not fmt:
                ext = photo.path.suffix.lower()
            else:
                ext = f".{fmt}"
            names.append(base + ext)
        return names

    def _browse_output_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if dir_path:
            self.output_dir_input.setText(dir_path)

    def _init_result_table(self, summaries):
        self.result_table.setRowCount(len(summaries))
        for i, s in enumerate(summaries):
            self._set_result_row(i, s.project_name, "等待中", s.photo_count, 0, 0, 0)

    def _set_result_row(self, row, name, status, total, processed, skipped, failed):
        self.result_table.setItem(row, 0, QTableWidgetItem(name))
        status_item = QTableWidgetItem(status)
        if status == "成功":
            status_item.setForeground(QColor("#4CAF50"))
        elif status == "失败":
            status_item.setForeground(QColor("#F44336"))
        elif status == "处理中...":
            status_item.setForeground(QColor("#2196F3"))
        self.result_table.setItem(row, 1, status_item)
        self.result_table.setItem(row, 2, QTableWidgetItem(str(total)))
        self.result_table.setItem(row, 3, QTableWidgetItem(str(processed)))
        self.result_table.setItem(row, 4, QTableWidgetItem(str(skipped)))
        self.result_table.setItem(row, 5, QTableWidgetItem(str(failed)))

    def _on_batch_progress(self, value, message):
        self.progress_bar.setValue(value)
        self.status_label.setText(message)

    def _on_project_finished(self, project_name, result):
        for i in range(self.result_table.rowCount()):
            if self.result_table.item(i, 0).text() == project_name:
                status = "成功" if result["status"] == "success" else "失败"
                self._set_result_row(
                    i, project_name, status,
                    result["total"], result["processed"],
                    result["skipped"], result["failed"]
                )
                break
        self._refresh_queue()

    def _on_batch_all_finished(self, results, batch_id, batch_status):
        self.confirm_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setValue(100)

        success_count = sum(1 for r in results if r["status"] == "success")
        fail_count = sum(1 for r in results if r["status"] == "error")
        self.status_label.setText(f"完成！成功 {success_count} 个，失败 {fail_count} 个")

        self.batch_finished.emit()

        msg = f"批次号: {batch_id}\n共处理 {len(results)} 个项目\n成功: {success_count} 个\n失败: {fail_count} 个"
        if batch_status == "stopped":
            msg += "\n\n（用户中途停止）"
        QMessageBox.information(self, "批量生成完成", msg)

    def _on_batch_error(self, error_msg):
        self.confirm_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.status_label.setText("批量生成出错")
        QMessageBox.critical(self, "错误", f"批量生成失败: {error_msg}")

    def _on_result_clicked(self, item):
        row = item.row()
        if row < 0 or row >= self.result_table.rowCount():
            return

        project_name = self.result_table.item(row, 0).text()
        status = self.result_table.item(row, 1).text()

        records = self.history.get_records_by_project(project_name)
        if not records:
            self.result_detail.setPlainText(f"项目: {project_name}\n状态: {status}\n\n暂无历史记录")
            return

        latest = records[0]
        detail_text = f"""项目名称: {latest.project_name}
客户姓名: {latest.client_name or '未填写'}
拍摄日期: {latest.shoot_date or '未识别'}
打包时间: {latest.timestamp}
状态: {'成功' if latest.status == 'success' else '失败'}

统计:
  总照片数: {latest.total_photos}
  成功处理: {latest.processed}
  跳过数量: {latest.skipped}
  失败数量: {latest.failed}

输出路径:
  {latest.package_path}
"""
        if latest.skip_reasons:
            detail_text += "\n跳过原因:\n"
            for reason, count in latest.skip_reasons.items():
                detail_text += f"  • {reason}: {count} 个\n"

        if latest.failed_files:
            detail_text += "\n失败文件:\n"
            for f in latest.failed_files[:10]:
                detail_text += f"  • {f.get('filename', '?')}: {f.get('error', '?')}\n"
            if len(latest.failed_files) > 10:
                detail_text += f"  ... 还有 {len(latest.failed_files) - 10} 个\n"

        self.result_detail.setPlainText(detail_text)

    def _open_output_dir(self):
        output_dir = self.output_dir_input.text().strip()
        if output_dir and Path(output_dir).exists():
            try:
                os.startfile(output_dir)
            except Exception:
                QMessageBox.information(self, "提示", f"输出目录:\n{output_dir}")
        else:
            QMessageBox.warning(self, "提示", "请先设置输出目录")
