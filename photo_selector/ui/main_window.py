import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QVBoxLayout, QWidget
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt

from ..scanner import FileScanner
from ..rules import RulesConfig
from ..logger import Logger, PackageHistory
from ..packager import PackageGenerator
from ..config import AppConfig
from ..delivery_profile import DeliveryProfileManager
from ..task_queue import TaskQueue
from ..batch_record import BatchHistory


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{AppConfig.APP_NAME} v{AppConfig.APP_VERSION}")
        self.setMinimumSize(1200, 750)

        self.scanner = FileScanner()
        self.rules = RulesConfig()
        self.logger = Logger()
        self.history = PackageHistory()
        self.batch_history = BatchHistory()
        self.profile_manager = DeliveryProfileManager()
        self.task_queue = TaskQueue()
        self.packager = PackageGenerator(self.rules, self.logger)

        self._init_ui()
        self._init_history()

    def _init_history(self):
        import tempfile
        data_dir = Path.home() / ".photo_selector"
        data_dir.mkdir(parents=True, exist_ok=True)

        self.history.set_history_directory(str(data_dir / "history"))
        self.batch_history.set_history_directory(str(data_dir / "batch_history"))
        self.logger.set_log_directory(str(data_dir / "logs"))
        self.profile_manager.set_profile_directory(str(data_dir / "profiles"))
        self.task_queue.set_queue_directory(str(data_dir / "queue"))

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(10, 10, 10, 10)

        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.North)
        layout.addWidget(self.tabs)

        from .scan_page import ScanPage
        from .rules_page import RulesPage
        from .preview_page import PreviewPage
        from .output_page import OutputPage
        from .log_page import LogPage

        self.scan_page = ScanPage(self.scanner, self)
        self.rules_page = RulesPage(self.rules, self)
        self.preview_page = PreviewPage(self.scanner, self.rules, self)
        self.output_page = OutputPage(
            self.scanner, self.rules, self.packager,
            self.logger, self.history, self.batch_history,
            self.profile_manager, self.task_queue, self
        )
        self.log_page = LogPage(self.logger, self.history, self.batch_history, self)

        self.tabs.addTab(self.scan_page, "📁 文件扫描")
        self.tabs.addTab(self.rules_page, "⚙️ 规则设置")
        self.tabs.addTab(self.preview_page, "👁️ 封面预览")
        self.tabs.addTab(self.output_page, "📦 打包输出")
        self.tabs.addTab(self.log_page, "📋 日志记录")

        self.scan_page.projects_updated.connect(self._on_projects_updated)
        self.rules_page.rules_changed.connect(self._on_rules_changed)
        self.output_page.rules_changed.connect(self._on_rules_changed)
        self.output_page.profile_applied.connect(self._on_profile_applied)
        self.output_page.batch_finished.connect(self._on_batch_finished)

        self.statusBar().showMessage("就绪")

    def _on_projects_updated(self):
        self.preview_page.refresh_projects()
        self.output_page.refresh_projects()
        self.statusBar().showMessage(f"扫描完成，共 {len(self.scanner.projects)} 个项目")

    def _on_rules_changed(self):
        self.preview_page.refresh_preview()
        self.output_page.refresh_delivery_check()
        self.statusBar().showMessage("规则已更新")

    def _on_profile_applied(self):
        self.preview_page.refresh_preview()
        self.rules_page.refresh_controls()
        self.statusBar().showMessage("交付方案已套用")

    def _on_batch_finished(self):
        self.log_page.refresh_history()
        self.log_page.refresh_batch_history()
        self.statusBar().showMessage("批量生成完成")


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
