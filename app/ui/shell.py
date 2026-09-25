from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from app.ui.components import (
    muted_label,
    nav_button,
)


class TakeDreamSidebar(QFrame):
    navigate = Signal(str)

    def __init__(
        self,
        active="home",
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(210)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 24, 18, 18)
        layout.setSpacing(8)

        brand = QLabel("☁  TakeDream")
        brand.setObjectName("Brand")
        brand.setStyleSheet(
            "font-size:24px; font-weight:800; color:#FFFFFF;"
        )
        subtitle = muted_label(
            "Transforme vídeos\nem histórias incríveis."
        )

        layout.addWidget(brand)
        layout.addWidget(subtitle)
        layout.addSpacing(22)

        items = (
            ("home", "⌂", "Início"),
            ("new", "＋", "Novo Projeto"),
            ("projects", "▣", "Projetos"),
            ("review", "✂", "Revisão"),
            ("exports", "⇧", "Exportações"),
            ("settings", "⚙", "Configurações"),
        )

        self.buttons = {}

        for key, icon, text in items:
            button = nav_button(
                icon,
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
        promo_layout.setSpacing(6)

        promo_title = QLabel("✦  Crie. Edite. Sonhe.")
        promo_title.setStyleSheet(
            "font-weight:800; color:#FFFFFF; font-size:13px;"
        )
        promo_text = muted_label(
            "A IA monta o primeiro corte.\n"
            "Você controla o resultado.",
            True,
        )
        promo_art = QLabel("✧   ◈   ✦   ⚔")
        promo_art.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        promo_art.setStyleSheet(
            "font-size:22px; color:#D8B4FE; padding-top:8px;"
        )

        promo_layout.addWidget(promo_title)
        promo_layout.addWidget(promo_text)
        promo_layout.addWidget(promo_art)
        layout.addWidget(promo)

    def set_active(self, key):
        for name, button in self.buttons.items():
            button.setProperty(
                "navActive",
                name == key,
            )
            button.style().unpolish(button)
            button.style().polish(button)
