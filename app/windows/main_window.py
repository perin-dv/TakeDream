from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.windows.new_project_dialog import NewProjectDialog
from core.project_manager import ProjectManager


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.project_manager = ProjectManager()

        self.setWindowTitle("TakeDream")
        self.resize(800, 500)

        container = QWidget()
        layout = QVBoxLayout(container)

        title = QLabel("TAKEDREAM")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("Edição inteligente começa aqui.")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.status_label = QLabel("Nenhum projeto aberto.")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        new_project_button = QPushButton("Novo Projeto")
        new_project_button.clicked.connect(self.create_project)

        open_project_button = QPushButton("Abrir Projeto")
        open_project_button.setEnabled(False)
        open_project_button.setToolTip("Será implementado na próxima etapa.")

        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(20)
        layout.addWidget(new_project_button)
        layout.addWidget(open_project_button)
        layout.addSpacing(20)
        layout.addWidget(self.status_label)
        layout.addStretch()

        self.setCentralWidget(container)

    def create_project(self):
        dialog = NewProjectDialog(self)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.project_data()

        try:
            project_dir = self.project_manager.create_project(**data)
        except ValueError as error:
            QMessageBox.warning(self, "Não foi possível criar", str(error))
            return
        except OSError as error:
            QMessageBox.critical(
                self,
                "Erro ao criar projeto",
                f"Falha ao criar os arquivos do projeto.\n\n{error}",
            )
            return

        self.status_label.setText(f"Projeto criado: {data['name']}")

        QMessageBox.information(
            self,
            "Projeto criado",
            f"O projeto foi criado com sucesso.\n\n{project_dir}",
        )
