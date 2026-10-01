import shutil
from pathlib import Path

from PySide6.QtCore import QUrl, Signal, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.ui.components import (
    BrandWidget,
    muted_label,
    nav_button,
)
from app.ui.icons import app_icon, icon_pixmap


class TakeDreamSidebar(QFrame):
    navigate = Signal(str)

    def __init__(
        self,
        active="home",
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(226)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 22, 18, 18)
        layout.setSpacing(7)

        self.brand = BrandWidget()
        subtitle = muted_label(
            "Transforme vídeos em\nhistórias incríveis."
        )
        subtitle.setStyleSheet(
            "font-size:11px; line-height:1.2;"
        )

        layout.addWidget(self.brand)
        layout.addWidget(subtitle)

        self.menu_button = QPushButton("☰  Menu")
        self.menu_button.setObjectName("AppMenuButton")
        self.menu_button.setToolTip("Abrir menu do TakeDream")
        self.menu_button.setMenu(self._build_menu())
        layout.addWidget(self.menu_button)
        layout.addSpacing(10)

        items = (
            ("home", "home", "Início"),
            ("new", "plus", "Novo Projeto"),
            ("projects", "projects", "Projetos"),
            ("review", "review", "Revisão"),
            ("exports", "export", "Exportações"),
            ("settings", "settings", "Configurações"),
        )

        self.buttons = {}

        for key, icon_name, text in items:
            button = nav_button(
                icon_name,
                text,
                active=(key == active),
            )
            button.clicked.connect(
                lambda checked=False, name=key:
                self.navigate.emit(name)
            )
            layout.addWidget(button)
            self.buttons[key] = button

        layout.addStretch(1)

        promo = QFrame()
        promo.setObjectName("FantasyPromo")
        promo_layout = QVBoxLayout(promo)
        promo_layout.setContentsMargins(14, 14, 14, 14)
        promo_layout.setSpacing(7)

        promo_header = QHBoxLayout()
        promo_icon = QLabel()
        promo_icon.setFixedSize(28, 28)
        promo_icon.setPixmap(
            icon_pixmap(
                "sparkles",
                color="#FFFFFF",
                accent="#D8B4FE",
                size=24,
            )
        )

        promo_title = QLabel("Crie. Edite. Sonhe.")
        promo_title.setStyleSheet(
            "font-weight:800; color:#FFFFFF; font-size:13px;"
        )

        promo_header.addWidget(promo_icon)
        promo_header.addWidget(promo_title)
        promo_header.addStretch(1)

        promo_text = muted_label(
            "A IA monta o primeiro corte.\n"
            "Você controla o resultado.",
            True,
        )

        promo_art = QFrame()
        promo_art.setFixedHeight(50)
        promo_art.setStyleSheet(
            "background:qlineargradient("
            "x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #3A1D72, stop:.5 #263B71, stop:1 #54216D);"
            "border:1px solid #6C53B5; border-radius:10px;"
        )
        art_layout = QHBoxLayout(promo_art)
        art_layout.setContentsMargins(9, 7, 9, 7)

        for name in ("star", "sparkles", "brand"):
            label = QLabel()
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setPixmap(
                icon_pixmap(
                    name,
                    color="#F4EEFF",
                    accent="#C084FC",
                    size=22,
                )
            )
            art_layout.addWidget(label)

        promo_layout.addLayout(promo_header)
        promo_layout.addWidget(promo_text)
        promo_layout.addWidget(promo_art)
        layout.addWidget(promo)

    def _build_menu(self):
        menu = QMenu(self)
        menu.setObjectName("AppMenu")

        file_menu = menu.addMenu("Arquivo")
        file_menu.addAction("Novo projeto", lambda: self.navigate.emit("new"))
        file_menu.addAction("Projetos", lambda: self.navigate.emit("projects"))
        file_menu.addAction("Exportações", lambda: self.navigate.emit("exports"))

        edit_menu = menu.addMenu("Editar")
        edit_menu.addAction("Abrir revisão", lambda: self.navigate.emit("review"))
        edit_menu.addAction("Configurações", lambda: self.navigate.emit("settings"))

        view_menu = menu.addMenu("Exibir")
        view_menu.addAction("Início", lambda: self.navigate.emit("home"))
        view_menu.addAction("Projetos", lambda: self.navigate.emit("projects"))
        view_menu.addAction("Revisão", lambda: self.navigate.emit("review"))

        tools_menu = menu.addMenu("Ferramentas")
        tools_menu.addAction("Configurações", lambda: self.navigate.emit("settings"))
        tools_menu.addSeparator()
        self.open_cache_action = tools_menu.addAction(
            "Abrir pasta de cache",
            self._open_project_cache,
        )
        self.clear_cache_action = tools_menu.addAction(
            "Limpar cache temporário deste projeto...",
            self._clear_project_cache,
        )

        help_menu = menu.addMenu("Ajuda")
        help_menu.addAction("Sobre o TakeDream", self._show_about)

        menu.aboutToShow.connect(self._update_context_actions)
        return menu

    def _context_widget(self):
        widget = self.parentWidget()
        while widget is not None:
            if hasattr(widget, "project_dir"):
                return widget
            widget = widget.parentWidget()
        return None

    def _project_cache_dir(self):
        context = self._context_widget()
        if context is None:
            return None
        try:
            project_dir = Path(context.project_dir).expanduser().resolve()
        except (AttributeError, TypeError, ValueError):
            return None
        return project_dir / "cache"

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
        context = self._context_widget()
        cache_dir = self._project_cache_dir()
        if cache_dir is None:
            QMessageBox.information(
                self,
                "Cache",
                "Abra um projeto para limpar o cache dele.",
            )
            return

        if context is not None and getattr(context, "worker", None) is not None:
            QMessageBox.warning(
                self,
                "Processamento em andamento",
                "Espere o processamento terminar ou cancele antes de limpar o cache.",
            )
            return

        file_count = 0
        size_bytes = 0
        if cache_dir.exists():
            for path in cache_dir.rglob("*"):
                if not path.is_file():
                    continue
                file_count += 1
                try:
                    size_bytes += path.stat().st_size
                except OSError:
                    pass

        if file_count == 0:
            QMessageBox.information(
                self,
                "Cache",
                "O cache temporário deste projeto já está vazio.",
            )
            return

        answer = QMessageBox.question(
            self,
            "Limpar cache temporário",
            "Deseja apagar o cache temporário deste projeto?\n\n"
            "Isso remove miniaturas e arquivos temporários. "
            "As mídias originais e o project.json não são apagados.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        shutil.rmtree(cache_dir, ignore_errors=True)
        cache_dir.mkdir(parents=True, exist_ok=True)
        size_mb = size_bytes / (1024 * 1024)
        QMessageBox.information(
            self,
            "Cache limpo",
            f"{file_count} arquivo(s) temporário(s) removido(s) • {size_mb:.1f} MB liberados.",
        )

    def _show_about(self):
        QMessageBox.information(
            self,
            "Sobre o TakeDream",
            "TakeDream\nEdição assistida por IA com revisão humana na timeline.",
        )

    def set_active(self, key):
        for name, button in self.buttons.items():
            button.setProperty(
                "navActive",
                name == key,
            )
            button.setIcon(
                app_icon(
                    {
                        "home": "home",
                        "new": "plus",
                        "projects": "projects",
                        "review": "review",
                        "exports": "export",
                        "settings": "settings",
                    }.get(name, "sparkles"),
                    color=(
                        "#FFFFFF"
                        if name == key
                        else "#D8DDF8"
                    ),
                    accent="#C084FC",
                    size=19,
                )
            )
            button.style().unpolish(button)
            button.style().polish(button)
