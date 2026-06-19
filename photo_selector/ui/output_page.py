import os
from pathlib import Path
from datetime import datetime, timedelta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QFileDialog, QGroupBox, QCheckBox, QProgressBar, QMessageBox,
    QListWidget, QListWidgetItem, QTextEdit, QSplitter, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
)
from PySide6.QtCore import Signal, Qt, QThread
from PySide6.QtGui import QColor

from ..scanner import FileScanner, ProjectItem
from ..rules import RulesConfig
from ..packager import PackageGenerator
from ..logger import Logger, PackageHistory, ProcessingStats
from ..image_processor import ImageProcessor


class BatchPackageThread(QThread):
    progress = Signal(int, str)
    project_progress = Signal(int, int, str)
    project_finished = Signal(str, dict)
    all_finished = Signal(list)
    error = Signal(str)

    def __init__(
        self,
        packager: PackageGenerator,
        history: PackageHistory,
        projects: list,
        output_dir: str,
        make_zip: bool
    ):
        super().__init__()
        self.packager = packager
        self.history = history
        self.projects = projects
        self.output_dir = output_dir
        self.make_zip = make_zip
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        total = len(self.projects)
        results = []
        stats_list = []

        for idx, project in enumerate(self.projects):
            if self._stop:
                break

            try:
                self.project_progress.emit(idx, total, f"正在处理: {project.name}")
                overall_pct = int((idx / total) * 100)
                self.progress.emit(overall_pct, f"[{idx+1}/{total}] 正在生成 {project.name}...")

                self.packager.logger.reset_stats()
                self.packager.logger.stats.total_files = project.photo_count

                package_path = self.packager.generate_package(project, self.output_dir)

                if self.make_zip:
                    self.progress.emit(overall_pct + 5, f"[{idx+1}/{total}] 正在压缩 {project.name}...")
                    self.packager.generate_zip(package_path)

                record = self.history.create_record_from_stats(
                    project_name=project.name,
                    client_name=project.client_name,
                    shoot_date=project.shoot_date,
                    package_path=str(package_path),
                    stats=self.packager.logger.stats,
                    status="success"
                )

                result = {
                    "project": project.name,
                    "status": "success",
                    "total": project.photo_count,
                    "processed": self.packager.logger.stats.processed_files,
                    "skipped": self.packager.logger.stats.skipped_files,
                    "failed": self.packager.logger.stats.failed_files,
                    "path": str(package_path)
                }
                results.append(result)
                self.project_finished.emit(project.name, result)
                stats_list.append(record)

            except Exception as e:
                result = {
                    "project": project.name,
                    "status": "error",
                    "error": str(e),
                    "total": project.photo_count,
                    "processed": 0,
                    "skipped": 0,
                    "failed": project.photo_count,
                    "path": ""
                }
                results.append(result)
                self.project_finished.emit(project.name, result)

        overall_pct = 100
        self.progress.emit(overall_pct, f"完成 {len(results)}/{total} 个项目")
        self.all_finished.emit(results)


class OutputPage(QWidget):
    batch_finished = Signal()

    def __init__(
        self,
        scanner: FileScanner,
        rules: RulesConfig,
        packager: PackageGenerator,
        logger: Logger,
        history: PackageHistory,
        parent=None
    ):
        super().__init__(parent)
        self.scanner = scanner
        self.rules = rules
        self.packager = packager
        self.logger = logger
        self.history = history
        self.batch_thread = None
        self.image_processor = ImageProcessor()
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        main_splitter = QSplitter(Qt.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        project_group = QGroupBox("选择项目 (可多选批量生成)")
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

        left_layout.addWidget(project_group)

        output_group = QGroupBox("输出设置")
        output_layout = QVBoxLayout(output_group)

        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("输出目录:"))
        self.output_dir_input = QLineEdit()
        self.output_dir_input.setPlaceholderText("请选择输出目录...")
        self.output_dir_input.textChanged.connect(lambda _: self.refresh_delivery_check())
        dir_layout.addWidget(self.output_dir_input)

        self.browse_btn = QPushButton("浏览...")
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

        action_group = QGroupBox("操作")
        action_layout = QVBoxLayout(action_group)

        self.check_btn = QPushButton("🔍 执行交付检查")
        self.check_btn.clicked.connect(self._run_delivery_check)
        action_layout.addWidget(self.check_btn)

        self.generate_btn = QPushButton("📦 批量生成选片包")
        self.generate_btn.clicked.connect(self._start_batch)
        self.generate_btn.setStyleSheet(
            "QPushButton { background: #2196F3; color: white; padding: 14px; font-size: 15px; font-weight: bold; }"
            "QPushButton:hover { background: #1976D2; }"
            "QPushButton:disabled { background: #BDBDBD; }"
        )
        action_layout.addWidget(self.generate_btn)

        self.stop_btn = QPushButton("停止")
        self.stop_btn.clicked.connect(self._stop_batch)
        self.stop_btn.setEnabled(False)
        action_layout.addWidget(self.stop_btn)

        self.open_dir_btn = QPushButton("打开输出目录")
        self.open_dir_btn.clicked.connect(self._open_output_dir)
        action_layout.addWidget(self.open_dir_btn)

        left_layout.addWidget(action_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        left_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("就绪")
        self.status_label.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(self.status_label)

        left_layout.addStretch()

        main_splitter.addWidget(left_panel)

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
        main_splitter.setSizes([380, 620])

        layout.addWidget(main_splitter, 1)

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
                elif not self.image_processor.is_valid_image(photo.path):
                    corrupted += 1
                    all_corrupted.append(f"{project.name}/{photo.filename}")

                ext = photo.path.suffix.lower()
                if ext in {'.raw', '.cr2', '.nef', '.arw', '.dng', '.rw2'}:
                    raw_count += 1
                    all_raw_count += 1

            if missing > 0:
                detail_lines.append(f"   ⚠️ 缺失文件: {missing} 个")
            if corrupted > 0:
                detail_lines.append(f"   ❌ 损坏文件: {corrupted} 个")
            if raw_count > 0 and not self.rules.include_raw:
                detail_lines.append(f"   ℹ️  RAW文件: {raw_count} 个（设置不包含，将仅复制普通图片）")
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

    def _start_batch(self):
        if self.batch_thread and self.batch_thread.isRunning():
            return

        projects = self._get_selected_projects()
        if not projects:
            QMessageBox.warning(self, "提示", "请先勾选要生成的项目")
            return

        output_dir = self.output_dir_input.text().strip()
        if not output_dir:
            QMessageBox.warning(self, "提示", "请选择输出目录")
            return

        if not Path(output_dir).exists():
            QMessageBox.warning(self, "错误", "输出目录不存在")
            return

        self.tabs.setCurrentIndex(1)
        self._init_result_table(projects)

        self.generate_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("开始批量生成...")

        self.batch_thread = BatchPackageThread(
            self.packager,
            self.history,
            projects,
            output_dir,
            self.zip_checkbox.isChecked()
        )
        self.batch_thread.progress.connect(self._on_batch_progress)
        self.batch_thread.project_finished.connect(self._on_project_finished)
        self.batch_thread.all_finished.connect(self._on_batch_all_finished)
        self.batch_thread.error.connect(self._on_batch_error)
        self.batch_thread.start()

    def _stop_batch(self):
        if self.batch_thread and self.batch_thread.isRunning():
            self.batch_thread.stop()
            self.status_label.setText("正在停止...")

    def _init_result_table(self, projects):
        self.result_table.setRowCount(len(projects))
        for i, project in enumerate(projects):
            self._set_result_row(i, project.name, "等待中", project.photo_count, 0, 0, 0)

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

    def _on_batch_all_finished(self, results):
        self.generate_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setValue(100)

        success_count = sum(1 for r in results if r["status"] == "success")
        fail_count = sum(1 for r in results if r["status"] == "error")
        self.status_label.setText(f"完成！成功 {success_count} 个，失败 {fail_count} 个")

        self.batch_finished.emit()

        QMessageBox.information(
            self, "批量生成完成",
            f"共处理 {len(results)} 个项目\n"
            f"成功: {success_count} 个\n"
            f"失败: {fail_count} 个"
        )

    def _on_batch_error(self, error_msg):
        self.generate_btn.setEnabled(True)
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
状态: {latest.status}

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
