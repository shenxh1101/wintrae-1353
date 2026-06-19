from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox, QTextEdit,
    QSplitter, QAbstractItemView, QMessageBox
)
from PySide6.QtCore import Qt

from ..logger import Logger, LogLevel, LogType


class LogPage(QWidget):
    def __init__(self, logger: Logger, parent=None):
        super().__init__(parent)
        self.logger = logger
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
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

        self.export_btn = QPushButton("导出日志")
        self.export_btn.clicked.connect(self._export_logs)
        filter_layout.addWidget(self.export_btn)

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

    def _create_stat_label(self, title: str, value: str, color: str = "#333") -> QLabel:
        label = QLabel()
        label.setAlignment(Qt.AlignCenter)
        label.setText(f"<div style='font-size: 20px; font-weight: bold; color: {color};'>{value}</div>"
                      f"<div style='font-size: 12px; color: #666;'>{title}</div>")
        label.setStyleSheet("QLabel { padding: 10px; background: #f5f5f5; border-radius: 6px; }")
        return label

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

        level_map = {
            0: None,
            1: "info",
            2: "warning",
            3: "error",
            4: "success"
        }
        type_map = {
            0: None,
            1: "scan",
            2: "process",
            3: "skip",
            4: "package",
            5: "system"
        }

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
        self.log_table.setRowCount(len(entries))

        level_colors = {
            "info": "#2196F3",
            "warning": "#FF9800",
            "error": "#F44336",
            "success": "#4CAF50"
        }

        type_names = {
            "scan": "扫描",
            "process": "处理",
            "skip": "跳过",
            "package": "打包",
            "system": "系统"
        }

        level_names = {
            "info": "信息",
            "warning": "警告",
            "error": "错误",
            "success": "成功"
        }

        for row, entry in enumerate(entries):
            time_item = QTableWidgetItem(entry.timestamp)
            level_item = QTableWidgetItem(level_names.get(entry.level, entry.level))
            type_item = QTableWidgetItem(type_names.get(entry.type, entry.type))
            msg_item = QTableWidgetItem(entry.message)

            color = level_colors.get(entry.level, "#333")
            level_item.setForeground(Qt.GlobalColor(color) if isinstance(color, str) else color)

            self.log_table.setItem(row, 0, time_item)
            self.log_table.setItem(row, 1, level_item)
            self.log_table.setItem(row, 2, type_item)
            self.log_table.setItem(row, 3, msg_item)

    def _on_log_clicked(self, item):
        row = item.row()
        if row >= len(self.logger.entries):
            return

        entry = self.logger.entries[-(row + 1)] if row < len(self.logger.entries) else None
        if not entry:
            return

        details_text = f"时间: {entry.timestamp}\n"
        details_text += f"级别: {entry.level}\n"
        details_text += f"类型: {entry.type}\n"
        details_text += f"消息: {entry.message}\n"

        if entry.details:
            details_text += "\n详细信息:\n"
            for key, value in entry.details.items():
                details_text += f"  {key}: {value}\n"

        self.detail_text.setPlainText(details_text)

    def _export_logs(self):
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
            self, "确认", "确定要清空所有日志吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.logger.entries = []
            self.logger.reset_stats()
            self.refresh_logs()
            self.detail_text.clear()
