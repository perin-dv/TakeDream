import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QWidget

from app.windows.safe_main_window import SafeMainWindow


class _BusyPage(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = object()
        self.status_label = QLabel(self)


class ProcessingNavigationGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.window = SafeMainWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.current_project_page = None
        self.window.current_review_page = None
        self.window.close()
        self.app.processEvents()

    def _mount_busy_page(self):
        page = _BusyPage()
        self.window.current_project_page = page
        self.window.app_stack.addWidget(page)
        self.window.app_stack.setCurrentWidget(page)
        return page

    def test_navigation_stays_on_processing_page(self):
        page = self._mount_busy_page()

        self.window._navigate("home")
        self.app.processEvents()

        self.assertIs(self.window.app_stack.currentWidget(), page)
        self.assertIn("Processamento em andamento", page.status_label.text())

    def test_page_cannot_be_removed_while_worker_is_active(self):
        page = self._mount_busy_page()

        self.window._remove_page(page)
        self.app.processEvents()

        self.assertGreaterEqual(self.window.app_stack.indexOf(page), 0)
        self.assertIs(self.window.current_project_page, page)

    def test_navigation_is_released_after_worker_finishes(self):
        page = self._mount_busy_page()
        page.worker = None

        self.window._navigate("home")
        self.app.processEvents()

        self.assertIs(self.window.app_stack.currentWidget(), self.window.shell_root)


if __name__ == "__main__":
    unittest.main()
