from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.components import (
    card,
    muted_label,
    option_button,
    quality_button,
    section_title,
)
from app.ui.shell import TakeDreamSidebar
from app.ui.theme import apply_app_theme
from app.ui.windows import enable_dark_title_bar
from profiles import (
    get_profile_definition,
    profile_names,
    styles_for_profile,
)
from renderer.captions import CAPTION_STYLES
from renderer.export_profiles import EXPORT_PROFILES
from renderer.formats import ASPECT_RATIOS


PROFILE_ICONS = {
    "YouTube": "▶",
    "Shorts / Reels / TikTok": "ϟ",
    "Podcast": "●",
    "Casamento": "◇",
    "Gaming": "◆",
    "Curso": "▤",
    "VSL": "✦",
    "Institucional": "▣",
}


class NewProjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("TakeDream — Novo Projeto")
        self.resize(1360, 840)
        self.setMinimumSize(1120, 720)

        self.selected_profile = profile_names()[0]
        self.selected_style = styles_for_profile(
            self.selected_profile
        )[0]
        self.selected_aspect = get_profile_definition(
            self.selected_profile
        ).aspect_ratio
        self.selected_quality = "original"

        # Hidden compatibility controls keep the original internal contract
        # available to tests and older code while the visible UI uses cards.
        self.profile_combo = QComboBox()
        self.profile_combo.addItems(profile_names())
        self.profile_combo.hide()

        self.style_combo = QComboBox()
        self.style_combo.hide()

        self.aspect_combo = QComboBox()
        for aspect in ASPECT_RATIOS:
            self.aspect_combo.addItem(aspect.label, aspect.key)
        self.aspect_combo.hide()

        self.profile_description = QLabel()
        self.profile_description.hide()

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = TakeDreamSidebar("new")
        self.sidebar.navigate.connect(self._sidebar_nav)
        root.addWidget(self.sidebar)

        content = QWidget()
        content.setObjectName("AppPage")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(22, 20, 22, 18)
        content_layout.setSpacing(14)

        header = QHBoxLayout()
        plus = QLabel("＋")
        plus.setFixedSize(48, 48)
        plus.setAlignment(Qt.AlignmentFlag.AlignCenter)
        plus.setStyleSheet(
            "background:#6D28D9; color:#FFFFFF; border-radius:24px;"
            "font-size:26px; font-weight:700;"
        )

        header_text = QVBoxLayout()
        header_text.setSpacing(0)
        title = QLabel("Novo Projeto")
        title.setObjectName("PageTitle")
        subtitle = QLabel(
            "Configure seu vídeo e comece a criar com o TakeDream."
        )
        subtitle.setObjectName("PageSubtitle")
        header_text.addWidget(title)
        header_text.addWidget(subtitle)

        header.addWidget(plus)
        header.addSpacing(8)
        header.addLayout(header_text)
        header.addStretch(1)

        close_button = QPushButton("Fechar")
        close_button.clicked.connect(self.reject)
        self.cancel_button = close_button
        header.addWidget(close_button)

        content_layout.addLayout(header)

        columns = QHBoxLayout()
        columns.setSpacing(12)

        # --------------------------------------------------------------
        # LEFT / FORM
        # --------------------------------------------------------------
        form_card = QFrame()
        form_card.setObjectName("SoftCard")
        form_card.setMinimumWidth(610)
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(18, 16, 18, 16)
        form_layout.setSpacing(12)

        form_layout.addWidget(
            self._numbered_title(
                "1",
                "Informações do projeto",
            )
        )

        info_row = QHBoxLayout()
        info_row.setSpacing(12)

        name_box = QVBoxLayout()
        name_label = QLabel("Nome do projeto")
        name_label.setStyleSheet(
            "font-weight:700; color:#17152A;"
        )
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Minha edição incrível")
        self.name_input.setStyleSheet(
            "QLineEdit {background:#FFFFFF; color:#19172B;"
            "border:1px solid #D7D4E8; border-radius:9px;"
            "padding:9px 11px;}"
            "QLineEdit:focus {border:2px solid #8B5CF6;}"
        )
        name_box.addWidget(name_label)
        name_box.addWidget(self.name_input)

        video_box = QVBoxLayout()
        video_label = QLabel("Arquivo de vídeo")
        video_label.setStyleSheet(
            "font-weight:700; color:#17152A;"
        )
        self.video_button = QPushButton("Selecionar vídeo")
        self.video_button.setStyleSheet(
            "QPushButton {background:#FFFFFF; color:#302A51;"
            "border:1px dashed #A7A0C5; border-radius:9px;"
            "padding:9px 11px; text-align:left;}"
            "QPushButton:hover {border:2px solid #8B5CF6;}"
        )
        self.video_button.clicked.connect(self.select_video)
        self.select_video_button = self.video_button
        video_box.addWidget(video_label)
        video_box.addWidget(self.video_button)

        info_row.addLayout(name_box, 1)
        info_row.addLayout(video_box, 1)
        form_layout.addLayout(info_row)

        self.video_input = QLineEdit()
        self.video_input.hide()

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background:#E7E4EF;")
        form_layout.addWidget(divider)

        form_layout.addWidget(
            self._numbered_title(
                "2",
                "Perfil do conteúdo",
                "Isso ajuda a otimizar a edição para seu tipo de vídeo.",
            )
        )

        self.profile_group = QButtonGroup(self)
        self.profile_group.setExclusive(True)
        self.profile_buttons = {}

        profile_grid = QGridLayout()
        profile_grid.setHorizontalSpacing(8)
        profile_grid.setVerticalSpacing(8)

        for index, profile in enumerate(profile_names()):
            definition = get_profile_definition(profile)
            short_name = (
                "Shorts"
                if profile == "Shorts / Reels / TikTok"
                else profile
            )
            text = (
                f"{PROFILE_ICONS.get(profile, '✦')}\n"
                f"{short_name}\n"
                f"{self._profile_short_description(profile)}"
            )
            button = QPushButton(text)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(98)
            button.setStyleSheet(
                "QPushButton {background:#FFFFFF; color:#29243F;"
                "border:1px solid #DCD8EA; border-radius:11px;"
                "padding:8px; font-weight:650;}"
                "QPushButton:hover {border:2px solid #B794F4;}"
                "QPushButton:checked {background:#FAF7FF;"
                "border:2px solid #8B5CF6; color:#241B45;}"
            )
            self.profile_group.addButton(button)
            self.profile_buttons[profile] = button
            button.clicked.connect(
                lambda checked=False, name=profile:
                self._set_profile(name)
            )
            profile_grid.addWidget(
                button,
                index // 4,
                index % 4,
            )

        form_layout.addLayout(profile_grid)

        form_layout.addWidget(
            self._numbered_title(
                "3",
                "Estilo de edição",
                "Escolha o ritmo e a personalidade do resultado.",
            )
        )

        self.style_buttons_layout = QHBoxLayout()
        self.style_buttons_layout.setSpacing(8)
        self.style_group = QButtonGroup(self)
        self.style_group.setExclusive(True)
        self.style_buttons = {}
        form_layout.addLayout(self.style_buttons_layout)

        form_layout.addWidget(
            self._numbered_title(
                "4",
                "Formato do vídeo",
                "Você pode usar qualquer formato em qualquer perfil.",
            )
        )

        self.aspect_group = QButtonGroup(self)
        self.aspect_group.setExclusive(True)
        self.aspect_buttons = {}
        aspect_row = QHBoxLayout()
        aspect_row.setSpacing(8)

        aspect_examples = {
            "16:9": "▰\n16:9\nYouTube, TV, PC",
            "9:16": "▯\n9:16\nShorts, Reels",
            "1:1": "□\n1:1\nFeed quadrado",
            "4:5": "▯\n4:5\nFeed retrato",
        }

        for aspect in ASPECT_RATIOS:
            button = QPushButton(aspect_examples[aspect.key])
            button.setCheckable(True)
            button.setMinimumHeight(82)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(
                "QPushButton {background:#FFFFFF; color:#29243F;"
                "border:1px solid #DCD8EA; border-radius:11px;"
                "padding:7px; font-weight:700;}"
                "QPushButton:hover {border:2px solid #B794F4;}"
                "QPushButton:checked {background:#FAF7FF;"
                "border:2px solid #8B5CF6; color:#241B45;}"
            )
            self.aspect_group.addButton(button)
            self.aspect_buttons[aspect.key] = button
            button.clicked.connect(
                lambda checked=False, key=aspect.key:
                self._set_aspect(key)
            )
            aspect_row.addWidget(button)

        form_layout.addLayout(aspect_row)
        form_layout.addStretch(1)

        # --------------------------------------------------------------
        # RIGHT / PREVIEW + SETTINGS
        # --------------------------------------------------------------
        right = QWidget()
        right.setMinimumWidth(390)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        preview_card = card()
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_layout.setSpacing(8)

        preview_header = QHBoxLayout()
        preview_header.addWidget(section_title("◉  Pré-visualização"))
        preview_header.addStretch(1)
        self.preview_aspect_label = QLabel(self.selected_aspect)
        self.preview_aspect_label.setStyleSheet(
            "background:#20294B; border:1px solid #46558A;"
            "border-radius:7px; padding:5px 8px; font-weight:700;"
        )
        preview_header.addWidget(self.preview_aspect_label)
        preview_layout.addLayout(preview_header)

        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumHeight(230)
        self.video_widget.setStyleSheet(
            "background:qlineargradient("
            "x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #1D2450, stop:0.55 #23396B, stop:1 #51245C);"
            "border-radius:10px;"
        )

        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.35)

        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)

        self.preview_play_button = QPushButton("▶  Reproduzir")
        self.preview_play_button.clicked.connect(self._toggle_preview)

        preview_layout.addWidget(self.video_widget, 1)
        preview_layout.addWidget(self.preview_play_button)
        preview_layout.addWidget(
            muted_label(
                "A prévia usa o vídeo escolhido. "
                "O resultado final será criado pelo pipeline do TakeDream.",
                True,
            )
        )
        right_layout.addWidget(preview_card, 2)

        settings_card = card()
        settings_layout = QVBoxLayout(settings_card)
        settings_layout.setContentsMargins(12, 12, 12, 12)
        settings_layout.setSpacing(9)

        settings_layout.addWidget(
            section_title("⚙  Configurações de exportação")
        )
        settings_layout.addWidget(
            muted_label("Qualidade preferida do vídeo")
        )

        self.quality_group = QButtonGroup(self)
        self.quality_group.setExclusive(True)
        self.quality_buttons = {}
        quality_row = QHBoxLayout()
        quality_row.setSpacing(6)

        quality_subtitles = {
            "original": "Original",
            "1080p": "Full HD",
            "720p": "HD",
            "480p": "SD",
            "360p": "Leve",
        }

        for profile in EXPORT_PROFILES:
            button = quality_button(
                profile.label,
                quality_subtitles.get(profile.key, ""),
                checked=(profile.key == "original"),
            )
            button.setMinimumWidth(60)
            self.quality_group.addButton(button)
            self.quality_buttons[profile.key] = button
            button.clicked.connect(
                lambda checked=False, key=profile.key:
                self._set_quality(key)
            )
            quality_row.addWidget(button)

        settings_layout.addLayout(quality_row)

        self.captions_checkbox = QCheckBox("Legendas automáticas")
        self.captions_checkbox.setChecked(False)
        settings_layout.addWidget(self.captions_checkbox)
        settings_layout.addWidget(
            muted_label(
                "Gera legendas usando a transcrição do projeto.",
                True,
            )
        )

        self.auto_zoom_checkbox = QCheckBox("Zoom automático")
        self.auto_zoom_checkbox.setChecked(False)
        settings_layout.addWidget(self.auto_zoom_checkbox)
        settings_layout.addWidget(
            muted_label(
                "Usa os momentos sugeridos pela análise de conteúdo.",
                True,
            )
        )

        self.caption_style = CAPTION_STYLES[1]

        right_layout.addWidget(settings_card, 2)

        self.create_button = QPushButton("✦  Criar Projeto  →")
        self.create_button.setProperty("primary", True)
        self.create_button.setMinimumHeight(48)
        self.create_button.clicked.connect(self.validate_and_accept)
        right_layout.addWidget(self.create_button)

        columns.addWidget(form_card, 3)
        columns.addWidget(right, 2)
        content_layout.addLayout(columns, 1)

        root.addWidget(content, 1)

        apply_app_theme(self)
        enable_dark_title_bar(self)
        self._set_profile(self.selected_profile)

    def _numbered_title(self, number, title, subtitle=None):
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        badge = QLabel(number)
        badge.setFixedSize(28, 28)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            "background:#7C3AED; color:#FFFFFF; border-radius:14px;"
            "font-weight:800;"
        )
        title_label = QLabel(title)
        title_label.setStyleSheet(
            "font-size:14px; font-weight:800; color:#17152A;"
        )

        layout.addWidget(badge)
        layout.addWidget(title_label)

        if subtitle:
            layout.addStretch(1)
            subtitle_label = QLabel(subtitle)
            subtitle_label.setStyleSheet(
                "color:#6B6880; font-size:11px;"
            )
            subtitle_label.setWordWrap(True)
            layout.addWidget(subtitle_label)

        return container

    def _profile_short_description(self, profile):
        descriptions = {
            "YouTube": "Vídeos completos",
            "Shorts / Reels / TikTok": "Vídeos curtos",
            "Podcast": "Conversas",
            "Casamento": "Momentos especiais",
            "Gaming": "Gameplay",
            "Curso": "Aulas",
            "VSL": "Conversão",
            "Institucional": "Corporativo",
        }
        return descriptions.get(profile, "")

    def _set_profile(self, profile):
        self.selected_profile = profile

        profile_index = self.profile_combo.findText(profile)
        if profile_index >= 0:
            blocked = self.profile_combo.blockSignals(True)
            self.profile_combo.setCurrentIndex(profile_index)
            self.profile_combo.blockSignals(blocked)

        for name, button in self.profile_buttons.items():
            blocked = button.blockSignals(True)
            button.setChecked(name == profile)
            button.blockSignals(blocked)

        styles = styles_for_profile(profile)
        self.style_combo.clear()
        self.style_combo.addItems(styles)
        self.selected_style = styles[0]
        self._rebuild_style_buttons(styles)

        suggested = get_profile_definition(profile).aspect_ratio
        self._set_aspect(suggested)

    def _rebuild_style_buttons(self, styles):
        while self.style_buttons_layout.count():
            item = self.style_buttons_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self.style_group = QButtonGroup(self)
        self.style_group.setExclusive(True)
        self.style_buttons = {}

        descriptions = {
            "Clean": "Limpo e moderno",
            "Dinâmico": "Ritmo acelerado",
            "Conversa": "Natural",
            "Highlights": "Melhores momentos",
            "Didático": "Clareza e ensino",
            "Conversão": "Foco em retenção",
            "Premium": "Visual sofisticado",
            "Highlight": "Resumo emocional",
            "Cinematográfico": "Ritmo de filme",
        }

        for index, style in enumerate(styles):
            button = QPushButton(
                f"{'✦' if index == 0 else '◇'}\n"
                f"{style}\n"
                f"{descriptions.get(style, 'Estilo personalizado')}"
            )
            button.setCheckable(True)
            button.setMinimumHeight(72)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(
                "QPushButton {background:#FFFFFF; color:#29243F;"
                "border:1px solid #DCD8EA; border-radius:11px;"
                "padding:7px; font-weight:700;}"
                "QPushButton:hover {border:2px solid #B794F4;}"
                "QPushButton:checked {background:#FAF7FF;"
                "border:2px solid #8B5CF6; color:#241B45;}"
            )
            self.style_group.addButton(button)
            self.style_buttons[style] = button
            button.clicked.connect(
                lambda checked=False, name=style:
                self._set_style(name)
            )
            self.style_buttons_layout.addWidget(button)

        self._set_style(styles[0])

    def _set_style(self, style):
        self.selected_style = style

        style_index = self.style_combo.findText(style)
        if style_index >= 0:
            blocked = self.style_combo.blockSignals(True)
            self.style_combo.setCurrentIndex(style_index)
            self.style_combo.blockSignals(blocked)
        for name, button in self.style_buttons.items():
            blocked = button.blockSignals(True)
            button.setChecked(name == style)
            button.blockSignals(blocked)

    def _set_aspect(self, aspect):
        self.selected_aspect = aspect
        self.preview_aspect_label.setText(aspect)

        aspect_index = self.aspect_combo.findData(aspect)
        if aspect_index >= 0:
            blocked = self.aspect_combo.blockSignals(True)
            self.aspect_combo.setCurrentIndex(aspect_index)
            self.aspect_combo.blockSignals(blocked)

        for key, button in self.aspect_buttons.items():
            blocked = button.blockSignals(True)
            button.setChecked(key == aspect)
            button.blockSignals(blocked)

    def _set_quality(self, quality):
        self.selected_quality = quality

        for key, button in self.quality_buttons.items():
            blocked = button.blockSignals(True)
            button.setChecked(key == quality)
            button.blockSignals(blocked)

    def _sidebar_nav(self, target):
        if target == "new":
            return

        parent = self.parent()
        if parent is not None and hasattr(parent, "_navigate"):
            self.reject()
            parent._navigate(target)

    def select_video(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar vídeo",
            "",
            "Vídeos (*.mp4 *.mov *.mkv *.avi *.webm *.m4v);;"
            "Todos os arquivos (*)",
        )

        if not file_path:
            return

        self.video_input.setText(file_path)

        name = Path(file_path).name
        self.video_button.setText(f"▣  {name}   ×")
        self.player.setSource(
            QUrl.fromLocalFile(file_path)
        )

        if not self.name_input.text().strip():
            self.name_input.setText(
                Path(file_path).stem[:80]
            )

    def _toggle_preview(self):
        if (
            self.player.playbackState()
            == QMediaPlayer.PlaybackState.PlayingState
        ):
            self.player.pause()
            self.preview_play_button.setText("▶  Reproduzir")
        else:
            self.player.play()
            self.preview_play_button.setText("Ⅱ  Pausar")

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

        self.player.stop()
        self.accept()

    def reject(self):
        self.player.stop()
        super().reject()

    def project_data(self):
        return {
            "name": self.name_input.text().strip(),
            "source_video": self.video_input.text().strip(),
            "profile": self.selected_profile,
            "style": self.selected_style,
            "aspect_ratio": self.selected_aspect,
            "captions_enabled": self.captions_checkbox.isChecked(),
            "auto_zoom": self.auto_zoom_checkbox.isChecked(),
            "caption_style": self.caption_style,
            "export_quality": self.selected_quality,
        }
