from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QFileDialog, QListWidget, QListWidgetItem, QComboBox, QGroupBox,
    QSplitter, QMessageBox, QProgressBar
)
from PySide6.QtCore import Signal, Qt, QThread
from PySide6.QtGui import QPixmap, QIcon

from ..scanner import FileScanner, ProjectItem


class ScanThread(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, scanner: FileScanner):
        super().__init__()
        self.scanner = scanner

    def run(self):
        try:
            projects = self.scanner.scan()
            self.finished.emit(projects)
        except Exception as e:
            self.error.emit(str(e))


class ScanPage(QWidget):
    projects_updated = Signal()

    def __init__(self, scanner: FileScanner, parent=None):
        super().__init__(parent)
        self.scanner = scanner
        self.scan_thread = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        dir_group = QGroupBox("源目录设置")
        dir_layout = QHBoxLayout(dir_group)

        self.dir_input = QLineEdit()
        self.dir_input.setPlaceholderText("请选择包含原片的目录...")
        dir_layout.addWidget(self.dir_input)

        self.browse_btn = QPushButton("浏览...")
        self.browse_btn.clicked.connect(self._browse_directory)
        dir_layout.addWidget(self.browse_btn)

        self.scan_btn = QPushButton("开始扫描")
        self.scan_btn.clicked.connect(self._start_scan)
        dir_layout.addWidget(self.scan_btn)

        layout.addWidget(dir_group)

        mode_group = QGroupBox("项目识别方式")
        mode_layout = QHBoxLayout(mode_group)

        mode_layout.addWidget(QLabel("识别模式:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([
            "文件名前缀识别",
            "拍摄日期识别",
            "客户姓名识别"
        ])
        self.mode_combo.setCurrentIndex(0)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addStretch()

        layout.addWidget(mode_group)

        splitter = QSplitter(Qt.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_layout.addWidget(QLabel("项目列表:"))
        self.project_list = QListWidget()
        self.project_list.itemClicked.connect(self._on_project_selected)
        left_layout.addWidget(self.project_list)

        self.project_info = QLabel("选择项目查看详情")
        self.project_info.setWordWrap(True)
        self.project_info.setStyleSheet("QLabel { padding: 10px; background: #f0f0f0; border-radius: 4px; }")
        left_layout.addWidget(self.project_info)

        splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        right_layout.addWidget(QLabel("项目内照片:"))
        self.photo_list = QListWidget()
        right_layout.addWidget(self.photo_list)

        splitter.addWidget(right_panel)
        splitter.setSizes([300, 500])

        layout.addWidget(splitter, 1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("请选择原片目录开始扫描")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

    def _browse_directory(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择原片目录")
        if dir_path:
            self.dir_input.setText(dir_path)

    def _on_mode_changed(self, index):
        modes = ["prefix", "date", "client"]
        self.scanner.set_recognize_mode(modes[index])

    def _start_scan(self):
        dir_path = self.dir_input.text().strip()
        if not dir_path:
            QMessageBox.warning(self, "提示", "请先选择原片目录")
            return

        if not Path(dir_path).exists():
            QMessageBox.warning(self, "错误", "目录不存在")
            return

        try:
            self.scanner.set_source_directory(dir_path)
        except Exception as e:
            QMessageBox.critical(self, "错误", str(e))
            return

        modes = ["prefix", "date", "client"]
        self.scanner.set_recognize_mode(modes[self.mode_combo.currentIndex()])

        self.scan_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.status_label.setText("正在扫描...")

        self.scan_thread = ScanThread(self.scanner)
        self.scan_thread.finished.connect(self._on_scan_finished)
        self.scan_thread.error.connect(self._on_scan_error)
        self.scan_thread.start()

    def _on_scan_finished(self, projects):
        self.project_list.clear()
        self.photo_list.clear()

        for project in projects:
            item = QListWidgetItem(f"📷 {project.name} ({project.photo_count}张)")
            item.setData(Qt.UserRole, project.name)
            self.project_list.addItem(item)

        self.scan_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"扫描完成，共 {len(projects)} 个项目，{sum(p.photo_count for p in projects)} 张照片")

        self.projects_updated.emit()

    def _on_scan_error(self, error_msg):
        self.scan_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("扫描失败")
        QMessageBox.critical(self, "扫描错误", error_msg)

    def _on_project_selected(self, item):
        project_name = item.data(Qt.UserRole)
        project = self.scanner.get_project_by_name(project_name)

        if project:
            size_mb = project.total_size / (1024 * 1024)
            info_text = (
                f"项目名称: {project.name}\n"
                f"客户姓名: {project.client_name or '未识别'}\n"
                f"拍摄日期: {project.shoot_date or '未识别'}\n"
                f"照片数量: {project.photo_count} 张\n"
                f"总大小: {size_mb:.2f} MB"
            )
            self.project_info.setText(info_text)

            self.photo_list.clear()
            for i, photo in enumerate(project.photos, 1):
                size_kb = photo.size / 1024
                photo_item = QListWidgetItem(f"{i:04d}. {photo.filename} ({size_kb:.1f} KB)")
                self.photo_list.addItem(photo_item)
