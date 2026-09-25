import sys

from PySide6.QtWidgets import QApplication

from app.ui.theme import APP_STYLESHEET
from app.windows.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLESHEET)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
