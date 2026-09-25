from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from app.ui.components import (
    BrandWidget,
    muted_label,
    nav_button,
)
from app.ui.icons import icon_pixmap


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
        layout.addSpacing(22)

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

    def set_active(self, key):
        for name, button in self.buttons.items():
            button.setProperty(
                "navActive",
                name == key,
            )
            button.setIcon(
                __import__(
                    "app.ui.icons",
                    fromlist=["app_icon"],
                ).app_icon(
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
