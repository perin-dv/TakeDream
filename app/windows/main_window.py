from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.ui.components import (
    card,
    muted_label,
    section_title,
)
from app.ui.icons import app_icon, icon_pixmap
from app.ui.shell import TakeDreamSidebar
from app.ui.theme import apply_app_theme
from app.ui.windows import enable_dark_title_bar
from app.windows.new_project_dialog import NewProjectDialog
from app.windows.project_window import ProjectWindow
from app.windows.review_window import ReviewWindow
from core.project_manager import ProjectManager


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.project_manager = ProjectManager()
        self.project_windows = []
        self.review_windows = []
        self.new_project_page = None
        self.current_project_page = None
        self.current_review_page = None

        self.setWindowTitle("TakeDream")
        self.resize(1440, 900)
        self.setMinimumSize(1120, 720)

        root = QWidget()
        root.setObjectName("Root")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.sidebar = TakeDreamSidebar("home")
        self.sidebar.navigate.connect(self._navigate)

        self.pages = QStackedWidget()
        self.pages.setObjectName("AppPages")

        self.home_page = QWidget()
        self.home_page.setObjectName("AppPage")
        self.projects_page = QWidget()
        self.projects_page.setObjectName("AppPage")
        self.exports_page = QWidget()
        self.exports_page.setObjectName("AppPage")
        self.settings_page = QWidget()
        self.settings_page.setObjectName("AppPage")

        self.pages.addWidget(self.home_page)
        self.pages.addWidget(self.projects_page)
        self.pages.addWidget(self.exports_page)
        self.pages.addWidget(self.settings_page)

        root_layout.addWidget(self.sidebar)
        root_layout.addWidget(self.pages, 1)

        self.shell_root = root
        self.app_stack = QStackedWidget()
        self.app_stack.setObjectName("MainAppStack")
        self.app_stack.addWidget(self.shell_root)
        self.setCentralWidget(self.app_stack)

        self.status_label = QLabel()
        self.status_label.hide()

        apply_app_theme(self)
        enable_dark_title_bar(self)
        self._build_all_pages()
        self._navigate("home")

    # ------------------------------------------------------------------
    # PAGE BUILDERS
    # ------------------------------------------------------------------
    def _page_shell(self, page, title, subtitle):
        outer = QVBoxLayout(page)
        outer.setContentsMargins(24, 22, 24, 22)
        outer.setSpacing(16)

        header = QHBoxLayout()
        texts = QVBoxLayout()
        texts.setSpacing(1)

        title_label = QLabel(title)
        title_label.setObjectName("PageTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("PageSubtitle")

        texts.addWidget(title_label)
        texts.addWidget(subtitle_label)

        header.addLayout(texts)
        header.addStretch(1)

        outer.addLayout(header)
        return outer, header

    def _clear_page(self, page):
        old = page.layout()
        if old is None:
            return

        while old.count():
            item = old.takeAt(0)
            widget = item.widget()
            layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            if layout is not None:
                self._clear_layout(layout)

        QWidget().setLayout(old)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child = item.layout()
            if widget is not None:
                widget.deleteLater()
            if child is not None:
                self._clear_layout(child)

    def _build_all_pages(self):
        for page in (
            self.home_page,
            self.projects_page,
            self.exports_page,
            self.settings_page,
        ):
            if page.layout() is not None:
                self._clear_page(page)

        self._build_home_page()
        self._build_projects_page()
        self._build_exports_page()
        self._build_settings_page()

    def _build_home_page(self):
        layout, header = self._page_shell(
            self.home_page,
            "Bem-vindo ao TakeDream",
            "Crie, revise e exporte seus vídeos em um único lugar.",
        )

        refresh_button = QPushButton("Atualizar")
        refresh_button.setIcon(
            app_icon("refresh", color="#EDE9FE", accent="#A855F7", size=17)
        )
        refresh_button.clicked.connect(self._build_all_pages)
        header.addWidget(refresh_button)

        hero = QFrame()
        hero.setObjectName("HeroCard")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(22, 20, 22, 20)
        hero_layout.setSpacing(20)

        hero_text = QVBoxLayout()
        hero_text.setSpacing(8)

        eyebrow = QLabel("EDIÇÃO INTELIGENTE")
        eyebrow.setStyleSheet(
            "color:#C084FC; font-weight:800; letter-spacing:1px;"
        )
        hero_title = QLabel(
            "Seu vídeo entra bruto.\n"
            "O TakeDream prepara o primeiro corte."
        )
        hero_title.setStyleSheet(
            "font-size:26px; font-weight:850; color:#FFFFFF;"
        )
        hero_subtitle = muted_label(
            "Transcreva, corte, revise, ajuste o formato e exporte "
            "sem trocar de programa.",
            True,
        )

        actions = QHBoxLayout()
        new_button = QPushButton("Novo Projeto")
        new_button.setIcon(app_icon("plus", color="#FFFFFF", accent="#FFFFFF", size=18))
        new_button.setProperty("primary", True)
        new_button.clicked.connect(self.create_project)

        open_button = QPushButton("Abrir projeto existente")
        open_button.setIcon(app_icon("folder", color="#EDE9FE", accent="#A855F7", size=18))
        open_button.setProperty("secondary", True)
        open_button.clicked.connect(self.open_project)

        actions.addWidget(new_button)
        actions.addWidget(open_button)
        actions.addStretch(1)

        hero_text.addWidget(eyebrow)
        hero_text.addWidget(hero_title)
        hero_text.addWidget(hero_subtitle)
        hero_text.addSpacing(4)
        hero_text.addLayout(actions)

        hero_art = QFrame()
        hero_art.setFixedWidth(380)
        hero_art.setStyleSheet(
            "background:qlineargradient("
            "x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #301B6B, stop:0.55 #1B315F, stop:1 #5A1D6F);"
            "border:1px solid #7C5CE7; border-radius:16px;"
        )
        art_layout = QVBoxLayout(hero_art)
        art_layout.setContentsMargins(22, 18, 22, 18)
        art_icons = QHBoxLayout()
        art_icons.setSpacing(18)
        for icon_name, icon_size in (
            ("star", 34),
            ("brand", 62),
            ("sparkles", 34),
        ):
            art_icon = QLabel()
            art_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            art_icon.setPixmap(
                icon_pixmap(
                    icon_name,
                    color="#FFFFFF",
                    accent="#D8B4FE",
                    size=icon_size,
                )
            )
            art_icons.addWidget(art_icon)

        art_layout.addStretch(1)
        art_layout.addLayout(art_icons)
        art_layout.addStretch(1)
        art_caption = QLabel("Crie histórias. Não só cortes.")
        art_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        art_caption.setStyleSheet(
            "font-size:15px; font-weight:800; color:#FFFFFF;"
        )
        art_layout.addWidget(art_caption)

        hero_layout.addLayout(hero_text, 1)
        hero_layout.addWidget(hero_art)

        layout.addWidget(hero)

        quick = QHBoxLayout()
        quick.setSpacing(10)

        steps = (
            ("1", "Transcrever", "Converta fala em texto com timestamps.", "#6D28D9"),
            ("2", "Cortar", "Remova pausas e ajuste trechos.", "#2563EB"),
            ("3", "Revisar", "Veja o resultado em uma timeline real.", "#C026D3"),
            ("4", "Exportar", "Escolha formato e qualidade final.", "#B7791F"),
        )

        for number, title, description, accent in steps:
            frame = card()
            frame.setMinimumHeight(120)
            frame.setStyleSheet(
                "QFrame#Card {"
                "background:#141C39; border:1px solid #2B3762;"
                "border-radius:14px;}"
            )
            box = QVBoxLayout(frame)
            box.setContentsMargins(14, 12, 14, 12)
            badge = QLabel(number)
            badge.setFixedSize(30, 30)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet(
                f"background:{accent}; border-radius:15px;"
                "font-weight:800; color:#FFFFFF;"
            )
            name = QLabel(title)
            name.setStyleSheet(
                "font-size:15px; font-weight:800; color:#FFFFFF;"
            )
            desc = muted_label(description, True)
            box.addWidget(badge)
            box.addWidget(name)
            box.addWidget(desc)
            quick.addWidget(frame, 1)

        layout.addWidget(section_title("Fluxo rápido", "sparkles"))
        layout.addLayout(quick)

        lower = QHBoxLayout()
        lower.setSpacing(12)

        recent_projects = card()
        recent_layout = QVBoxLayout(recent_projects)
        recent_layout.setContentsMargins(14, 14, 14, 14)

        title_row = QHBoxLayout()
        title_row.addWidget(section_title("Continuar projeto", "projects"))
        title_row.addStretch(1)
        see_projects = QPushButton("Ver todos  →")
        see_projects.clicked.connect(lambda: self._navigate("projects"))
        title_row.addWidget(see_projects)
        recent_layout.addLayout(title_row)

        projects = self.project_manager.list_projects()[:3]
        if not projects:
            empty = muted_label(
                "Nenhum projeto ainda. Crie o primeiro para começar.",
                True,
            )
            recent_layout.addWidget(empty)
        else:
            cards_row = QHBoxLayout()
            cards_row.setSpacing(8)
            for project in projects:
                cards_row.addWidget(self._project_card(project), 1)
            recent_layout.addLayout(cards_row)

        recent_exports = card()
        recent_exports.setFixedWidth(360)
        export_layout = QVBoxLayout(recent_exports)
        export_layout.setContentsMargins(14, 14, 14, 14)

        export_title = QHBoxLayout()
        export_title.addWidget(section_title("Exportações recentes", "export"))
        export_title.addStretch(1)
        see_exports = QPushButton("Ver todas")
        see_exports.clicked.connect(lambda: self._navigate("exports"))
        export_title.addWidget(see_exports)
        export_layout.addLayout(export_title)

        exports = self.project_manager.list_exports()[:5]
        if not exports:
            export_layout.addWidget(
                muted_label("Nenhuma exportação ainda.", True)
            )
        else:
            for item in exports:
                export_layout.addWidget(self._export_row(item))

        lower.addWidget(recent_projects, 1)
        lower.addWidget(recent_exports)
        layout.addLayout(lower, 1)

    def _build_projects_page(self):
        layout, header = self._page_shell(
            self.projects_page,
            "Projetos",
            "Continue um trabalho existente ou comece algo novo.",
        )

        new_button = QPushButton("Novo Projeto")
        new_button.setIcon(app_icon("plus", color="#FFFFFF", accent="#FFFFFF", size=18))
        new_button.setProperty("primary", True)
        new_button.clicked.connect(self.create_project)
        header.addWidget(new_button)

        browse_button = QPushButton("Abrir project.json")
        browse_button.setIcon(app_icon("folder", color="#EDE9FE", accent="#A855F7", size=17))
        browse_button.clicked.connect(self.open_project)
        header.addWidget(browse_button)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        body = QWidget()
        grid = QGridLayout(body)
        grid.setContentsMargins(2, 2, 12, 12)
        grid.setSpacing(12)

        projects = self.project_manager.list_projects()
        if not projects:
            empty = card()
            empty_layout = QVBoxLayout(empty)
            empty_layout.addWidget(
                section_title("Nenhum projeto encontrado")
            )
            empty_layout.addWidget(
                muted_label(
                    "Seus projetos aparecerão aqui em cards, "
                    "com formato, estilo e status.",
                    True,
                )
            )
            create = QPushButton("Criar primeiro projeto")
            create.setProperty("primary", True)
            create.clicked.connect(self.create_project)
            empty_layout.addWidget(create)
            grid.addWidget(empty, 0, 0)
        else:
            for index, project in enumerate(projects):
                grid.addWidget(
                    self._project_card(project, large=True),
                    index // 3,
                    index % 3,
                )

        scroll.setWidget(body)
        layout.addWidget(scroll, 1)

    def _build_exports_page(self):
        layout, _ = self._page_shell(
            self.exports_page,
            "Exportações",
            "Todos os vídeos finais gerados pelo TakeDream.",
        )

        exports = self.project_manager.list_exports()

        if not exports:
            empty = card()
            box = QVBoxLayout(empty)
            box.addWidget(section_title("Nenhum vídeo exportado ainda"))
            box.addWidget(
                muted_label(
                    "Quando você exportar um projeto, "
                    "o arquivo aparecerá aqui.",
                    True,
                )
            )
            layout.addWidget(empty)
            layout.addStretch(1)
            return

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 8, 8)
        body_layout.setSpacing(8)

        for item in exports:
            body_layout.addWidget(self._export_row(item, large=True))

        body_layout.addStretch(1)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)

    def _build_settings_page(self):
        layout, _ = self._page_shell(
            self.settings_page,
            "Configurações",
            "Preferências gerais do TakeDream.",
        )

        cards = (
            (
                "Aparência",
                "Tema TakeDream",
                "O redesign fantasia está ativo em todo o programa.",
            ),
            (
                "Processamento",
                "GPU automática",
                "NVIDIA, Intel ou AMD quando disponível, com fallback para CPU.",
            ),
            (
                "Transcrição",
                "Faster Whisper",
                "Modelo e dispositivo continuam configuráveis por ambiente.",
            ),
            (
                "Projetos",
                str(self.project_manager.projects_root),
                "Pasta padrão onde o TakeDream mantém seus projetos.",
            ),
        )

        grid = QGridLayout()
        grid.setSpacing(12)

        for index, (title, value, description) in enumerate(cards):
            frame = card()
            box = QVBoxLayout(frame)
            box.setContentsMargins(16, 14, 16, 14)

            box.addWidget(section_title(title))
            value_label = QLabel(value)
            value_label.setStyleSheet(
                "font-size:15px; font-weight:800; color:#FFFFFF;"
            )
            box.addWidget(value_label)
            box.addWidget(muted_label(description, True))

            grid.addWidget(
                frame,
                index // 2,
                index % 2,
            )

        layout.addLayout(grid)
        layout.addStretch(1)

    # ------------------------------------------------------------------
    # CARD HELPERS
    # ------------------------------------------------------------------
    def _project_card(self, project, large=False):
        frame = card()
        frame.setMinimumHeight(160 if large else 132)

        box = QVBoxLayout(frame)
        box.setContentsMargins(12, 12, 12, 12)
        box.setSpacing(7)

        preview = QLabel()
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setMinimumHeight(82 if large else 62)
        preview.setStyleSheet(
            "background:qlineargradient("
            "x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #2B1E68, stop:0.55 #173B61, stop:1 #4D1F6D);"
            "border:1px solid #4B5790; border-radius:10px;"
        )

        thumbnails = sorted(
            (project["project_dir"] / "cache" / "thumbnails").glob(
                "thumb_*.jpg"
            )
        )
        if thumbnails:
            pixmap = QPixmap(str(thumbnails[0]))
            if not pixmap.isNull():
                preview.setPixmap(
                    pixmap.scaled(
                        320 if large else 220,
                        120 if large else 85,
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        else:
            preview.setPixmap(
                icon_pixmap(
                    "brand",
                    color="#FFFFFF",
                    accent="#C084FC",
                    size=42 if large else 32,
                )
            )

        name = QLabel(project["name"])
        name.setStyleSheet(
            "font-size:14px; font-weight:800; color:#FFFFFF;"
        )

        metadata = muted_label(
            f"{project['profile']}  •  {project['style']}  •  "
            f"{project['aspect_ratio']}"
        )

        source = muted_label(project["source_filename"])
        source.setToolTip(project["source_filename"])

        open_button = QPushButton("Abrir projeto")
        open_button.setIcon(app_icon("folder", color="#EDE9FE", accent="#A855F7", size=16))
        open_button.setProperty("secondary", True)
        open_button.clicked.connect(
            lambda checked=False, path=project["project_dir"]:
            self._show_project_window(path)
        )

        box.addWidget(preview)
        box.addWidget(name)
        box.addWidget(metadata)
        if large:
            box.addWidget(source)
        box.addWidget(open_button)

        return frame

    def _export_row(self, item, large=False):
        frame = QFrame()
        frame.setObjectName("Card")
        row = QHBoxLayout(frame)
        row.setContentsMargins(10, 9, 10, 9)
        row.setSpacing(10)

        badge = QLabel()
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(34, 34)
        badge.setStyleSheet(
            "background:#136A58; border-radius:9px;"
        )
        badge.setPixmap(
            icon_pixmap(
                "check",
                color="#FFFFFF",
                accent="#FFFFFF",
                size=18,
            )
        )

        texts = QVBoxLayout()
        texts.setSpacing(1)
        title = QLabel(item["project_name"])
        title.setStyleSheet("font-weight:800; color:#FFFFFF;")
        file_label = muted_label(item["filename"])
        texts.addWidget(title)
        texts.addWidget(file_label)

        row.addWidget(badge)
        row.addLayout(texts, 1)

        if large:
            size_mb = item["size_bytes"] / (1024 * 1024)
            size = muted_label(f"{size_mb:.1f} MB")
            row.addWidget(size)

        open_button = QPushButton("Abrir")
        open_button.setIcon(app_icon("play", color="#EDE9FE", accent="#A855F7", size=15))
        open_button.clicked.connect(
            lambda checked=False, path=item["path"]:
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(path))
            )
        )
        row.addWidget(open_button)

        folder_button = QPushButton("Pasta")
        folder_button.setIcon(app_icon("folder", color="#EDE9FE", accent="#A855F7", size=15))
        folder_button.clicked.connect(
            lambda checked=False, path=item["path"].parent:
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(path))
            )
        )
        row.addWidget(folder_button)

        return frame

    # ------------------------------------------------------------------
    # NAVIGATION / ACTIONS — SINGLE WINDOW
    # ------------------------------------------------------------------
    def _show_shell_page(self, target):
        page_map = {
            "home": (0, "home"),
            "projects": (1, "projects"),
            "exports": (2, "exports"),
            "settings": (3, "settings"),
        }

        if target not in page_map:
            return

        index, active = page_map[target]
        self.pages.setCurrentIndex(index)
        self.sidebar.set_active(active)
        self.app_stack.setCurrentWidget(
            self.shell_root
        )

    def _navigate(self, target):
        if target == "new":
            self.create_project()
            return

        if target == "review":
            projects = [
                project
                for project in self.project_manager.list_projects()
                if project.get("output_path")
            ]

            if not projects:
                QMessageBox.information(
                    self,
                    "Revisão",
                    "Abra ou processe um projeto antes de revisar a edição.",
                )
                return

            self._show_review_page(
                projects[0]["project_dir"]
            )
            return

        self._show_shell_page(target)

    def _remove_page(self, page):
        if page is None:
            return

        try:
            if hasattr(page, "player"):
                page.player.stop()
        except Exception:
            pass

        index = self.app_stack.indexOf(page)
        if index >= 0:
            self.app_stack.removeWidget(page)

        page.deleteLater()

    def create_project(self):
        self._remove_page(
            self.new_project_page
        )

        self.new_project_page = (
            NewProjectDialog(
                self.app_stack,
                embedded=True,
                host=self,
            )
        )
        self.app_stack.addWidget(
            self.new_project_page
        )
        self.app_stack.setCurrentWidget(
            self.new_project_page
        )

    def _create_project_from_data(self, data):
        try:
            project_dir = (
                self.project_manager.create_project(
                    **data
                )
            )
        except ValueError as error:
            QMessageBox.warning(
                self,
                "Não foi possível criar",
                str(error),
            )
            return
        except OSError as error:
            QMessageBox.critical(
                self,
                "Erro ao criar projeto",
                "Falha ao criar os arquivos do projeto."
                f"\n\n{error}",
            )
            return

        self._build_all_pages()
        self._show_project_window(project_dir)

    def open_project(self):
        project_file, _ = (
            QFileDialog.getOpenFileName(
                self,
                "Abrir projeto TakeDream",
                str(
                    self.project_manager.projects_root
                ),
                "Projeto TakeDream (project.json)",
            )
        )

        if not project_file:
            return

        try:
            project_dir, _ = (
                self.project_manager.load_project(
                    project_file
                )
            )
        except ValueError as error:
            QMessageBox.warning(
                self,
                "Projeto inválido",
                str(error),
            )
            return

        self._show_project_window(
            project_dir
        )

    def _show_project_window(self, project_dir):
        self._remove_page(
            self.current_review_page
        )
        self.current_review_page = None

        self._remove_page(
            self.current_project_page
        )

        try:
            page = ProjectWindow(
                project_dir,
                self.app_stack,
                embedded=True,
                host=self,
            )
        except ValueError as error:
            QMessageBox.warning(
                self,
                "Projeto inválido",
                str(error),
            )
            self._show_shell_page("projects")
            return

        self.current_project_page = page
        self.project_windows = [page]

        self.app_stack.addWidget(page)
        self.app_stack.setCurrentWidget(page)

    def _show_review_page(self, project_dir):
        self._remove_page(
            self.current_review_page
        )

        try:
            page = ReviewWindow(
                project_dir,
                self.app_stack,
                embedded=True,
                host=self,
            )
        except ValueError as error:
            QMessageBox.warning(
                self,
                "Não foi possível abrir a revisão",
                str(error),
            )
            return

        self.current_review_page = page
        self.review_windows = [page]

        self.app_stack.addWidget(page)
        self.app_stack.setCurrentWidget(page)

    def _remove_project_window(self, window):
        if window in self.project_windows:
            self.project_windows.remove(window)

        if self.current_project_page is window:
            self.current_project_page = None

        self._build_all_pages()
        self._show_shell_page("projects")

    def _remove_review_window(self, window):
        if window in self.review_windows:
            self.review_windows.remove(window)

        if self.current_review_page is window:
            self.current_review_page = None

        self._build_all_pages()
        self._show_shell_page("home")
