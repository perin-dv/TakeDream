import shutil
from pathlib import Path

from PySide6.QtCore import QUrl, Signal, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMenu,
    QMessageBox,
    QToolButton,
)


TOP_MENU_STYLE = """
QFrame#TopMenuBar {
    background: #181514;
    border: none;
    border-bottom: 1px solid #282321;
}
QToolButton#TopMenuButton {
    background: transparent;
    border: none;
    border-radius: 5px;
    padding: 4px 10px;
    color: #B8B1AE;
    font-size: 12px;
    font-weight: 500;
}
QToolButton#TopMenuButton:hover,
QToolButton#TopMenuButton:pressed,
QToolButton#TopMenuButton:checked {
    background: #2A2523;
    color: #FFFFFF;
}
QToolButton#TopMenuButton::menu-indicator {
    image: none;
    width: 0px;
}
"""

DROPDOWN_STYLE = """
QMenu {
    background: #211E1D;
    color: #ECE8E6;
    border: 1px solid #3A3431;
    border-radius: 7px;
    padding: 5px;
    font-size: 12px;
}
QMenu::item {
    background: transparent;
    color: #ECE8E6;
    padding: 7px 26px 7px 10px;
    border-radius: 5px;
}
QMenu::item:selected {
    background: #37312E;
    color: #FFFFFF;
}
QMenu::item:disabled {
    color: #716A67;
}
QMenu::separator {
    height: 1px;
    background: #3A3431;
    margin: 5px 8px;
}
QMenu::right-arrow {
    width: 0px;
    height: 0px;
}
"""


class TakeDreamTopMenu(QFrame):
    navigate = Signal(str)

    def __init__(self, host=None, parent=None):
        super().__init__(parent)
        self.host = host
        self.setObjectName("TopMenuBar")
        self.setFixedHeight(36)
        self.setStyleSheet(TOP_MENU_STYLE)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(0)

        self.file_button = self._menu_button("Arquivo", self._file_menu())
        self.edit_button = self._menu_button("Editar", self._edit_menu())
        self.view_button = self._menu_button("Exibir", self._view_menu())
        self.tools_button = self._menu_button("Ferramentas", self._tools_menu())
        self.help_button = self._menu_button("Ajuda", self._help_menu())

        for button in (
            self.file_button,
            self.edit_button,
            self.view_button,
            self.tools_button,
            self.help_button,
        ):
            layout.addWidget(button)
        layout.addStretch(1)

    def _menu_button(self, text, menu):
        button = QToolButton(self)
        button.setObjectName("TopMenuButton")
        button.setText(text)
        button.setAutoRaise(True)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setMenu(menu)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def _new_menu(self):
        menu = QMenu(self)
        menu.setObjectName("TopDropdownMenu")
        menu.setStyleSheet(DROPDOWN_STYLE)
        return menu

    def _file_menu(self):
        menu = self._new_menu()
        menu.addAction("Novo projeto", lambda: self.navigate.emit("new"))
        menu.addAction("Projetos", lambda: self.navigate.emit("projects"))
        menu.addAction("Exportações", lambda: self.navigate.emit("exports"))
        menu.addSeparator()
        menu.addAction("Sair", self._close_host)
        return menu

    def _edit_menu(self):
        menu = self._new_menu()
        menu.addAction("Abrir revisão", lambda: self.navigate.emit("review"))
        menu.addAction("Configurações", lambda: self.navigate.emit("settings"))
        return menu

    def _view_menu(self):
        menu = self._new_menu()
        menu.addAction("Início", lambda: self.navigate.emit("home"))
        menu.addAction("Projetos", lambda: self.navigate.emit("projects"))
        menu.addAction("Revisão", lambda: self.navigate.emit("review"))
        menu.addAction("Exportações", lambda: self.navigate.emit("exports"))
        return menu

    def _tools_menu(self):
        menu = self._new_menu()
        menu.addAction("Configurações", lambda: self.navigate.emit("settings"))
        menu.addSeparator()
        self.open_cache_action = menu.addAction(
            "Abrir pasta de cache",
            self._open_project_cache,
        )
        self.clear_cache_action = menu.addAction(
            "Limpar cache temporário deste projeto...",
            self._clear_project_cache,
        )
        menu.aboutToShow.connect(self._update_context_actions)
        return menu

    def _help_menu(self):
        menu = self._new_menu()
        menu.addAction("Sobre o TakeDream", self._show_about)
        return menu

    def _current_project_widget(self):
        host = self.host
        if host is None:
            return None
        for name in ("current_review_page", "current_project_page"):
            widget = getattr(host, name, None)
            if widget is not None and hasattr(widget, "project_dir"):
                return widget
        current = getattr(getattr(host, "app_stack", None), "currentWidget", None)
        if callable(current):
            widget = current()
            if widget is not None and hasattr(widget, "project_dir"):
                return widget
        return None

    def _project_cache_dir(self):
        context = self._current_project_widget()
        if context is None:
            return None
        try:
            return Path(context.project_dir).expanduser().resolve() / "cache"
        except (AttributeError, TypeError, ValueError):
            return None

    def _update_context_actions(self):
        available = self._project_cache_dir() is not None
        self.open_cache_action.setEnabled(available)
        self.clear_cache_action.setEnabled(available)

    def _open_project_cache(self):
        cache_dir = self._project_cache_dir()
        if cache_dir is None:
            QMessageBox.information(
                self,
                "Cache",
                "Abra um projeto para acessar o cache dele.",
            )
            return
        cache_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(cache_dir)))

    def _clear_project_cache(self):
        context = self._current_project_widget()
        cache_dir = self._project_cache_dir()
        if cache_dir is None:
            QMessageBox.information(
                self,
                "Cache",
                "Abra um projeto para limpar o cache dele.",
            )
            return
        if getattr(context, "worker", None) is not None:
            QMessageBox.warning(
                self,
                "Processamento em andamento",
                "Espere o processamento terminar ou cancele antes de limpar o cache.",
            )
            return

        files = []
        total_bytes = 0
        if cache_dir.exists():
            for path in cache_dir.rglob("*"):
                if path.is_file():
                    files.append(path)
                    try:
                        total_bytes += path.stat().st_size
                    except OSError:
                        pass
        if not files:
            QMessageBox.information(self, "Cache", "O cache deste projeto já está vazio.")
            return

        answer = QMessageBox.question(
            self,
            "Limpar cache temporário",
            "Deseja apagar o cache temporário deste projeto?\n\n"
            "Miniaturas e temporários serão removidos. As mídias originais e o project.json não serão apagados.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        shutil.rmtree(cache_dir, ignore_errors=True)
        cache_dir.mkdir(parents=True, exist_ok=True)
        QMessageBox.information(
            self,
            "Cache limpo",
            f"{len(files)} arquivo(s) removido(s) • {total_bytes / (1024 * 1024):.1f} MB liberados.",
        )

    def _show_about(self):
        QMessageBox.information(
            self,
            "Sobre o TakeDream",
            "TakeDream\nEdição assistida por IA com revisão humana na timeline.",
        )

    def _close_host(self):
        if self.host is not None:
            self.host.close()
