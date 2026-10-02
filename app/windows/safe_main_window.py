from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox, QPushButton, QWidget

from app.windows.main_window import MainWindow


class SafeMainWindow(MainWindow):
    """Main window with a guard that keeps active media workers alive.

    The embedded ProjectWindow/ReviewWindow owns its QThread. Navigating away
    while that worker is running can leave signals targeting a page that is no
    longer active (or, on some routes, scheduled for deletion). This wrapper
    keeps the processing page mounted until the worker finishes or the user
    explicitly cancels the operation.
    """

    def __init__(self):
        self._close_after_processing = False
        super().__init__()

        self._processing_guard_timer = QTimer(self)
        self._processing_guard_timer.setInterval(180)
        self._processing_guard_timer.timeout.connect(
            self._sync_processing_navigation_state
        )
        self._processing_guard_timer.start()

    def _processing_page(self):
        for name in ("current_project_page", "current_review_page"):
            page = getattr(self, name, None)
            if page is not None and getattr(page, "worker", None) is not None:
                return page
        return None

    def _set_page_navigation_enabled(self, page, enabled):
        if page is None:
            return

        sidebar = getattr(page, "sidebar", None)
        buttons = getattr(sidebar, "buttons", {}) if sidebar is not None else {}
        for button in buttons.values():
            try:
                button.setEnabled(bool(enabled))
            except RuntimeError:
                pass

        # ProjectWindow currently creates this button locally rather than as an
        # attribute. Find it by label so it cannot bypass the navigation guard.
        try:
            for button in page.findChildren(QPushButton):
                text = button.text().strip().lower()
                if text in {
                    "voltar ao dashboard",
                    "voltar ao projeto",
                    "início",
                    "inicio",
                }:
                    button.setEnabled(bool(enabled))
        except (AttributeError, RuntimeError):
            pass

    def _sync_processing_navigation_state(self):
        processing = self._processing_page()
        for name in ("current_project_page", "current_review_page"):
            page = getattr(self, name, None)
            self._set_page_navigation_enabled(
                page,
                not (page is not None and page is processing),
            )

    def _guard_processing_navigation(self, target=None):
        page = self._processing_page()
        if page is None:
            return False

        label = getattr(page, "status_label", None)
        if label is not None:
            try:
                label.setText(
                    "Processamento em andamento • navegação bloqueada. "
                    "Aguarde terminar ou use Cancelar."
                )
            except RuntimeError:
                pass

        if isinstance(page, QWidget) and self.app_stack.indexOf(page) >= 0:
            self.app_stack.setCurrentWidget(page)

        return True

    def _navigate(self, target):
        if self._guard_processing_navigation(target):
            return
        super()._navigate(target)

    def create_project(self):
        if self._guard_processing_navigation("new"):
            return
        super().create_project()

    def open_project(self):
        if self._guard_processing_navigation("projects"):
            return
        super().open_project()

    def _show_project_window(self, project_dir):
        if self._guard_processing_navigation("projects"):
            return
        super()._show_project_window(project_dir)

    def _show_review_page(self, project_dir):
        if self._guard_processing_navigation("review"):
            return
        super()._show_review_page(project_dir)

    def _remove_page(self, page):
        if page is not None and getattr(page, "worker", None) is not None:
            return
        super()._remove_page(page)

    def closeEvent(self, event):
        page = self._processing_page()
        if page is None:
            if hasattr(self, "_processing_guard_timer"):
                self._processing_guard_timer.stop()
            super().closeEvent(event)
            return

        answer = QMessageBox.question(
            self,
            "Processamento em andamento",
            "Existe um processamento em andamento.\n\n"
            "Deseja cancelar o processamento e fechar o TakeDream?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            event.ignore()
            return

        event.ignore()
        self._close_after_processing = True

        cancel = getattr(page, "_cancel_processing", None)
        if callable(cancel):
            cancel()
        else:
            worker = getattr(page, "worker", None)
            token = getattr(worker, "cancel", None)
            if token is not None and hasattr(token, "set"):
                token.set()

        self._wait_until_processing_stops_then_close()

    def _wait_until_processing_stops_then_close(self):
        if not self._close_after_processing:
            return
        if self._processing_page() is not None:
            QTimer.singleShot(120, self._wait_until_processing_stops_then_close)
            return

        self._close_after_processing = False
        self.close()
