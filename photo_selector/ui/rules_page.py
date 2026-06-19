from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit,
    QSpinBox, QCheckBox, QComboBox, QPushButton, QSlider, QFormLayout,
    QMessageBox, QFileDialog
)
from PySide6.QtCore import Signal, Qt

from ..rules import RulesConfig


class RulesPage(QWidget):
    rules_changed = Signal()

    def __init__(self, rules: RulesConfig, parent=None):
        super().__init__(parent)
        self.rules = rules
        self._init_ui()
        self._load_rules()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        thumb_group = QGroupBox("缩略图设置")
        thumb_layout = QFormLayout(thumb_group)

        self.thumb_width = QSpinBox()
        self.thumb_width.setRange(100, 4000)
        self.thumb_width.setSuffix(" px")
        thumb_layout.addRow("宽度:", self.thumb_width)

        self.thumb_height = QSpinBox()
        self.thumb_height.setRange(100, 4000)
        self.thumb_height.setSuffix(" px")
        thumb_layout.addRow("高度:", self.thumb_height)

        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(1, 100)
        self.quality_spin.setSuffix(" %")
        thumb_layout.addRow("JPEG质量:", self.quality_spin)

        layout.addWidget(thumb_group)

        watermark_group = QGroupBox("水印设置")
        watermark_layout = QVBoxLayout(watermark_group)

        self.watermark_enabled = QCheckBox("启用水印")
        watermark_layout.addWidget(self.watermark_enabled)

        wm_form = QFormLayout()
        self.watermark_text = QLineEdit()
        self.watermark_text.setPlaceholderText("请输入水印文字")
        wm_form.addRow("水印文字:", self.watermark_text)

        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(10, 100)
        self.opacity_label = QLabel("50%")
        opacity_layout = QHBoxLayout()
        opacity_layout.addWidget(self.opacity_slider)
        opacity_layout.addWidget(self.opacity_label)
        wm_form.addRow("透明度:", opacity_layout)

        self.opacity_slider.valueChanged.connect(
            lambda v: self.opacity_label.setText(f"{v}%")
        )

        watermark_layout.addLayout(wm_form)
        layout.addWidget(watermark_group)

        selection_group = QGroupBox("选片规则")
        selection_layout = QFormLayout(selection_group)

        self.max_selection = QSpinBox()
        self.max_selection.setRange(1, 1000)
        selection_layout.addRow("入选上限:", self.max_selection)

        self.include_raw = QCheckBox("包含RAW格式原片")
        selection_layout.addRow("", self.include_raw)

        layout.addWidget(selection_group)

        naming_group = QGroupBox("文件命名")
        naming_layout = QVBoxLayout(naming_group)

        self.naming_pattern = QLineEdit()
        self.naming_pattern.setPlaceholderText("{client}_{date}_{index:04d}")
        naming_layout.addWidget(QLabel("命名模板:"))
        naming_layout.addWidget(self.naming_pattern)

        hint = QLabel("可用变量: {client} 客户名, {date} 日期, {index} 序号, {original} 原名")
        hint.setStyleSheet("color: gray; font-size: 11px;")
        naming_layout.addWidget(hint)

        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("输出格式:"))
        self.output_format = QComboBox()
        self.output_format.addItems(["jpg", "png", "保持原格式"])
        format_layout.addWidget(self.output_format)
        format_layout.addStretch()
        naming_layout.addLayout(format_layout)

        layout.addWidget(naming_group)

        expire_group = QGroupBox("过期提示")
        expire_layout = QHBoxLayout(expire_group)

        self.expire_enabled = QCheckBox("启用过期提醒")
        expire_layout.addWidget(self.expire_enabled)

        expire_layout.addWidget(QLabel("有效期:"))
        self.expire_days = QSpinBox()
        self.expire_days.setRange(1, 365)
        self.expire_days.setSuffix(" 天")
        expire_layout.addWidget(self.expire_days)
        expire_layout.addStretch()

        layout.addWidget(expire_group)

        btn_layout = QHBoxLayout()

        self.load_btn = QPushButton("加载配置")
        self.load_btn.clicked.connect(self._load_config_file)
        btn_layout.addWidget(self.load_btn)

        self.save_btn = QPushButton("保存配置")
        self.save_btn.clicked.connect(self._save_config_file)
        btn_layout.addWidget(self.save_btn)

        self.default_btn = QPushButton("恢复默认")
        self.default_btn.clicked.connect(self._reset_defaults)
        btn_layout.addWidget(self.default_btn)

        btn_layout.addStretch()

        self.apply_btn = QPushButton("应用规则")
        self.apply_btn.clicked.connect(self._apply_rules)
        self.apply_btn.setStyleSheet("QPushButton { background: #4CAF50; color: white; padding: 8px 20px; }")
        btn_layout.addWidget(self.apply_btn)

        layout.addLayout(btn_layout)
        layout.addStretch()

        self.watermark_enabled.toggled.connect(self._update_watermark_state)

    def _update_watermark_state(self, enabled):
        self.watermark_text.setEnabled(enabled)
        self.opacity_slider.setEnabled(enabled)

    def _load_rules(self):
        self.thumb_width.setValue(self.rules.thumbnail_width)
        self.thumb_height.setValue(self.rules.thumbnail_height)
        self.quality_spin.setValue(self.rules.jpeg_quality)
        self.watermark_enabled.setChecked(self.rules.watermark_enabled)
        self.watermark_text.setText(self.rules.watermark_text)
        self.opacity_slider.setValue(self.rules.watermark_opacity)
        self.max_selection.setValue(self.rules.max_selection)
        self.include_raw.setChecked(self.rules.include_raw)
        self.naming_pattern.setText(self.rules.naming_pattern)

        if self.rules.output_format == "jpg":
            self.output_format.setCurrentIndex(0)
        elif self.rules.output_format == "png":
            self.output_format.setCurrentIndex(1)
        else:
            self.output_format.setCurrentIndex(2)

        self.expire_enabled.setChecked(self.rules.expire_enabled)
        self.expire_days.setValue(self.rules.expire_days)

        self._update_watermark_state(self.rules.watermark_enabled)

    def _apply_rules(self):
        self.rules.thumbnail_width = self.thumb_width.value()
        self.rules.thumbnail_height = self.thumb_height.value()
        self.rules.jpeg_quality = self.quality_spin.value()
        self.rules.watermark_enabled = self.watermark_enabled.isChecked()
        self.rules.watermark_text = self.watermark_text.text() or "摄影工作室"
        self.rules.watermark_opacity = self.opacity_slider.value()
        self.rules.max_selection = self.max_selection.value()
        self.rules.include_raw = self.include_raw.isChecked()
        self.rules.naming_pattern = self.naming_pattern.text() or "{client}_{date}_{index:04d}"

        fmt = self.output_format.currentIndex()
        if fmt == 0:
            self.rules.output_format = "jpg"
        elif fmt == 1:
            self.rules.output_format = "png"
        else:
            self.rules.output_format = "original"

        self.rules.expire_enabled = self.expire_enabled.isChecked()
        self.rules.expire_days = self.expire_days.value()

        self.rules_changed.emit()
        QMessageBox.information(self, "提示", "规则已应用")

    def _save_config_file(self):
        self._apply_rules_silent()
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存配置", "rules_config.json", "JSON文件 (*.json)"
        )
        if file_path:
            self.rules.save_to_file(file_path)
            QMessageBox.information(self, "提示", "配置已保存")

    def _load_config_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "加载配置", "", "JSON文件 (*.json)"
        )
        if file_path:
            self.rules = RulesConfig.load_from_file(file_path)
            self._load_rules()
            self.rules_changed.emit()
            QMessageBox.information(self, "提示", "配置已加载")

    def _reset_defaults(self):
        reply = QMessageBox.question(
            self, "确认", "确定要恢复默认设置吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.rules.apply_defaults()
            self._load_rules()
            self.rules_changed.emit()

    def _apply_rules_silent(self):
        self.rules.thumbnail_width = self.thumb_width.value()
        self.rules.thumbnail_height = self.thumb_height.value()
        self.rules.jpeg_quality = self.quality_spin.value()
        self.rules.watermark_enabled = self.watermark_enabled.isChecked()
        self.rules.watermark_text = self.watermark_text.text() or "摄影工作室"
        self.rules.watermark_opacity = self.opacity_slider.value()
        self.rules.max_selection = self.max_selection.value()
        self.rules.include_raw = self.include_raw.isChecked()
        self.rules.naming_pattern = self.naming_pattern.text() or "{client}_{date}_{index:04d}"

        fmt = self.output_format.currentIndex()
        if fmt == 0:
            self.rules.output_format = "jpg"
        elif fmt == 1:
            self.rules.output_format = "png"
        else:
            self.rules.output_format = "original"

        self.rules.expire_enabled = self.expire_enabled.isChecked()
        self.rules.expire_days = self.expire_days.value()
