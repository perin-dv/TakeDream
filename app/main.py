import sys

from PySide6.QtWidgets import QApplication

from app.ui.icons import app_icon
from app.ui.theme import APP_STYLESHEET
from app.ui.top_menu import TakeDreamTopMenu
from app.windows.safe_main_window import SafeMainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("TakeDream")
    app.setWindowIcon(
        app_icon(
            "brand",
            color="#FFFFFF",
            accent="#A855F7",
            size=48,
        )
    )
    app.setStyleSheet(APP_STYLESHEET)

    window = SafeMainWindow()
    window.top_menu = TakeDreamTopMenu(host=window, parent=window)
    window.top_menu.navigate.connect(window._navigate)
    window.setMenuWidget(window.top_menu)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
