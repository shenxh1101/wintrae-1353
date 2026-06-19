from datetime import datetime, timedelta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox, QTextEdit,
    QSplitter, QAbstractItemView, QMessageBox, QListWidget, QListWidgetItem,
    QDateEdit, QTabWidget
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QColor

from ..logger import Logger, PackageHistory, PackageRecord


class LogPage(QWidget):
    def __init__(self, logger: Logger, history: PackageHistory, parent=None):
        super().__init__(parent)
        self.logger = logger
        self.history = history
        self._current_entries = []
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self.tabs = QTabWidget()

        self._init_history_tab()
        self._init_realtime_tab()

        layout.addWidget(self.tabs, 1)

    def _init_history_tab(self):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        project_group = QGroupBox("项目")
        project_layout = QVBoxLayout(project_group)

        self.project_list = QListWidget()
        self.project_list.itemClicked.connect(self._on_project_clicked)
        project_layout.addWidget(self.project_list)

        self.total_projects_label = QLabel("共 0 个项目")
        self.total_projects_label.setStyleSheet("QLabel { color: #666; font-size: 11px; }")
        project_layout.addWidget(self.total_projects_label)

        left_layout.addWidget(project_group)

        filter_group = QGroupBox("时间筛选")
        filter_layout = QVBoxLayout(filter_group)

        date_row = QHBoxLayout()
        date_row.addWidget(QLabel("从:"))
        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        default_start = QDate.currentDate().addDays(-30)
        self.start_date.setDate(default_start)
        date_row.addWidget(self.start_date)
        filter_layout.addLayout(date_row)

        date_row2 = QHBoxLayout()
        date_row2.addWidget(QLabel("到:"))
        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDate(QDate.currentDate())
        date_row2.addWidget(self.end_date)
        filter_layout.addLayout(date_row2)

        self.apply_filter_btn = QPushButton("应用筛选")
        self.apply_filter_btn.clicked.connect(self._apply_date_filter)
        filter_layout.addWidget(self.apply_filter_btn)

        self.reset_filter_btn = QPushButton("显示全部")
        self.reset_filter_btn.clicked.connect(self._reset_date_filter)
        filter_layout.addWidget(self.reset_filter_btn)

        left_layout.addWidget(filter_group)

        left_layout.addStretch()

        self.export_btn = QPushButton("📥 导出选中记录")
        self.export_btn.clicked.connect(self._export_selected_record)
        left_layout.addWidget(self.export_btn)

        self.refresh_history_btn = QPushButton("🔄 刷新历史")
        self.refresh_history_btn.clicked.connect(self.refresh_history)
        left_layout.addWidget(self.refresh_history_btn)

        layout.addWidget(left_panel, 1)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        records_group = QGroupBox("打包记录")
        records_layout = QVBoxLayout(records_group)

        self.records_table = QTableWidget()
        self.records_table.setColumnCount(5)
        self.records_table.setHorizontalHeaderLabels(["时间", "项目", "状态", "总数", "成功/跳过/失败"])
        self.records_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.records_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.records_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.records_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.records_table.setAlternatingRowColors(True)
        self.records_table.itemClicked.connect(self._on_record_clicked)
        records_layout.addWidget(self.records_table)

        self.records_count_label = QLabel("共 0 条记录")
        self.records_count_label.setStyleSheet("QLabel { color: #666; font-size: 11px; }")
        records_layout.addWidget(self.records_count_label)

        right_layout.addWidget(records_group, 1)

        detail_group = QGroupBox("记录详情")
        detail_layout = QVBoxLayout(detail_group)
        self.record_detail = QTextEdit()
        self.record_detail.setReadOnly(True)
        detail_layout.addWidget(self.record_detail)
        right_layout.addWidget(detail_group)

        layout.addWidget(right_panel, 3)

        self.tabs.addTab(widget, "📊 打包历史")

    def _init_realtime_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)

        stats_group = QGroupBox("处理统计")
        stats_layout = QHBoxLayout(stats_group)

        self.total_label = self._create_stat_label("总文件数", "0")
        self.processed_label = self._create_stat_label("已处理", "0", "#4CAF50")
        self.skipped_label = self._create_stat_label("已跳过", "0", "#FF9800")
        self.failed_label = self._create_stat_label("失败", "0", "#F44336")

        stats_layout.addWidget(self.total_label)
        stats_layout.addWidget(self.processed_label)
        stats_layout.addWidget(self.skipped_label)
        stats_layout.addWidget(self.failed_label)

        layout.addWidget(stats_group)

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("日志级别:"))
        self.level_combo = QComboBox()
        self.level_combo.addItems(["全部", "信息", "警告", "错误", "成功"])
        self.level_combo.currentIndexChanged.connect(self._filter_logs)
        filter_layout.addWidget(self.level_combo)

        filter_layout.addSpacing(20)

        filter_layout.addWidget(QLabel("日志类型:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(["全部", "扫描", "处理", "跳过", "打包", "系统"])
        self.type_combo.currentIndexChanged.connect(self._filter_logs)
        filter_layout.addWidget(self.type_combo)

        filter_layout.addStretch()

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.refresh_logs)
        filter_layout.addWidget(self.refresh_btn)

        self.export_log_btn = QPushButton("导出日志")
        self.export_log_btn.clicked.connect(self._export_current_logs)
        filter_layout.addWidget(self.export_log_btn)

        self.clear_btn = QPushButton("清空日志")
        self.clear_btn.clicked.connect(self._clear_logs)
        filter_layout.addWidget(self.clear_btn)

        layout.addLayout(filter_layout)

        splitter = QSplitter(Qt.Vertical)

        log_table_group = QGroupBox("日志列表")
        log_table_layout = QVBoxLayout(log_table_group)

        self.log_table = QTableWidget()
        self.log_table.setColumnCount(4)
        self.log_table.setHorizontalHeaderLabels(["时间", "级别", "类型", "消息"])
        self.log_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.log_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.log_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.log_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.log_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.log_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.log_table.setAlternatingRowColors(True)
        self.log_table.itemClicked.connect(self._on_log_clicked)
        log_table_layout.addWidget(self.log_table)

        splitter.addWidget(log_table_group)

        detail_group = QGroupBox("详细信息")
        detail_layout = QVBoxLayout(detail_group)

        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setPlaceholderText("点击日志条目查看详细信息...")
        detail_layout.addWidget(self.detail_text)

        splitter.addWidget(detail_group)
        splitter.setSizes([400, 200])

        layout.addWidget(splitter, 1)

        skip_group = QGroupBox("跳过原因统计")
        skip_layout = QVBoxLayout(skip_group)

        self.skip_stats = QTextEdit()
        self.skip_stats.setReadOnly(True)
        self.skip_stats.setMaximumHeight(120)
        skip_layout.addWidget(self.skip_stats)

        layout.addWidget(skip_group)

        self.tabs.addTab(widget, "📝 实时日志")

    def _create_stat_label(self, title: str, value: str, color: str = "#333") -> QLabel:
        label = QLabel()
        label.setAlignment(Qt.AlignCenter)
        label.setText(f"<div style='font-size: 20px; font-weight: bold; color: {color};'>{value}</div>"
                      f"<div style='font-size: 12px; color: #666;'>{title}</div>")
        label.setStyleSheet("QLabel { padding: 10px; background: #f5f5f5; border-radius: 6px; }")
        return label

    def refresh_history(self):
        self.project_list.clear()
        projects = self.history.get_all_projects()
        self.total_projects_label.setText(f"共 {len(projects)} 个项目")

        all_item = QListWidgetItem("📋 全部项目")
        all_item.setData(Qt.UserRole, "__all__")
        self.project_list.addItem(all_item)

        for proj in projects:
            records = self.history.get_records_by_project(proj)
            item = QListWidgetItem(f"📷 {proj}  ({len(records)} 次)")
            item.setData(Qt.UserRole, proj)
            self.project_list.addItem(item)

        if self.project_list.count() > 0:
            self.project_list.setCurrentRow(0)
            self._on_project_clicked(self.project_list.item(0))

        self._populate_records_table(self.history.records)

    def _on_project_clicked(self, item):
        project_name = item.data(Qt.UserRole)
        if project_name == "__all__":
            records = self.history.records
        else:
            records = self.history.get_records_by_project(project_name)

        records = list(reversed(records))
        self._populate_records_table(records)

    def _apply_date_filter(self):
        start = self.start_date.date().toString("yyyy-MM-dd")
        end = self.end_date.date().toString("yyyy-MM-dd")

        current_item = self.project_list.currentItem()
        if current_item:
            project_name = current_item.data(Qt.UserRole)
        else:
            project_name = "__all__"

        if project_name == "__all__":
            all_records = self.history.records
        else:
            all_records = self.history.get_records_by_project(project_name)

        filtered = [
            r for r in all_records
            if start <= r.timestamp[:10] <= end
        ]

        filtered = list(reversed(filtered))
        self._populate_records_table(filtered)

    def _reset_date_filter(self):
        self.start_date.setDate(QDate.currentDate().addDays(-30))
        self.end_date.setDate(QDate.currentDate())
        self.refresh_history()

    def _populate_records_table(self, records):
        self.records_table.setRowCount(len(records))
        self.records_count_label.setText(f"共 {len(records)} 条记录")

        for row, record in enumerate(records):
            self.records_table.setItem(row, 0, QTableWidgetItem(record.timestamp))
            self.records_table.setItem(row, 1, QTableWidgetItem(record.project_name))

            status_item = QTableWidgetItem("成功" if record.status == "success" else "失败")
            if record.status == "success":
                status_item.setForeground(QColor("#4CAF50"))
            else:
                status_item.setForeground(QColor("#F44336"))
            self.records_table.setItem(row, 2, status_item)

            self.records_table.setItem(row, 3, QTableWidgetItem(str(record.total_photos)))

            summary = f"{record.processed} / {record.skipped} / {record.failed}"
            self.records_table.setItem(row, 4, QTableWidgetItem(summary))

        if records:
            self.records_table.setCurrentCell(0, 0)
            self._show_record_detail(records[0])
        else:
            self.record_detail.setPlainText("暂无记录")

    def _on_record_clicked(self, item):
        row = item.row()
        if row < 0 or row >= self.records_table.rowCount():
            return

        project_item = self.records_table.item(row, 1)
        time_item = self.records_table.item(row, 0)
        if not project_item or not time_item:
            return

        project_name = project_item.text()
        timestamp = time_item.text()

        records = self.history.get_records_by_project(project_name)
        for r in records:
            if r.timestamp == timestamp:
                self._show_record_detail(r)
                break

    def _show_record_detail(self, record: PackageRecord):
        detail = f"""项目名称: {record.project_name}
客户姓名: {record.client_name or '未填写'}
拍摄日期: {record.shoot_date or '未识别'}
打包时间: {record.timestamp}
状态: {'成功' if record.status == 'success' else '失败'}
输出路径: {record.package_path}

━━━━ 统计 ━━━━
  总照片数: {record.total_photos}
  成功处理: {record.processed}
  跳过数量: {record.skipped}
  失败数量: {record.failed}
"""
        if record.skip_reasons:
            detail += "\n━━━━ 跳过原因 ━━━━\n"
            for reason, count in sorted(record.skip_reasons.items(), key=lambda x: -x[1]):
                detail += f"  • {reason}: {count} 个\n"

        if record.failed_files:
            detail += "\n━━━━ 失败文件 ━━━━\n"
            for f in record.failed_files:
                detail += f"  ❌ {f.get('filename', '?')}: {f.get('error', '?')}\n"

        self.record_detail.setPlainText(detail)

    def _export_selected_record(self):
        current_row = self.records_table.currentRow()
        if current_row < 0:
            QMessageBox.information(self, "提示", "请先选择一条记录")
            return

        project_item = self.records_table.item(current_row, 1)
        time_item = self.records_table.item(current_row, 0)
        if not project_item or not time_item:
            return

        project_name = project_item.text()
        timestamp = time_item.text()

        records = self.history.get_records_by_project(project_name)
        target = None
        for r in records:
            if r.timestamp == timestamp:
                target = r
                break

        if not target:
            QMessageBox.warning(self, "提示", "未找到对应记录")
            return

        from PySide6.QtWidgets import QFileDialog
        import json
        default_name = f"{target.record_id}_报告.txt"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出记录", default_name, "文本文件 (*.txt);;JSON文件 (*.json)"
        )
        if not file_path:
            return

        try:
            if file_path.lower().endswith(".json"):
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(target.to_dict(), f, ensure_ascii=False, indent=2)
            else:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.record_detail.toPlainText())

            QMessageBox.information(self, "成功", f"记录已导出到:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出失败: {str(e)}")

    def refresh_logs(self):
        self._update_stats()
        self._update_skip_stats()
        self._filter_logs()

    def _update_stats(self):
        stats = self.logger.stats
        self.total_label.setText(
            f"<div style='font-size: 20px; font-weight: bold; color: #333;'>{stats.total_files}</div>"
            f"<div style='font-size: 12px; color: #666;'>总文件数</div>"
        )
        self.processed_label.setText(
            f"<div style='font-size: 20px; font-weight: bold; color: #4CAF50;'>{stats.processed_files}</div>"
            f"<div style='font-size: 12px; color: #666;'>已处理</div>"
        )
        self.skipped_label.setText(
            f"<div style='font-size: 20px; font-weight: bold; color: #FF9800;'>{stats.skipped_files}</div>"
            f"<div style='font-size: 12px; color: #666;'>已跳过</div>"
        )
        self.failed_label.setText(
            f"<div style='font-size: 20px; font-weight: bold; color: #F44336;'>{stats.failed_files}</div>"
            f"<div style='font-size: 12px; color: #666;'>失败</div>"
        )

    def _update_skip_stats(self):
        stats = self.logger.stats
        if not stats.skip_reasons:
            self.skip_stats.setPlainText("暂无跳过记录")
            return

        lines = []
        for reason, count in sorted(stats.skip_reasons.items(), key=lambda x: -x[1]):
            lines.append(f"• {reason}: {count} 个文件")

        self.skip_stats.setPlainText("\n".join(lines))

    def _filter_logs(self):
        level_idx = self.level_combo.currentIndex()
        type_idx = self.type_combo.currentIndex()

        level_map = {0: None, 1: "info", 2: "warning", 3: "error", 4: "success"}
        type_map = {0: None, 1: "scan", 2: "process", 3: "skip", 4: "package", 5: "system"}

        target_level = level_map.get(level_idx)
        target_type = type_map.get(type_idx)

        filtered = []
        for entry in self.logger.entries:
            if target_level and entry.level != target_level:
                continue
            if target_type and entry.type != target_type:
                continue
            filtered.append(entry)

        self._populate_table(filtered)

    def _populate_table(self, entries):
        self._current_entries = list(entries)
        self.log_table.setRowCount(len(self._current_entries))

        level_colors = {
            "info": "#2196F3",
            "warning": "#FF9800",
            "error": "#F44336",
            "success": "#4CAF50"
        }
        type_names = {"scan": "扫描", "process": "处理", "skip": "跳过", "package": "打包", "system": "系统"}
        level_names = {"info": "信息", "warning": "警告", "error": "错误", "success": "成功"}

        for row, entry in enumerate(self._current_entries):
            time_item = QTableWidgetItem(entry.timestamp)
            level_item = QTableWidgetItem(level_names.get(entry.level, entry.level))
            type_item = QTableWidgetItem(type_names.get(entry.type, entry.type))
            msg_item = QTableWidgetItem(entry.message)

            color_hex = level_colors.get(entry.level, "#333333")
            level_item.setForeground(QColor(color_hex))

            self.log_table.setItem(row, 0, time_item)
            self.log_table.setItem(row, 1, level_item)
            self.log_table.setItem(row, 2, type_item)
            self.log_table.setItem(row, 3, msg_item)

        self.detail_text.clear()

    def _on_log_clicked(self, item):
        row = item.row()
        if row < 0 or row >= len(self._current_entries):
            return

        entry = self._current_entries[row]
        if not entry:
            return

        level_names = {"info": "信息", "warning": "警告", "error": "错误", "success": "成功"}
        type_names = {"scan": "扫描", "process": "处理", "skip": "跳过", "package": "打包", "system": "系统"}

        details_text = f"时间: {entry.timestamp}\n"
        details_text += f"级别: {level_names.get(entry.level, entry.level)}\n"
        details_text += f"类型: {type_names.get(entry.type, entry.type)}\n"
        details_text += f"消息: {entry.message}\n"

        if entry.details:
            details_text += "\n详细信息:\n"
            for key, value in entry.details.items():
                details_text += f"  {key}: {value}\n"

        self.detail_text.setPlainText(details_text)

    def _export_current_logs(self):
        if not self.logger.entries:
            QMessageBox.information(self, "提示", "暂无日志可导出")
            return

        try:
            log_path = self.logger.save_logs()
            if log_path:
                QMessageBox.information(self, "成功", f"日志已导出到:\n{log_path}")
            else:
                QMessageBox.warning(self, "提示", "请先设置日志目录")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出失败: {str(e)}")

    def _clear_logs(self):
        reply = QMessageBox.question(
            self, "确认", "确定要清空所有实时日志吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.logger.entries = []
            self.logger.reset_stats()
            self.refresh_logs()
            self.detail_text.clear()
