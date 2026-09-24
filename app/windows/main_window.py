from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("TakeDream")
        self.resize(800, 500)

        container = QWidget()
        layout = QVBoxLayout(container)

        title = QLabel("TAKEDREAM")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        new_project_button = QPushButton("Novo Projeto")
        open_project_button = QPushButton("Abrir Projeto")

        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(new_project_button)
        layout.addWidget(open_project_button)
        layout.addStretch()

        self.setCentralWidget(container)
