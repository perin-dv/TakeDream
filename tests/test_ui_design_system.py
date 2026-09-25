import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.ui.components import (
    AspectCardButton,
    BrandWidget,
    ModernSwitch,
    QualityCardButton,
    SelectionCardButton,
)
from app.ui.icons import app_icon, icon_pixmap


class DesignSystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_vector_icons_render(self):
        icon = app_icon("brand", size=32)
        pixmap = icon_pixmap("youtube", size=24)

        self.assertFalse(icon.isNull())
        self.assertFalse(pixmap.isNull())

    def test_brand_widget_can_be_created(self):
        widget = BrandWidget()
        self.assertGreater(widget.sizeHint().width(), 0)

    def test_modern_switch_keeps_checkbox_contract(self):
        switch = ModernSwitch("Legendas")
        self.assertFalse(switch.isChecked())

        switch.setChecked(True)

        self.assertTrue(switch.isChecked())

    def test_selection_cards_are_checkable(self):
        profile = SelectionCardButton(
            "YouTube",
            "Vídeos completos",
            "youtube",
        )
        aspect = AspectCardButton(
            "9:16",
            "Shorts e Reels",
        )
        quality = QualityCardButton(
            "1080p",
            "FULL HD",
            "Melhor",
        )

        for control in (
            profile,
            aspect,
            quality,
        ):
            self.assertTrue(control.isCheckable())
            control.setChecked(True)
            self.assertTrue(control.isChecked())


if __name__ == "__main__":
    unittest.main()
