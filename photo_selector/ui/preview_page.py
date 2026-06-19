import os
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QSplitter, QScrollArea, QFrame, QGridLayout, QMessageBox, QPushButton,
    QComboBox, QGroupBox, QCheckBox
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QImage, QIcon

from ..scanner import FileScanner, ProjectItem
from ..rules import RulesConfig
from ..image_processor import ImageProcessor


class PreviewPage(QWidget):
    def __init__(self, scanner: FileScanner, rules: RulesConfig, parent=None):
        super().__init__(parent)
        self.scanner = scanner
        self.rules = rules
        self.image_processor = ImageProcessor()
        self.current_project: ProjectItem = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("选择项目:"))

        self.project_combo = QComboBox()
        self.project_combo.currentIndexChanged.connect(self._on_project_changed)
        top_layout.addWidget(self.project_combo)

        top_layout.addStretch()

        self.refresh_btn = QPushButton("刷新预览")
        self.refresh_btn.clicked.connect(self.refresh_preview)
        top_layout.addWidget(self.refresh_btn)

        layout.addLayout(top_layout)

        splitter = QSplitter(Qt.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        cover_group = QGroupBox("封面预览")
        cover_layout = QVBoxLayout(cover_group)

        self.cover_label = QLabel()
        self.cover_label.setAlignment(Qt.AlignCenter)
        self.cover_label.setMinimumSize(400, 300)
        self.cover_label.setStyleSheet("QLabel { background: #222; border: 2px solid #555; }")
        self.cover_label.setText("暂无封面")
        self.cover_label.setStyleSheet("QLabel { background: #222; color: #888; border: 2px solid #555; }")
        cover_layout.addWidget(self.cover_label)

        left_layout.addWidget(cover_group)

        info_group = QGroupBox("项目信息")
        info_layout = QVBoxLayout(info_group)
        self.info_label = QLabel("请选择项目查看信息")
        self.info_label.setWordWrap(True)
        info_layout.addWidget(self.info_label)
        left_layout.addWidget(info_group)

        warning_group = QGroupBox("⚠️ 警告信息")
        warning_layout = QVBoxLayout(warning_group)
        self.warning_label = QLabel("暂无警告")
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet("QLabel { color: #666; }")
        warning_layout.addWidget(self.warning_label)
        left_layout.addWidget(warning_group)

        splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        right_layout.addWidget(QLabel("照片列表 (点击预览):"))

        self.photos_list = QListWidget()
        self.photos_list.setViewMode(QListWidget.IconMode)
        self.photos_list.setIconSize(QSize(120, 90))
        self.photos_list.setResizeMode(QListWidget.Adjust)
        self.photos_list.setMovement(QListWidget.Static)
        self.photos_list.setSpacing(8)
        self.photos_list.itemClicked.connect(self._on_photo_clicked)
        right_layout.addWidget(self.photos_list, 1)

        splitter.addWidget(right_panel)
        splitter.setSizes([450, 550])

        layout.addWidget(splitter, 1)

    def refresh_projects(self):
        self.project_combo.blockSignals(True)
        self.project_combo.clear()

        for project in self.scanner.projects:
            self.project_combo.addItem(f"{project.name} ({project.photo_count}张)", project.name)

        self.project_combo.blockSignals(False)

        if self.scanner.projects:
            self.project_combo.setCurrentIndex(0)
            self._on_project_changed(0)
        else:
            self.cover_label.setText("暂无数据")
            self.photos_list.clear()

    def _on_project_changed(self, index):
        if index < 0 or not self.scanner.projects:
            return

        project_name = self.project_combo.itemData(index)
        self.current_project = self.scanner.get_project_by_name(project_name)

        if self.current_project:
            self._update_project_info()
            self._update_warnings()
            self._load_cover()
            self._load_photo_thumbs()

    def _update_project_info(self):
        if not self.current_project:
            return

        p = self.current_project
        size_mb = p.total_size / (1024 * 1024)

        info = f"""
        <b>项目名称:</b> {p.name}<br>
        <b>客户姓名:</b> {p.client_name or '未识别'}<br>
        <b>拍摄日期:</b> {p.shoot_date or '未识别'}<br>
        <b>照片数量:</b> {p.photo_count} 张<br>
        <b>总大小:</b> {size_mb:.2f} MB<br>
        <b>入选上限:</b> {self.rules.max_selection} 张
        """
        self.info_label.setText(info)

    def _update_warnings(self):
        if not self.current_project:
            return

        warnings = []

        if self.current_project.photo_count == 0:
            warnings.append("❌ 该项目没有任何照片")

        if not self.current_project.cover_path:
            warnings.append("⚠️ 缺少封面照片")

        if not self.current_project.client_name:
            warnings.append("⚠️ 未能识别客户姓名")

        if not self.current_project.shoot_date:
            warnings.append("⚠️ 未能识别拍摄日期")

        if self.current_project.photo_count > self.rules.max_selection * 3:
            warnings.append(f"ℹ️ 照片数量较多 ({self.current_project.photo_count}张)，建议分批处理")

        raw_count = 0
        image_count = 0
        for photo in self.current_project.photos:
            ext = photo.path.suffix.lower()
            if ext in {'.raw', '.cr2', '.nef', '.arw', '.dng', '.rw2'}:
                raw_count += 1
            else:
                image_count += 1

        if raw_count > 0 and not self.rules.include_raw:
            warnings.append(f"ℹ️ 包含 {raw_count} 个RAW文件，当前设置不包含RAW原片")

        if warnings:
            self.warning_label.setText("<br>".join(warnings))
            self.warning_label.setStyleSheet("QLabel { color: #d35400; }")
        else:
            self.warning_label.setText("✓ 一切正常")
            self.warning_label.setStyleSheet("QLabel { color: #27ae60; }")

    def _load_cover(self):
        if not self.current_project or not self.current_project.cover_path:
            self.cover_label.setText("暂无封面")
            return

        cover_path = self.current_project.cover_path
        if not cover_path.exists():
            self.cover_label.setText("封面文件不存在")
            return

        try:
            pixmap = QPixmap(str(cover_path))
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    self.cover_label.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.cover_label.setPixmap(scaled)
            else:
                self.cover_label.setText("无法加载封面")
        except Exception:
            self.cover_label.setText("加载封面失败")

    def _load_photo_thumbs(self):
        self.photos_list.clear()

        if not self.current_project:
            return

        for i, photo in enumerate(self.current_project.photos, 1):
            try:
                pixmap = QPixmap(str(photo.path))
                if not pixmap.isNull():
                    icon = QIcon(pixmap.scaled(120, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                    item = QListWidgetItem(icon, f"{i:04d}")
                    item.setData(Qt.UserRole, str(photo.path))
                    self.photos_list.addItem(item)
                else:
                    item = QListWidgetItem(f"❌ {i:04d}")
                    self.photos_list.addItem(item)
            except Exception:
                item = QListWidgetItem(f"❌ {i:04d}")
                self.photos_list.addItem(item)

    def _on_photo_clicked(self, item):
        photo_path = item.data(Qt.UserRole)
        if photo_path and Path(photo_path).exists():
            try:
                pixmap = QPixmap(photo_path)
                if not pixmap.isNull():
                    scaled = pixmap.scaled(
                        self.cover_label.size(),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )
                    self.cover_label.setPixmap(scaled)
            except Exception:
                pass

    def refresh_preview(self):
        if self.current_project:
            self._update_project_info()
            self._update_warnings()
            self._load_cover()
