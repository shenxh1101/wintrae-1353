import os
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QFileDialog, QComboBox, QGroupBox, QCheckBox, QProgressBar, QMessageBox,
    QListWidget, QListWidgetItem, QTextEdit, QSplitter
)
from PySide6.QtCore import Signal, Qt, QThread

from ..scanner import FileScanner, ProjectItem
from ..rules import RulesConfig
from ..packager import PackageGenerator
from ..logger import Logger


class PackageThread(QThread):
    progress = Signal(int, str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, packager: PackageGenerator, project: ProjectItem, output_dir: str, make_zip: bool):
        super().__init__()
        self.packager = packager
        self.project = project
        self.output_dir = output_dir
        self.make_zip = make_zip

    def run(self):
        try:
            self.progress.emit(10, "正在生成选片包...")
            package_path = self.packager.generate_package(self.project, self.output_dir)
            self.progress.emit(80, "选片包生成完成")

            if self.make_zip:
                self.progress.emit(90, "正在生成压缩包...")
                self.packager.generate_zip(package_path)
                self.progress.emit(100, "压缩包生成完成")
            else:
                self.progress.emit(100, "完成")

            self.finished.emit(str(package_path))
        except Exception as e:
            self.error.emit(str(e))


class OutputPage(QWidget):
    package_generated = Signal(str)

    def __init__(
        self,
        scanner: FileScanner,
        rules: RulesConfig,
        packager: PackageGenerator,
        logger: Logger,
        parent=None
    ):
        super().__init__(parent)
        self.scanner = scanner
        self.rules = rules
        self.packager = packager
        self.logger = logger
        self.package_thread = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        top_splitter = QSplitter(Qt.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        project_group = QGroupBox("选择项目")
        project_layout = QVBoxLayout(project_group)

        self.project_combo = QComboBox()
        project_layout.addWidget(self.project_combo)

        self.project_info = QLabel("请选择要打包的项目")
        self.project_info.setWordWrap(True)
        self.project_info.setStyleSheet("QLabel { padding: 8px; background: #f5f5f5; border-radius: 4px; }")
        project_layout.addWidget(self.project_info)

        left_layout.addWidget(project_group)

        output_group = QGroupBox("输出设置")
        output_layout = QVBoxLayout(output_group)

        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("输出目录:"))
        self.output_dir_input = QLineEdit()
        self.output_dir_input.setPlaceholderText("请选择输出目录...")
        dir_layout.addWidget(self.output_dir_input)

        self.browse_btn = QPushButton("浏览...")
        self.browse_btn.clicked.connect(self._browse_output_dir)
        dir_layout.addWidget(self.browse_btn)
        output_layout.addLayout(dir_layout)

        self.zip_checkbox = QCheckBox("同时生成 ZIP 压缩包")
        self.zip_checkbox.setChecked(True)
        output_layout.addWidget(self.zip_checkbox)

        self.log_dir_checkbox = QCheckBox("输出日志文件")
        self.log_dir_checkbox.setChecked(True)
        output_layout.addWidget(self.log_dir_checkbox)

        left_layout.addWidget(output_group)

        action_group = QGroupBox("操作")
        action_layout = QVBoxLayout(action_group)

        self.generate_btn = QPushButton("📦 生成选片包")
        self.generate_btn.clicked.connect(self._generate_package)
        self.generate_btn.setStyleSheet(
            "QPushButton { background: #2196F3; color: white; padding: 12px; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background: #1976D2; }"
            "QPushButton:disabled { background: #BDBDBD; }"
        )
        action_layout.addWidget(self.generate_btn)

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

        top_splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        preview_group = QGroupBox("生成预览 (内容结构)")
        preview_layout = QVBoxLayout(preview_group)

        self.structure_preview = QListWidget()
        preview_layout.addWidget(self.structure_preview)

        right_layout.addWidget(preview_group, 1)

        summary_group = QGroupBox("生成内容说明")
        summary_layout = QVBoxLayout(summary_group)

        summary_text = QLabel(
            "选片包包含以下内容:\n"
            "• cover.jpg - 封面图片\n"
            "• 客户说明.txt - 给客户的说明文档\n"
            "• 回传清单.txt - 选片回传模板\n"
            "• manifest.json - 数据清单(程序读取)\n"
            "• thumbnails/ - 带水印缩略图(供选片)\n"
            "• originals/ - 高清原片(入选后交付)"
        )
        summary_text.setWordWrap(True)
        summary_text.setStyleSheet("QLabel { color: #555; line-height: 1.6; }")
        summary_layout.addWidget(summary_text)

        right_layout.addWidget(summary_group)

        top_splitter.addWidget(right_panel)
        top_splitter.setSizes([400, 500])

        layout.addWidget(top_splitter, 1)

        self.project_combo.currentIndexChanged.connect(self._on_project_changed)

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
            self.project_info.setText("暂无项目，请先扫描")
            self.structure_preview.clear()

    def _on_project_changed(self, index):
        if index < 0:
            return

        project_name = self.project_combo.itemData(index)
        project = self.scanner.get_project_by_name(project_name)

        if project:
            size_mb = project.total_size / (1024 * 1024)
            info = (
                f"照片数量: {project.photo_count} 张\n"
                f"预计大小: {size_mb * 1.2:.1f} MB (含缩略图)\n"
                f"入选上限: {self.rules.max_selection} 张"
            )
            self.project_info.setText(info)
            self._update_structure_preview(project)

    def _update_structure_preview(self, project: ProjectItem):
        self.structure_preview.clear()

        package_name = f"{project.shoot_date or 'date'}_{project.client_name or project.name}_选片包"

        items = [
            f"📁 {package_name}/",
            f"  📄 cover.jpg",
            f"  📄 客户说明.txt",
            f"  📄 回传清单.txt",
            f"  📄 manifest.json",
            f"  📁 thumbnails/ ({project.photo_count} 张缩略图)",
            f"  📁 originals/ ({project.photo_count} 张原片)",
        ]

        for item_text in items:
            item = QListWidgetItem(item_text)
            if item_text.startswith("📁"):
                item.setForeground(Qt.darkBlue)
            self.structure_preview.addItem(item)

    def _browse_output_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if dir_path:
            self.output_dir_input.setText(dir_path)

    def _generate_package(self):
        if self.package_thread and self.package_thread.isRunning():
            return

        project_index = self.project_combo.currentIndex()
        if project_index < 0:
            QMessageBox.warning(self, "提示", "请先选择项目")
            return

        output_dir = self.output_dir_input.text().strip()
        if not output_dir:
            QMessageBox.warning(self, "提示", "请选择输出目录")
            return

        if not Path(output_dir).exists():
            QMessageBox.warning(self, "错误", "输出目录不存在")
            return

        project_name = self.project_combo.itemData(project_index)
        project = self.scanner.get_project_by_name(project_name)

        if not project or project.photo_count == 0:
            QMessageBox.warning(self, "提示", "该项目没有照片")
            return

        if self.log_dir_checkbox.isChecked():
            self.logger.set_log_directory(str(Path(output_dir) / "logs"))

        self.generate_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("正在生成...")

        self.package_thread = PackageThread(
            self.packager,
            project,
            output_dir,
            self.zip_checkbox.isChecked()
        )
        self.package_thread.progress.connect(self._on_progress)
        self.package_thread.finished.connect(self._on_finished)
        self.package_thread.error.connect(self._on_error)
        self.package_thread.start()

    def _on_progress(self, value, message):
        self.progress_bar.setValue(value)
        self.status_label.setText(message)

    def _on_finished(self, package_path):
        self.generate_btn.setEnabled(True)
        self.progress_bar.setValue(100)
        self.status_label.setText("生成完成！")

        self.package_generated.emit(package_path)

        QMessageBox.information(
            self, "完成",
            f"选片包已生成:\n{package_path}\n\n"
            f"处理: {self.logger.stats.processed_files} 张\n"
            f"跳过: {self.logger.stats.skipped_files} 张\n"
            f"失败: {self.logger.stats.failed_files} 张"
        )

    def _on_error(self, error_msg):
        self.generate_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("生成失败")
        QMessageBox.critical(self, "错误", f"生成失败: {error_msg}")

    def _open_output_dir(self):
        output_dir = self.output_dir_input.text().strip()
        if output_dir and Path(output_dir).exists():
            try:
                os.startfile(output_dir)
            except Exception:
                QMessageBox.information(self, "提示", f"输出目录:\n{output_dir}")
        else:
            QMessageBox.warning(self, "提示", "请先设置输出目录")
