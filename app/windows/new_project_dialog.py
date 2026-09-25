from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from profiles import (
    get_profile_definition,
    profile_names,
    styles_for_profile,
)
from renderer.formats import (
    ASPECT_RATIOS,
    get_aspect_ratio,
)


class NewProjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Novo Projeto")
        self.resize(620, 330)

        self.name_input = QLineEdit()

        self.video_input = QLineEdit()
        self.video_input.setReadOnly(True)

        self.select_video_button = QPushButton("Selecionar vídeo")
        self.select_video_button.clicked.connect(self.select_video)

        video_layout = QHBoxLayout()
        video_layout.addWidget(self.video_input)
        video_layout.addWidget(self.select_video_button)

        self.profile_combo = QComboBox()
        self.profile_combo.addItems(profile_names())
        self.profile_combo.currentTextChanged.connect(
            self._refresh_profile
        )

        self.style_combo = QComboBox()

        self.aspect_combo = QComboBox()
        for aspect in ASPECT_RATIOS:
            self.aspect_combo.addItem(
                aspect.label,
                aspect.key,
            )

        self.profile_description = QLabel()
        self.profile_description.setWordWrap(True)
        self.profile_description.setAlignment(
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignTop
        )

        form = QFormLayout()
        form.addRow("Nome do projeto:", self.name_input)
        form.addRow("Vídeo:", video_layout)
        form.addRow("Perfil:", self.profile_combo)
        form.addRow("Estilo:", self.style_combo)
        form.addRow("Formato:", self.aspect_combo)
        form.addRow("Descrição:", self.profile_description)

        self.create_button = QPushButton("Criar Projeto")
        self.cancel_button = QPushButton("Cancelar")

        self.create_button.clicked.connect(self.validate_and_accept)
        self.cancel_button.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.create_button)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addStretch()
        layout.addLayout(buttons)

        self._refresh_profile(self.profile_combo.currentText())

    def _refresh_profile(self, profile):
        self.style_combo.clear()
        self.style_combo.addItems(styles_for_profile(profile))

        definition = get_profile_definition(profile)
        orientation = (
            "Vertical"
            if definition.orientation == "vertical"
            else "Horizontal"
        )
        suggested_index = self.aspect_combo.findData(
            definition.aspect_ratio
        )
        if suggested_index >= 0:
            self.aspect_combo.setCurrentIndex(
                suggested_index
            )

        aspect = get_aspect_ratio(
            definition.aspect_ratio
        )
        self.profile_description.setText(
            f"{definition.description}\n"
            f"Sugestão do perfil: {orientation} • "
            f"{aspect.label}. Você pode escolher outro formato."
        )

    def select_video(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar vídeo",
            "",
            "Vídeos (*.mp4 *.mov *.mkv *.avi *.webm *.m4v);;"
            "Todos os arquivos (*)",
        )

        if file_path:
            self.video_input.setText(file_path)

    def validate_and_accept(self):
        if not self.name_input.text().strip():
            QMessageBox.warning(
                self,
                "Nome obrigatório",
                "Informe um nome para o projeto.",
            )
            return

        if not self.video_input.text().strip():
            QMessageBox.warning(
                self,
                "Vídeo obrigatório",
                "Selecione um vídeo para o projeto.",
            )
            return

        self.accept()

    def project_data(self):
        return {
            "name": self.name_input.text().strip(),
            "source_video": self.video_input.text().strip(),
            "profile": self.profile_combo.currentText(),
            "style": self.style_combo.currentText(),
            "aspect_ratio": self.aspect_combo.currentData(),
        }
