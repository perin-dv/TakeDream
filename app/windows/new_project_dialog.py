from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QButtonGroup,
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
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.ui.components import (
    AspectCardButton,
    ModernSwitch,
    QualityCardButton,
    SelectionCardButton,
    card,
    muted_label,
    section_title,
)
from app.ui.icons import app_icon, icon_pixmap
from app.ui.shell import TakeDreamSidebar
from app.ui.theme import apply_app_theme
from app.ui.wedding_setup import WeddingSetupWidget
from app.ui.windows import enable_dark_title_bar
from core.media_library import discover_media
from profiles import (
    get_edit_rules,
    get_profile_definition,
    get_style_preset,
    profile_names,
    styles_for_profile,
)
from renderer.captions import CAPTION_STYLES
from renderer.export_profiles import EXPORT_PROFILES
from renderer.formats import ASPECT_RATIOS


PROFILE_ICONS = {
    "YouTube": "youtube",
    "Shorts / Reels / TikTok": "shorts",
    "Podcast": "podcast",
    "Casamento": "wedding",
    "Gaming": "gaming",
    "Curso": "course",
    "VSL": "vsl",
    "Institucional": "institutional",
}


class NewProjectDialog(QDialog):
    def __init__(self, parent=None, *, embedded=False, host=None):
        super().__init__(parent)
        self.embedded = embedded
        self.host = host
        if embedded:
            self.setWindowFlags(Qt.WindowType.Widget)

        self.setWindowTitle("TakeDream — Novo Projeto")
        self.resize(1360, 840)
        self.setMinimumSize(1120, 720)

        self.selected_profile = profile_names()[0]
        self.selected_style = styles_for_profile(self.selected_profile)[0]
        self.selected_aspect = get_profile_definition(
            self.selected_profile
        ).aspect_ratio
        self.selected_quality = "original"
        self.selected_media_paths = []
        self.caption_style = CAPTION_STYLES[1]

        # Contrato legado mantido para testes e integrações internas.
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
        content.setMinimumWidth(1060)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(22, 20, 22, 18)
        content_layout.setSpacing(14)

        header = QHBoxLayout()
        header_icon = QLabel()
        header_icon.setFixedSize(48, 48)
        header_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_icon.setPixmap(
            icon_pixmap("plus", color="#FFFFFF", accent="#C084FC", size=34)
        )
        header_icon.setStyleSheet("background:#6D28D9; border-radius:24px;")
        header_text = QVBoxLayout()
        header_text.setSpacing(0)
        title = QLabel("Novo Projeto")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Configure suas mídias e comece a criar com o TakeDream.")
        subtitle.setObjectName("PageSubtitle")
        header_text.addWidget(title)
        header_text.addWidget(subtitle)
        header.addWidget(header_icon)
        header.addSpacing(8)
        header.addLayout(header_text)
        header.addStretch(1)
        self.cancel_button = QPushButton("Voltar" if embedded else "Fechar")
        self.cancel_button.clicked.connect(self._close_page)
        header.addWidget(self.cancel_button)
        content_layout.addLayout(header)

        columns = QHBoxLayout()
        columns.setSpacing(12)

        form_card = QFrame()
        form_card.setObjectName("SoftCard")
        form_card.setMinimumWidth(610)
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(18, 16, 18, 16)
        form_layout.setSpacing(12)

        form_layout.addWidget(self._numbered_title("1", "Informações do projeto"))
        info_row = QHBoxLayout()
        info_row.setSpacing(12)

        name_box = QVBoxLayout()
        name_label = QLabel("Nome do projeto")
        name_label.setStyleSheet("font-weight:700; color:#17152A;")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Minha edição incrível")
        self.name_input.setStyleSheet(
            "QLineEdit {background:#FFFFFF; color:#19172B;"
            "border:1px solid #D7D4E8; border-radius:9px; padding:9px 11px;}"
            "QLineEdit:focus {border:2px solid #8B5CF6;}"
        )
        name_box.addWidget(name_label)
        name_box.addWidget(self.name_input)

        video_box = QVBoxLayout()
        video_label = QLabel("Mídias do projeto")
        video_label.setStyleSheet("font-weight:700; color:#17152A;")
        media_buttons = QHBoxLayout()
        media_buttons.setSpacing(6)
        self.video_button = QPushButton("Selecionar vídeos")
        self.video_button.setIcon(
            app_icon("video", color="#5B4A85", accent="#8B5CF6", size=18)
        )
        self.video_button.setStyleSheet(self._media_button_style())
        self.video_button.clicked.connect(self.select_video)
        self.select_video_button = self.video_button
        self.folder_button = QPushButton("Adicionar pasta")
        self.folder_button.setIcon(
            app_icon("folder", color="#5B4A85", accent="#8B5CF6", size=18)
        )
        self.folder_button.setStyleSheet(self._media_button_style())
        self.folder_button.clicked.connect(self.select_media_folder)
        media_buttons.addWidget(self.video_button, 1)
        media_buttons.addWidget(self.folder_button, 1)
        self.media_count_label = QLabel(
            "Nenhuma mídia selecionada. Você pode escolher vários vídeos ou uma pasta inteira."
        )
        self.media_count_label.setWordWrap(True)
        self.media_count_label.setStyleSheet("font-size:11px; color:#6B6880;")
        video_box.addWidget(video_label)
        video_box.addLayout(media_buttons)
        video_box.addWidget(self.media_count_label)
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
            short_name = "Shorts" if profile == "Shorts / Reels / TikTok" else profile
            button = SelectionCardButton(
                short_name,
                self._profile_short_description(profile),
                PROFILE_ICONS.get(profile, "sparkles"),
                accent=self._profile_accent(profile),
                light=True,
            )
            self.profile_group.addButton(button)
            self.profile_buttons[profile] = button
            button.clicked.connect(
                lambda checked=False, name=profile: self._set_profile(name)
            )
            profile_grid.addWidget(button, index // 4, index % 4)
        form_layout.addLayout(profile_grid)

        # Só aparece quando o perfil Casamento está ativo.
        self.wedding_setup = WeddingSetupWidget()
        self.wedding_setup.setVisible(False)
        form_layout.addWidget(self.wedding_setup)

        form_layout.addWidget(
            self._numbered_title(
                "3", "Estilo de edição", "Escolha o ritmo e a personalidade do resultado."
            )
        )
        self.style_buttons_layout = QGridLayout()
        self.style_buttons_layout.setHorizontalSpacing(8)
        self.style_buttons_layout.setVerticalSpacing(8)
        self.style_group = QButtonGroup(self)
        self.style_group.setExclusive(True)
        self.style_buttons = {}
        form_layout.addLayout(self.style_buttons_layout)

        form_layout.addWidget(
            self._numbered_title(
                "4", "Formato do vídeo", "Você pode usar qualquer formato em qualquer perfil."
            )
        )
        self.aspect_group = QButtonGroup(self)
        self.aspect_group.setExclusive(True)
        self.aspect_buttons = {}
        aspect_row = QHBoxLayout()
        aspect_row.setSpacing(8)
        aspect_examples = {
            "16:9": "YouTube, TV, PC",
            "9:16": "Shorts, Reels, TikTok",
            "1:1": "Instagram Feed",
            "4:5": "Instagram, Facebook",
        }
        for aspect in ASPECT_RATIOS:
            button = AspectCardButton(aspect.key, aspect_examples[aspect.key])
            self.aspect_group.addButton(button)
            self.aspect_buttons[aspect.key] = button
            button.clicked.connect(
                lambda checked=False, key=aspect.key: self._set_aspect(key)
            )
            aspect_row.addWidget(button)
        form_layout.addLayout(aspect_row)
        form_layout.addStretch(1)

        # Direita: preview e configurações.
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
        preview_header.addWidget(section_title("Pré-visualização", "preview"))
        preview_header.addStretch(1)
        self.preview_aspect_label = QLabel(self.selected_aspect)
        self.preview_aspect_label.setStyleSheet(
            "background:#20294B; border:1px solid #46558A;"
            "border-radius:7px; padding:5px 8px; font-weight:700;"
        )
        preview_header.addWidget(self.preview_aspect_label)
        preview_layout.addLayout(preview_header)

        self.preview_stack = QStackedWidget()
        self.preview_stack.setMinimumHeight(230)
        self.preview_stack.setStyleSheet(
            "QStackedWidget {background:#070B18; border:1px solid #34416F; border-radius:11px;}"
        )
        placeholder = QFrame()
        placeholder.setObjectName("PreviewPlaceholder")
        placeholder.setStyleSheet(
            "QFrame#PreviewPlaceholder {background:qlineargradient("
            "x1:0,y1:0,x2:1,y2:1,stop:0 #241A55,stop:.48 #18365F,stop:1 #54215E);"
            "border-radius:10px;}"
        )
        placeholder_layout = QVBoxLayout(placeholder)
        placeholder_layout.setContentsMargins(20, 28, 20, 28)
        placeholder_layout.addStretch(1)
        preview_icon = QLabel()
        preview_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_icon.setPixmap(
            icon_pixmap("video", color="#FFFFFF", accent="#D8B4FE", size=54)
        )
        preview_title = QLabel("Selecione um vídeo para visualizar")
        preview_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_title.setStyleSheet("font-size:15px; font-weight:800; color:#FFFFFF;")
        preview_hint = QLabel(
            "A prévia usa a primeira mídia. As demais entram no Media Bin do projeto."
        )
        preview_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_hint.setWordWrap(True)
        preview_hint.setStyleSheet("font-size:11px; color:#C7CDED;")
        placeholder_layout.addWidget(preview_icon)
        placeholder_layout.addWidget(preview_title)
        placeholder_layout.addWidget(preview_hint)
        placeholder_layout.addStretch(1)
        self.video_widget = QVideoWidget()
        self.video_widget.setStyleSheet("background:#050814; border-radius:10px;")
        self.preview_stack.addWidget(placeholder)
        self.preview_stack.addWidget(self.video_widget)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.35)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)
        self.preview_play_button = QPushButton("Reproduzir")
        self.preview_play_button.setIcon(
            app_icon("play", color="#FFFFFF", accent="#C084FC", size=17)
        )
        self.preview_play_button.clicked.connect(self._toggle_preview)
        preview_layout.addWidget(self.preview_stack, 1)
        preview_layout.addWidget(self.preview_play_button)
        preview_layout.addWidget(
            muted_label(
                "A primeira mídia fica como prévia. Arquivos grandes permanecem no local original.",
                True,
            )
        )
        right_layout.addWidget(preview_card, 2)

        settings_card = card()
        settings_layout = QVBoxLayout(settings_card)
        settings_layout.setContentsMargins(12, 12, 12, 12)
        settings_layout.setSpacing(9)
        settings_layout.addWidget(section_title("Configurações de exportação", "settings"))
        settings_layout.addWidget(muted_label("Qualidade preferida do vídeo"))
        self.quality_group = QButtonGroup(self)
        self.quality_group.setExclusive(True)
        self.quality_buttons = {}
        quality_row = QHBoxLayout()
        quality_row.setSpacing(6)
        quality_meta = {
            "original": ("ORIGINAL", "Fonte"),
            "1080p": ("FULL HD", "Melhor"),
            "720p": ("HD", "Leve"),
            "480p": ("SD", "Menor"),
            "360p": ("LEVE", "Compacto"),
        }
        for export_profile in EXPORT_PROFILES:
            badge, subtitle = quality_meta.get(export_profile.key, ("VIDEO", ""))
            button = QualityCardButton(export_profile.label, badge, subtitle)
            button.setChecked(export_profile.key == "original")
            self.quality_group.addButton(button)
            self.quality_buttons[export_profile.key] = button
            button.clicked.connect(
                lambda checked=False, key=export_profile.key: self._set_quality(key)
            )
            quality_row.addWidget(button)
        settings_layout.addLayout(quality_row)
        self.captions_checkbox = ModernSwitch("Legendas automáticas")
        settings_layout.addWidget(self.captions_checkbox)
        settings_layout.addWidget(
            muted_label("Gera legendas usando a transcrição do projeto.", True)
        )
        self.auto_zoom_checkbox = ModernSwitch("Zoom automático")
        settings_layout.addWidget(self.auto_zoom_checkbox)
        settings_layout.addWidget(
            muted_label("Quando ligado, sua escolha tem prioridade sobre o preset.", True)
        )
        right_layout.addWidget(settings_card, 2)

        style_summary_card = card()
        summary_layout = QVBoxLayout(style_summary_card)
        summary_layout.setContentsMargins(12, 11, 12, 11)
        summary_layout.addWidget(section_title("Como o TakeDream vai editar", "ai"))
        self.style_summary_label = QLabel()
        self.style_summary_label.setProperty("muted", True)
        self.style_summary_label.setWordWrap(True)
        summary_layout.addWidget(self.style_summary_label)
        right_layout.addWidget(style_summary_card)

        self.create_button = QPushButton("Criar Projeto")
        self.create_button.setIcon(
            app_icon("sparkles", color="#FFFFFF", accent="#FFFFFF", size=18)
        )
        self.create_button.setProperty("primary", True)
        self.create_button.setMinimumHeight(48)
        self.create_button.clicked.connect(self.validate_and_accept)
        right_layout.addWidget(self.create_button)

        columns.addWidget(form_card, 3)
        columns.addWidget(right, 2)
        content_layout.addLayout(columns, 1)

        page_scroll = QScrollArea()
        page_scroll.setObjectName("AppPageScroll")
        page_scroll.viewport().setObjectName("AppPageViewport")
        page_scroll.setWidgetResizable(True)
        page_scroll.setWidget(content)
        page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        page_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        root.addWidget(page_scroll, 1)

        apply_app_theme(self)
        if not embedded:
            enable_dark_title_bar(self)
        self._set_profile(self.selected_profile)

    @staticmethod
    def _media_button_style():
        return (
            "QPushButton {background:#FFFFFF; color:#302A51;"
            "border:1px dashed #A7A0C5; border-radius:9px;"
            "padding:9px 11px; text-align:left;}"
            "QPushButton:hover {border:2px solid #8B5CF6;}"
        )

    def _numbered_title(self, number, title, subtitle=None):
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        badge = QLabel(number)
        badge.setFixedSize(28, 28)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            "background:#7C3AED; color:#FFFFFF; border-radius:14px; font-weight:800;"
        )
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size:14px; font-weight:800; color:#17152A;")
        layout.addWidget(badge)
        layout.addWidget(title_label)
        if subtitle:
            layout.addStretch(1)
            subtitle_label = QLabel(subtitle)
            subtitle_label.setStyleSheet("color:#6B6880; font-size:11px;")
            subtitle_label.setWordWrap(True)
            layout.addWidget(subtitle_label)
        return container

    def _profile_short_description(self, profile):
        return {
            "YouTube": "Vídeos completos",
            "Shorts / Reels / TikTok": "Vídeos curtos",
            "Podcast": "Conversas",
            "Casamento": "Momentos especiais",
            "Gaming": "Gameplay",
            "Curso": "Aulas",
            "VSL": "Conversão",
            "Institucional": "Corporativo",
        }.get(profile, "")

    @staticmethod
    def _profile_accent(profile):
        return {
            "YouTube": "#EF4444",
            "Shorts / Reels / TikTok": "#F43F5E",
            "Podcast": "#6366F1",
            "Casamento": "#D99A4E",
            "Gaming": "#7C3AED",
            "Curso": "#3B82F6",
            "VSL": "#C026D3",
            "Institucional": "#64748B",
        }.get(profile, "#8B5CF6")

    def _set_profile(self, profile):
        self.selected_profile = profile
        index = self.profile_combo.findText(profile)
        if index >= 0:
            blocked = self.profile_combo.blockSignals(True)
            self.profile_combo.setCurrentIndex(index)
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
        self._set_aspect(get_profile_definition(profile).aspect_ratio)
        self.wedding_setup.setVisible(profile == "Casamento")

        if not self.selected_media_paths:
            if profile == "Casamento":
                self.media_count_label.setText(
                    "Casamento aceita vários vídeos ou uma pasta inteira. Os arquivos ficam no local original."
                )
            else:
                self.media_count_label.setText(
                    "Nenhuma mídia selecionada. Você pode escolher vários vídeos ou uma pasta inteira."
                )

    def _rebuild_style_buttons(self, styles):
        while self.style_buttons_layout.count():
            item = self.style_buttons_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.style_group = QButtonGroup(self)
        self.style_group.setExclusive(True)
        self.style_buttons = {}
        for index, style in enumerate(styles):
            preset = get_style_preset(style)
            button = SelectionCardButton(
                style,
                preset.description,
                preset.icon,
                accent=preset.accent,
                light=True,
            )
            button.setMinimumHeight(92)
            button.setToolTip(
                f"{preset.description}\nZoom: {'automático' if preset.auto_zoom else 'discreto/manual'} • "
                f"Legenda: {preset.caption_style}"
            )
            self.style_group.addButton(button)
            self.style_buttons[style] = button
            button.clicked.connect(
                lambda checked=False, name=style: self._set_style(name)
            )
            self.style_buttons_layout.addWidget(button, index // 3, index % 3)
        self._set_style(styles[0])

    def _set_style(self, style):
        self.selected_style = style
        preset = get_style_preset(style)
        index = self.style_combo.findText(style)
        if index >= 0:
            blocked = self.style_combo.blockSignals(True)
            self.style_combo.setCurrentIndex(index)
            self.style_combo.blockSignals(blocked)
        for name, button in self.style_buttons.items():
            blocked = button.blockSignals(True)
            button.setChecked(name == style)
            button.blockSignals(blocked)
        self.caption_style = preset.caption_style
        blocked = self.captions_checkbox.blockSignals(True)
        self.captions_checkbox.setChecked(preset.captions_enabled)
        self.captions_checkbox.blockSignals(blocked)
        blocked = self.auto_zoom_checkbox.blockSignals(True)
        self.auto_zoom_checkbox.setChecked(preset.auto_zoom)
        self.auto_zoom_checkbox.blockSignals(blocked)

        rules = get_edit_rules(self.selected_profile, style)
        silence = (
            f"{rules.minimum_silence_ms / 1000:.2f}s"
            if rules.automatic_silence_cuts
            else "desativado"
        )
        zoom = (
            f"{preset.zoom_scale:.2f}x a cada ~{preset.zoom_gap_ms // 1000}s"
            if preset.zoom_enabled
            else "opcional/manual"
        )
        broll = f"~{preset.broll_gap_ms // 1000}s" if preset.broll_enabled else "seletor visual"
        captions = preset.caption_style if preset.captions_enabled else "opcional"
        self.style_summary_label.setText(
            f"{preset.description}. Pausa mínima: {silence} • Zoom: {zoom} • "
            f"Legenda: {captions} • B-roll: {broll}."
        )

    def _set_aspect(self, aspect):
        self.selected_aspect = aspect
        self.preview_aspect_label.setText(aspect)
        index = self.aspect_combo.findData(aspect)
        if index >= 0:
            blocked = self.aspect_combo.blockSignals(True)
            self.aspect_combo.setCurrentIndex(index)
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
        self.player.stop()
        if self.host is not None and hasattr(self.host, "_navigate"):
            self.host._navigate(target)
            return
        parent = self.parent()
        if parent is not None and hasattr(parent, "_navigate"):
            self.reject()
            parent._navigate(target)

    def _close_page(self):
        self.player.stop()
        if self.embedded and self.host is not None:
            self.host._navigate("home")
            return
        self.reject()

    def _add_media_paths(self, inputs):
        discovered = discover_media(inputs)
        if not discovered:
            return 0
        existing = {
            str(Path(value).expanduser().resolve()).lower()
            for value in self.selected_media_paths
        }
        added = 0
        for path in discovered:
            key = str(path.resolve()).lower()
            if key in existing:
                continue
            self.selected_media_paths.append(str(path.resolve()))
            existing.add(key)
            added += 1
        self._refresh_media_selection()
        return added

    def _refresh_media_selection(self):
        if not self.selected_media_paths:
            self.video_input.clear()
            self.video_button.setText("Selecionar vídeos")
            self.media_count_label.setText("Nenhuma mídia selecionada.")
            return
        primary = self.selected_media_paths[0]
        self.video_input.setText(primary)
        count = len(self.selected_media_paths)
        if count == 1:
            self.video_button.setText(Path(primary).name)
            self.media_count_label.setText("1 vídeo selecionado • usado também como prévia principal.")
        else:
            self.video_button.setText(f"{count} vídeos selecionados")
            self.media_count_label.setText(
                f"{count} vídeos no Media Bin • prévia: {Path(primary).name}."
            )
        self.player.setSource(QUrl.fromLocalFile(primary))
        self.preview_stack.setCurrentWidget(self.video_widget)
        if not self.name_input.text().strip():
            self.name_input.setText(Path(primary).stem[:80])

    def select_video(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Selecionar vídeos",
            "",
            "Vídeos (*.mp4 *.mov *.mkv *.avi *.webm *.m4v);;Todos os arquivos (*)",
        )
        if file_paths:
            self._add_media_paths(file_paths)

    def select_media_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Selecionar pasta com vídeos", "")
        if not folder:
            return
        if self._add_media_paths([folder]) == 0:
            QMessageBox.information(
                self,
                "Nenhum vídeo encontrado",
                "A pasta selecionada não possui vídeos compatíveis. O TakeDream procura também nas subpastas.",
            )

    def _toggle_preview(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.preview_play_button.setText("Reproduzir")
            self.preview_play_button.setIcon(
                app_icon("play", color="#FFFFFF", accent="#C084FC", size=17)
            )
        else:
            self.player.play()
            self.preview_play_button.setText("Pausar")
            self.preview_play_button.setIcon(
                app_icon("pause", color="#FFFFFF", accent="#C084FC", size=17)
            )

    def validate_and_accept(self):
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "Nome obrigatório", "Informe um nome para o projeto.")
            return
        if not self.selected_media_paths and not self.video_input.text().strip():
            QMessageBox.warning(
                self,
                "Vídeo obrigatório",
                "Selecione pelo menos um vídeo ou uma pasta para o projeto.",
            )
            return
        self.player.stop()
        if self.embedded and self.host is not None:
            self.host._create_project_from_data(self.project_data())
            return
        self.accept()

    def reject(self):
        self.player.stop()
        super().reject()

    def project_data(self):
        media = list(self.selected_media_paths)
        if not media and self.video_input.text().strip():
            media = [self.video_input.text().strip()]
        primary = media[0] if media else ""
        data = {
            "name": self.name_input.text().strip(),
            "source_video": primary,
            "source_videos": media[1:],
            "profile": self.selected_profile,
            "style": self.selected_style,
            "aspect_ratio": self.selected_aspect,
            "captions_enabled": self.captions_checkbox.isChecked(),
            "auto_zoom": self.auto_zoom_checkbox.isChecked(),
            "caption_style": self.caption_style,
            "export_quality": self.selected_quality,
        }
        if self.selected_profile == "Casamento":
            data.update(self.wedding_setup.data())
        else:
            data.update(
                {
                    "deliverable_type": None,
                    "target_duration_seconds": None,
                    "reference_video": None,
                    "music_path": None,
                }
            )
        return data
