from copy import deepcopy
import wave

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import (
    QDesktopServices,
    QKeySequence,
    QShortcut,
)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from app.review_worker import ReviewWorker
from app.ui.components import (
    card,
    info_row,
    muted_label,
    nav_button,
    option_button,
    quality_button,
    section_title,
)
from app.ui.theme import apply_review_theme
from app.widgets.timeline_widget import TimelineWidget
from core.content_pipeline import load_content_analysis
from core.edit_pipeline import load_edit_state
from core.project_manager import ProjectManager
from core.render_settings import normalize_render_settings
from media.thumbnails import load_thumbnail_manifest
from media.waveform import load_or_create_waveform
from editor.review import (
    adjust_removed_segment,
    edited_to_source_ms,
    remove_range,
    remove_segment,
    restore_cut,
    segment_index_at,
    source_to_edited_ms,
    split_at,
)
from renderer.captions import CAPTION_STYLES
from renderer.export_profiles import EXPORT_PROFILES
from renderer.formats import ASPECT_RATIOS


class ReviewWindow(QMainWindow):
    def __init__(self, project_dir, parent=None):
        super().__init__(parent)

        self.project_manager = ProjectManager()
        self.project_dir, self.project_data = (
            self.project_manager.load_project(project_dir)
        )

        state = load_edit_state(self.project_dir)
        if state["edit_errors"]:
            raise ValueError("\n".join(state["edit_errors"]))
        if state["edit_plan"] is None:
            raise ValueError(
                "Nenhum edit_plan.json válido foi encontrado."
            )
        if not state["output_path"]:
            raise ValueError(
                "Nenhuma prévia renderizada foi encontrada."
            )

        self.plan = deepcopy(state["edit_plan"])
        self.saved_plan = deepcopy(state["edit_plan"])
        self.output_path = state["output_path"]

        self.saved_settings = normalize_render_settings(
            self.project_data.get("review_settings"),
            self.project_data,
        )
        self.render_settings = deepcopy(self.saved_settings)
        self.content_analysis = load_content_analysis(
            self.project_dir
        )

        self.worker = None
        self._close_pending = False
        self._dirty = False

        self.undo_stack = []
        self.redo_stack = []
        self.mark_in_ms = None
        self.mark_out_ms = None

        self.setWindowTitle(
            f"TakeDream — Revisão — {self.project_data['name']}"
        )
        self.resize(1480, 920)
        self.setMinimumSize(1180, 760)

        root = QWidget()
        root.setObjectName("Root")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ==============================================================
        # SIDEBAR
        # ==============================================================
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(205)

        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(18, 24, 18, 20)
        sidebar_layout.setSpacing(8)

        brand = QLabel("☁  TakeDream")
        brand.setObjectName("Brand")
        brand.setStyleSheet(
            "font-size:24px; font-weight:800; color:#FFFFFF;"
        )
        brand_subtitle = muted_label(
            "Transforme vídeos\nem histórias incríveis."
        )

        sidebar_layout.addWidget(brand)
        sidebar_layout.addWidget(brand_subtitle)
        sidebar_layout.addSpacing(24)

        nav_items = (
            ("⌂", "Início", False),
            ("＋", "Novo Projeto", False),
            ("▣", "Projetos", False),
            ("✂", "Revisão", True),
            ("⇧", "Exportações", False),
            ("⚙", "Configurações", False),
        )
        for icon_text, text, active in nav_items:
            button = nav_button(
                icon_text,
                text,
                active=active,
            )
            if not active:
                button.clicked.connect(
                    lambda checked=False, name=text:
                    self.status_label.setText(
                        f"{name}: navegação visual preparada "
                        "para o próximo redesign."
                    )
                )
            sidebar_layout.addWidget(button)

        sidebar_layout.addStretch(1)

        dream_card = QFrame()
        dream_card.setObjectName("Card")
        dream_card.setStyleSheet(
            "QFrame#Card {"
            "background:qlineargradient("
            "x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #24155B, stop:1 #3B1C70);"
            "border:1px solid #7C5CE7;"
            "border-radius:14px;}"
        )
        dream_layout = QVBoxLayout(dream_card)
        dream_layout.setContentsMargins(14, 14, 14, 14)
        dream_layout.setSpacing(6)

        dream_title = QLabel("✦  Crie. Edite. Sonhe.")
        dream_title.setStyleSheet(
            "font-weight:800; color:#FFFFFF; font-size:13px;"
        )
        dream_text = muted_label(
            "A IA monta o primeiro corte.\n"
            "Você controla o resultado.",
            True,
        )
        dream_art = QLabel("✧  ⚔  ✦  ◈")
        dream_art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dream_art.setStyleSheet(
            "font-size:22px; color:#D8B4FE; padding-top:6px;"
        )

        dream_layout.addWidget(dream_title)
        dream_layout.addWidget(dream_text)
        dream_layout.addWidget(dream_art)
        sidebar_layout.addWidget(dream_card)

        # ==============================================================
        # MAIN CONTENT WRAPPER
        # ==============================================================
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(18, 18, 18, 16)
        content_layout.setSpacing(14)

        header_row = QHBoxLayout()
        header_icon = QLabel("✂")
        header_icon.setFixedSize(42, 42)
        header_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_icon.setStyleSheet(
            "background:#6D28D9; border-radius:21px;"
            "font-size:19px; font-weight:800;"
        )

        header_texts = QVBoxLayout()
        header_texts.setSpacing(0)
        title = QLabel("Revisão da edição")
        title.setObjectName("PageTitle")
        subtitle = QLabel(
            "Ajuste o resultado e veja como o vídeo vai ficar."
        )
        subtitle.setObjectName("PageSubtitle")
        header_texts.addWidget(title)
        header_texts.addWidget(subtitle)

        header_row.addWidget(header_icon)
        header_row.addSpacing(8)
        header_row.addLayout(header_texts)
        header_row.addStretch(1)

        self.status_label = QLabel(
            "Prévia carregada. Revise os cortes."
        )
        self.status_label.setProperty("muted", True)
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignVCenter
        )
        self.status_label.setWordWrap(True)
        self.status_label.setMaximumWidth(380)
        header_row.addWidget(self.status_label)

        content_layout.addLayout(header_row)

        body = QHBoxLayout()
        body.setSpacing(12)

        # ==============================================================
        # CENTER EDITOR
        # ==============================================================
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(10)

        project_bar = card()
        project_bar_layout = QHBoxLayout(project_bar)
        project_bar_layout.setContentsMargins(14, 10, 14, 10)
        project_bar_layout.setSpacing(10)

        project_name = QLabel(
            self.project_data.get("name", "Projeto")
        )
        project_name.setObjectName("ProjectTitle")
        project_bar_layout.addWidget(project_name)
        project_bar_layout.addStretch(1)

        self.aspect_combo = QComboBox()
        for aspect in ASPECT_RATIOS:
            self.aspect_combo.addItem(
                aspect.label,
                aspect.key,
            )
        aspect_index = self.aspect_combo.findData(
            self.render_settings["aspect_ratio"]
        )
        if aspect_index >= 0:
            self.aspect_combo.setCurrentIndex(aspect_index)
        self.aspect_combo.hide()

        self.aspect_buttons = {}
        self.aspect_group = QButtonGroup(self)
        self.aspect_group.setExclusive(True)

        for aspect in ASPECT_RATIOS:
            button = option_button(
                aspect.key,
                checked=(
                    aspect.key
                    == self.render_settings["aspect_ratio"]
                ),
            )
            button.setFixedWidth(68)
            self.aspect_group.addButton(button)
            self.aspect_buttons[aspect.key] = button
            button.clicked.connect(
                lambda checked=False, key=aspect.key:
                self._select_aspect_ratio(key)
            )
            project_bar_layout.addWidget(button)

        self.aspect_combo.currentIndexChanged.connect(
            self._sync_aspect_buttons
        )
        self.aspect_combo.currentIndexChanged.connect(
            self._settings_changed
        )

        center_layout.addWidget(project_bar)

        # Player card.
        player_card = card(object_name="PlayerCard")
        player_layout = QVBoxLayout(player_card)
        player_layout.setContentsMargins(10, 10, 10, 10)
        player_layout.setSpacing(7)

        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumHeight(350)
        self.video_widget.setStyleSheet(
            "background:#050814; border-radius:10px;"
        )

        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.8)

        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)
        self.player.positionChanged.connect(
            self._on_position_changed
        )
        self.player.durationChanged.connect(
            self._on_duration_changed
        )

        self.play_button = QPushButton("▶")
        self.play_button.setFixedWidth(44)
        self.play_button.clicked.connect(self._toggle_playback)

        self.position_slider = QSlider(
            Qt.Orientation.Horizontal
        )
        self.position_slider.setRange(0, 0)
        self.position_slider.sliderMoved.connect(
            self.player.setPosition
        )

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setProperty("muted", True)

        player_controls = QHBoxLayout()
        player_controls.setSpacing(9)
        player_controls.addWidget(self.play_button)
        player_controls.addWidget(self.position_slider, 1)
        player_controls.addWidget(self.time_label)

        player_layout.addWidget(self.video_widget, 1)
        player_layout.addLayout(player_controls)

        center_layout.addWidget(player_card, 3)

        # Timeline + toolbar.
        timeline_card = card(object_name="TimelineCard")
        timeline_layout = QVBoxLayout(timeline_card)
        timeline_layout.setContentsMargins(12, 10, 12, 10)
        timeline_layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(7)

        self.undo_button = QPushButton("↶  Desfazer")
        self.undo_button.setEnabled(False)
        self.undo_button.clicked.connect(self._undo)

        self.redo_button = QPushButton("↷  Refazer")
        self.redo_button.setEnabled(False)
        self.redo_button.clicked.connect(self._redo)

        self.split_button = QPushButton("✂  Dividir")
        self.split_button.clicked.connect(self._split_at_cursor)

        self.remove_selected_button = QPushButton("⌫  Excluir")
        self.remove_selected_button.setEnabled(False)
        self.remove_selected_button.clicked.connect(
            self._remove_selected_segment
        )

        self.restore_button = QPushButton("↺  Restaurar")
        self.restore_button.setEnabled(False)
        self.restore_button.clicked.connect(
            self._restore_selected_cut
        )

        toolbar.addWidget(self.undo_button)
        toolbar.addWidget(self.redo_button)
        toolbar.addWidget(self.split_button)
        toolbar.addWidget(self.remove_selected_button)
        toolbar.addWidget(self.restore_button)
        toolbar.addStretch(1)

        zoom_minus = QLabel("−")
        zoom_minus.setStyleSheet(
            "font-size:18px; color:#AAB2D8;"
        )
        zoom_title = QLabel("Zoom")
        zoom_title.setProperty("muted", True)

        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(1, 10)
        self.zoom_slider.setValue(1)
        self.zoom_slider.setFixedWidth(120)
        self.zoom_slider.valueChanged.connect(
            self._change_timeline_zoom
        )

        self.zoom_label = QLabel("1x")
        self.zoom_label.setProperty("muted", True)

        toolbar.addWidget(zoom_minus)
        toolbar.addWidget(zoom_title)
        toolbar.addWidget(self.zoom_slider)
        toolbar.addWidget(self.zoom_label)

        timeline_layout.addLayout(toolbar)

        self.summary_label = QLabel()
        self.summary_label.setProperty("muted", True)
        self.summary_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        timeline_layout.addWidget(self.summary_label)

        # Functional timeline.
        self.timeline = TimelineWidget()
        self.timeline.set_plan(self.plan)
        self.timeline.set_content_analysis(
            self.content_analysis
        )
        self.timeline.segmentSelected.connect(
            self._select_segment
        )
        self.timeline.seekRequested.connect(
            self._seek_source_position
        )

        self.timeline_scroll = QScrollArea()
        self.timeline_scroll.setWidget(self.timeline)
        self.timeline_scroll.setWidgetResizable(False)
        self.timeline_scroll.setMinimumHeight(112)
        self.timeline_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        track_grid = QGridLayout()
        track_grid.setHorizontalSpacing(8)
        track_grid.setVerticalSpacing(5)
        track_grid.setColumnStretch(1, 1)

        video_label = QLabel("▦  Vídeo")
        video_label.setStyleSheet(
            "font-weight:700; color:#E9E7FF;"
        )
        track_grid.addWidget(video_label, 0, 0)
        track_grid.addWidget(self.timeline_scroll, 0, 1)

        caption_track = QFrame()
        caption_track.setFixedHeight(28)
        caption_track.setStyleSheet(
            "background:#32206D; border:1px solid #7656D8;"
            "border-radius:7px;"
        )
        caption_track_layout = QHBoxLayout(caption_track)
        caption_track_layout.setContentsMargins(10, 2, 10, 2)
        caption_track_layout.addWidget(
            QLabel("Que lugar incrível!     Vamos explorar...     Incrível!")
        )

        caption_label = QLabel("▣  Legendas")
        caption_label.setStyleSheet(
            "font-weight:700; color:#E9E7FF;"
        )
        track_grid.addWidget(caption_label, 1, 0)
        track_grid.addWidget(caption_track, 1, 1)

        audio_track = QFrame()
        audio_track.setFixedHeight(26)
        audio_track.setStyleSheet(
            "background:#0F3156; border:1px solid #1D6FA7;"
            "border-radius:7px;"
        )
        audio_track_layout = QHBoxLayout(audio_track)
        audio_track_layout.setContentsMargins(10, 0, 10, 0)
        waveform_label = QLabel(
            "▁▂▃▅▇▅▃▂▃▆▇▆▃▂▁  ▂▅▇▆▃▂  ▂▃▆▇▅▃▁"
        )
        waveform_label.setStyleSheet(
            "color:#42B5F5; font-weight:700;"
        )
        audio_track_layout.addWidget(waveform_label)

        audio_label = QLabel("♫  Áudio")
        audio_label.setStyleSheet(
            "font-weight:700; color:#E9E7FF;"
        )
        track_grid.addWidget(audio_label, 2, 0)
        track_grid.addWidget(audio_track, 2, 1)

        music_track = QFrame()
        music_track.setFixedHeight(26)
        music_track.setStyleSheet(
            "background:qlineargradient("
            "x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #7C2DBA, stop:1 #43236A);"
            "border:1px solid #A855F7; border-radius:7px;"
        )
        music_track_layout = QHBoxLayout(music_track)
        music_track_layout.setContentsMargins(10, 0, 10, 0)
        music_track_layout.addWidget(QLabel("♫  Trilha"))

        music_label = QLabel("♪  Música")
        music_label.setStyleSheet(
            "font-weight:700; color:#E9E7FF;"
        )
        track_grid.addWidget(music_label, 3, 0)
        track_grid.addWidget(music_track, 3, 1)

        timeline_layout.addLayout(track_grid)

        self.selection_label = QLabel(
            "Nenhum trecho selecionado."
        )
        self.selection_label.setProperty("muted", True)
        self.selection_label.setWordWrap(True)
        timeline_layout.addWidget(self.selection_label)

        # Compact advanced edit controls preserve all existing behavior.
        fine_controls = QHBoxLayout()
        fine_controls.setSpacing(6)

        self.mark_in_button = QPushButton("A  Entrada")
        self.mark_in_button.clicked.connect(self._set_mark_in)
        self.mark_out_button = QPushButton("B  Saída")
        self.mark_out_button.clicked.connect(self._set_mark_out)

        self.remove_range_button = QPushButton("Remover A→B")
        self.remove_range_button.setEnabled(False)
        self.remove_range_button.clicked.connect(
            self._remove_marked_range
        )

        self.range_label = QLabel("A: —  |  B: —")
        self.range_label.setProperty("muted", True)

        self.cut_start_spin = QDoubleSpinBox()
        self.cut_start_spin.setDecimals(3)
        self.cut_start_spin.setSuffix(" s")
        self.cut_start_spin.setSingleStep(0.050)

        self.cut_end_spin = QDoubleSpinBox()
        self.cut_end_spin.setDecimals(3)
        self.cut_end_spin.setSuffix(" s")
        self.cut_end_spin.setSingleStep(0.050)

        duration_seconds = self.plan["source_duration_ms"] / 1000
        self.cut_start_spin.setRange(0, duration_seconds)
        self.cut_end_spin.setRange(0, duration_seconds)

        self.adjust_cut_button = QPushButton("Aplicar corte")
        self.adjust_cut_button.setEnabled(False)
        self.adjust_cut_button.clicked.connect(
            self._adjust_selected_cut
        )

        fine_controls.addWidget(self.mark_in_button)
        fine_controls.addWidget(self.mark_out_button)
        fine_controls.addWidget(self.remove_range_button)
        fine_controls.addWidget(self.range_label)
        fine_controls.addStretch(1)
        fine_controls.addWidget(QLabel("Início"))
        fine_controls.addWidget(self.cut_start_spin)
        fine_controls.addWidget(QLabel("Fim"))
        fine_controls.addWidget(self.cut_end_spin)
        fine_controls.addWidget(self.adjust_cut_button)

        timeline_layout.addLayout(fine_controls)

        self.reset_button = QPushButton("Voltar à última prévia")
        self.reset_button.setEnabled(False)
        self.reset_button.clicked.connect(
            self._reset_review_changes
        )
        self.reset_button.setMaximumWidth(190)
        timeline_layout.addWidget(
            self.reset_button,
            alignment=Qt.AlignmentFlag.AlignRight,
        )

        center_layout.addWidget(timeline_card, 2)

        # ==============================================================
        # RIGHT CONTROL PANEL
        # ==============================================================
        right_panel = QWidget()
        right_panel.setFixedWidth(325)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(9)

        style_card = card()
        style_layout = QVBoxLayout(style_card)
        style_layout.setContentsMargins(12, 12, 12, 12)
        style_layout.setSpacing(8)
        style_layout.addWidget(section_title("✦  Estilo aplicado"))

        style_grid = QGridLayout()
        style_grid.setSpacing(7)
        current_style = (
            str(self.project_data.get("style", ""))
            .strip()
            .lower()
        )
        for index, name in enumerate(
            ("Clean", "Dinâmico", "Premium", "Highlights")
        ):
            selected = (
                name.lower() == current_style
                or (
                    name == "Dinâmico"
                    and current_style == "dinamico"
                )
            )
            style_button = option_button(
                name,
                checked=selected,
            )
            style_button.setEnabled(False)
            style_grid.addWidget(
                style_button,
                index // 2,
                index % 2,
            )
        style_layout.addLayout(style_grid)
        right_layout.addWidget(style_card)

        self.captions_checkbox = QCheckBox(
            "Legendas automáticas"
        )
        self.captions_checkbox.setChecked(
            self.render_settings["captions_enabled"]
        )

        captions_card = card()
        captions_layout = QVBoxLayout(captions_card)
        captions_layout.setContentsMargins(12, 10, 12, 10)
        captions_layout.addWidget(self.captions_checkbox)
        captions_layout.addWidget(
            muted_label(
                "Gera legendas automaticamente usando "
                "a transcrição do projeto.",
                True,
            )
        )
        right_layout.addWidget(captions_card)

        self.auto_zoom_checkbox = QCheckBox(
            "Zoom automático"
        )
        self.auto_zoom_checkbox.setChecked(
            self.render_settings["auto_zoom"]
        )

        zoom_card = card()
        zoom_card_layout = QVBoxLayout(zoom_card)
        zoom_card_layout.setContentsMargins(12, 10, 12, 10)
        zoom_card_layout.addWidget(self.auto_zoom_checkbox)
        zoom_card_layout.addWidget(
            muted_label(
                "Aplica punch zoom nos momentos sugeridos "
                "pela análise do conteúdo.",
                True,
            )
        )
        right_layout.addWidget(zoom_card)

        caption_style_card = card()
        caption_style_layout = QVBoxLayout(caption_style_card)
        caption_style_layout.setContentsMargins(12, 12, 12, 12)
        caption_style_layout.setSpacing(7)
        caption_style_layout.addWidget(
            section_title("Estilo das legendas")
        )

        self.caption_style_combo = QComboBox()
        self.caption_style_combo.addItems(CAPTION_STYLES)
        caption_index = self.caption_style_combo.findText(
            self.render_settings["caption_style"]
        )
        if caption_index >= 0:
            self.caption_style_combo.setCurrentIndex(caption_index)
        self.caption_style_combo.hide()

        self.caption_style_buttons = {}
        caption_style_group = QButtonGroup(self)
        caption_style_group.setExclusive(True)

        caption_styles_row = QHBoxLayout()
        for name in CAPTION_STYLES:
            button = option_button(
                name,
                checked=(
                    name
                    == self.render_settings["caption_style"]
                ),
            )
            caption_style_group.addButton(button)
            self.caption_style_buttons[name] = button
            button.clicked.connect(
                lambda checked=False, style=name:
                self._select_caption_style(style)
            )
            caption_styles_row.addWidget(button)

        caption_style_layout.addLayout(caption_styles_row)
        right_layout.addWidget(caption_style_card)

        ai_card = card()
        ai_layout = QVBoxLayout(ai_card)
        ai_layout.setContentsMargins(12, 12, 12, 12)
        ai_layout.setSpacing(7)
        ai_layout.addWidget(section_title("✦  Sugestões da IA"))

        self.ai_hesitation_value = QLabel("Aguardando análise")
        self.ai_repetition_value = QLabel("Aguardando análise")
        self.ai_broll_value = QLabel("Aguardando análise")
        self.ai_zoom_value = QLabel("Aguardando análise")

        for title_text, value_label, letter in (
            ("Hesitações", self.ai_hesitation_value, "H"),
            ("Repetições", self.ai_repetition_value, "R"),
            ("B-roll", self.ai_broll_value, "B"),
            ("Zoom", self.ai_zoom_value, "Z"),
        ):
            row = QFrame()
            row.setStyleSheet(
                "background:#171F3D; border:1px solid #2B3762;"
                "border-radius:9px;"
            )
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(9, 7, 9, 7)

            badge = QLabel(letter)
            badge.setFixedSize(28, 28)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet(
                "background:#432B87; color:#FFFFFF;"
                "border-radius:7px; font-weight:800;"
            )
            texts = QVBoxLayout()
            texts.setSpacing(0)
            title_label = QLabel(title_text)
            title_label.setStyleSheet(
                "font-weight:700; color:#FFFFFF;"
            )
            value_label.setProperty("muted", True)
            value_label.setWordWrap(True)
            texts.addWidget(title_label)
            texts.addWidget(value_label)

            row_layout.addWidget(badge)
            row_layout.addLayout(texts, 1)
            ai_layout.addWidget(row)

        self.analyze_content_button = QPushButton(
            "ANALISAR CONTEÚDO / IA V1"
        )
        self.analyze_content_button.setProperty(
            "secondary",
            True,
        )
        self.analyze_content_button.clicked.connect(
            lambda: self._start_worker("content")
        )

        self.content_summary_label = QLabel()
        self.content_summary_label.hide()
        self._refresh_content_summary()

        ai_layout.addWidget(self.analyze_content_button)
        right_layout.addWidget(ai_card)
        right_layout.addStretch(1)

        self.open_video_button = QPushButton(
            "Abrir vídeo no Windows"
        )
        self.open_video_button.clicked.connect(
            self._open_external_video
        )

        self.open_folder_button = QPushButton(
            "Abrir pasta do projeto"
        )
        self.open_folder_button.clicked.connect(
            self._open_project_folder
        )

        open_row = QHBoxLayout()
        open_row.addWidget(self.open_video_button)
        open_row.addWidget(self.open_folder_button)
        right_layout.addLayout(open_row)

        body.addWidget(center, 1)
        body.addWidget(right_panel)
        content_layout.addLayout(body, 1)

        # ==============================================================
        # EXPORT BAR
        # ==============================================================
        export_card = card(object_name="ExportCard")
        export_layout = QHBoxLayout(export_card)
        export_layout.setContentsMargins(14, 12, 14, 12)
        export_layout.setSpacing(8)

        export_text = QVBoxLayout()
        export_text.setSpacing(1)
        export_text.addWidget(section_title("⚙  Qualidade de exportação"))
        export_text.addWidget(
            muted_label(
                "Escolha a resolução final do vídeo."
            )
        )
        export_layout.addLayout(export_text)
        export_layout.addSpacing(10)

        self.export_combo = QComboBox()
        for profile in EXPORT_PROFILES:
            self.export_combo.addItem(
                profile.label,
                profile.key,
            )
        self.export_combo.hide()

        self.quality_buttons = {}
        self.quality_group = QButtonGroup(self)
        self.quality_group.setExclusive(True)

        quality_subtitles = {
            "original": "do arquivo",
            "1080p": "Full HD",
            "720p": "leve",
            "480p": "menor",
            "360p": "baixa",
        }

        for index, profile in enumerate(EXPORT_PROFILES):
            button = quality_button(
                profile.label,
                quality_subtitles.get(profile.key, ""),
                checked=(index == 0),
            )
            self.quality_group.addButton(button)
            self.quality_buttons[profile.key] = button
            button.clicked.connect(
                lambda checked=False, key=profile.key:
                self._select_export_quality(key)
            )
            export_layout.addWidget(button)

        export_layout.addStretch(1)

        self.rerender_button = QPushButton(
            "↻  Salvar e gerar nova prévia"
        )
        self.rerender_button.setProperty("secondary", True)
        self.rerender_button.setEnabled(False)
        self.rerender_button.clicked.connect(
            lambda: self._start_worker("rerender")
        )

        self.export_button = QPushButton(
            "✦  Exportar vídeo final  →"
        )
        self.export_button.setProperty("primary", True)
        self.export_button.clicked.connect(
            lambda: self._start_worker("export")
        )

        export_layout.addWidget(self.rerender_button)
        export_layout.addWidget(self.export_button)

        content_layout.addWidget(export_card)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setMaximumHeight(9)
        content_layout.addWidget(self.progress_bar)

        self.cancel_button = QPushButton(
            "Cancelar processamento"
        )
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(
            self._cancel_worker
        )
        self.cancel_button.setMaximumWidth(190)
        content_layout.addWidget(
            self.cancel_button,
            alignment=Qt.AlignmentFlag.AlignRight,
        )

        root_layout.addWidget(sidebar)
        root_layout.addWidget(content, 1)
        self.setCentralWidget(root)

        self.undo_shortcut = QShortcut(
            QKeySequence.StandardKey.Undo,
            self,
        )
        self.undo_shortcut.activated.connect(self._undo)

        self.redo_shortcut = QShortcut(
            QKeySequence.StandardKey.Redo,
            self,
        )
        self.redo_shortcut.activated.connect(self._redo)

        self.captions_checkbox.toggled.connect(
            self._settings_changed
        )
        self.caption_style_combo.currentIndexChanged.connect(
            self._sync_caption_style_buttons
        )
        self.caption_style_combo.currentIndexChanged.connect(
            self._settings_changed
        )
        self.auto_zoom_checkbox.toggled.connect(
            self._settings_changed
        )

        apply_review_theme(self)

        self._load_current_preview()

        try:
            self.timeline.set_waveform(
                load_or_create_waveform(
                    self.project_dir
                )
            )
        except (OSError, ValueError, wave.Error, EOFError):
            pass

        cached_thumbnails = load_thumbnail_manifest(
            self.project_dir
        )
        if cached_thumbnails:
            self.timeline.set_thumbnails(
                cached_thumbnails
            )

        self._sync_aspect_buttons()
        self._sync_caption_style_buttons()
        self._refresh_summary()
        self._refresh_edit_controls()

    def _select_aspect_ratio(self, key):
        index = self.aspect_combo.findData(key)
        if index >= 0:
            self.aspect_combo.setCurrentIndex(index)

    def _sync_aspect_buttons(self, *args):
        selected = self.aspect_combo.currentData()
        for key, button in self.aspect_buttons.items():
            blocked = button.blockSignals(True)
            button.setChecked(key == selected)
            button.blockSignals(blocked)

    def _select_caption_style(self, style):
        index = self.caption_style_combo.findText(style)
        if index >= 0:
            self.caption_style_combo.setCurrentIndex(index)

    def _sync_caption_style_buttons(self, *args):
        selected = self.caption_style_combo.currentText()
        for key, button in self.caption_style_buttons.items():
            blocked = button.blockSignals(True)
            button.setChecked(key == selected)
            button.blockSignals(blocked)

    def _select_export_quality(self, key):
        index = self.export_combo.findData(key)
        if index >= 0:
            self.export_combo.setCurrentIndex(index)

    def _load_current_preview(self):
        path = (
            self.project_dir / self.output_path
        ).resolve()

        if not path.exists():
            self.status_label.setText(
                "A prévia renderizada não foi encontrada no disco."
            )
            return

        self.player.stop()
        self.player.setSource(
            QUrl.fromLocalFile(str(path))
        )

    def _toggle_playback(self):
        if (
            self.player.playbackState()
            == QMediaPlayer.PlaybackState.PlayingState
        ):
            self.player.pause()
            self.play_button.setText("▶ Reproduzir")
        else:
            self.player.play()
            self.play_button.setText("⏸ Pausar")

    def _on_duration_changed(self, duration):
        self.position_slider.setRange(
            0,
            max(0, int(duration)),
        )
        self._update_time_label(
            self.player.position(),
            duration,
        )

    def _on_position_changed(self, position):
        if not self.position_slider.isSliderDown():
            self.position_slider.setValue(
                int(position)
            )

        source_ms = edited_to_source_ms(
            self.saved_plan,
            position,
        )
        self.timeline.set_playhead_source_ms(
            source_ms
        )
        self._update_time_label(
            position,
            self.player.duration(),
        )

    def _update_time_label(self, position, duration):
        self.time_label.setText(
            f"{self._format_ms(position)} / "
            f"{self._format_ms(duration)}"
        )

    def _seek_source_position(self, source_ms):
        edited_ms = source_to_edited_ms(
            self.saved_plan,
            source_ms,
        )
        self.player.setPosition(edited_ms)

    def _current_source_position(self):
        return edited_to_source_ms(
            self.saved_plan,
            self.player.position(),
        )

    def _change_timeline_zoom(self, value):
        self.timeline.set_zoom(value)
        self.zoom_label.setText(f"{value}x")

    def _select_segment(self, index):
        if not 0 <= index < len(self.plan["segments"]):
            return

        segment = self.plan["segments"][index]
        start = self._format_ms(segment["start_ms"])
        end = self._format_ms(segment["end_ms"])
        duration = self._format_ms(
            segment["end_ms"] - segment["start_ms"]
        )

        if segment["action"] == "remove":
            self.selection_label.setText(
                f"Corte selecionado: {start} → {end} "
                f"({duration}) • motivo: "
                f"{segment.get('reason', '—')}"
            )
            self.cut_start_spin.setValue(
                segment["start_ms"] / 1000
            )
            self.cut_end_spin.setValue(
                segment["end_ms"] / 1000
            )
        else:
            self.selection_label.setText(
                f"Trecho mantido: {start} → {end} "
                f"({duration})."
            )

        self._refresh_edit_controls()

    def _push_history(self):
        self.undo_stack.append(deepcopy(self.plan))
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def _apply_plan(self, plan, message, select_ms=None):
        self.plan = deepcopy(plan)
        self._update_dirty_state()

        self.timeline.set_plan(self.plan)

        if select_ms is not None:
            index = segment_index_at(
                self.plan,
                min(
                    int(select_ms),
                    self.plan["source_duration_ms"] - 1,
                ),
            )
            self.timeline.select_index(index)
            self._select_segment(index)

        self.status_label.setText(message)
        self._refresh_summary()
        self._refresh_edit_controls()

    def _split_at_cursor(self):
        source_ms = self._current_source_position()

        try:
            self._push_history()
            updated = split_at(
                self.plan,
                source_ms,
            )
        except ValueError as error:
            if self.undo_stack:
                self.undo_stack.pop()
            QMessageBox.warning(
                self,
                "Não foi possível dividir",
                str(error),
            )
            return

        self._apply_plan(
            updated,
            "Trecho dividido. Alteração pendente.",
            source_ms,
        )

    def _remove_selected_segment(self):
        index = self.timeline.selected_index()
        if index is None:
            return

        try:
            self._push_history()
            updated = remove_segment(
                self.plan,
                index,
            )
        except ValueError as error:
            if self.undo_stack:
                self.undo_stack.pop()
            QMessageBox.warning(
                self,
                "Não foi possível remover",
                str(error),
            )
            return

        source_ms = updated["segments"][index]["start_ms"]
        self._apply_plan(
            updated,
            "Trecho marcado para remoção.",
            source_ms,
        )

    def _restore_selected_cut(self):
        index = self.timeline.selected_index()
        if index is None:
            return

        try:
            self._push_history()
            updated = restore_cut(
                self.plan,
                index,
            )
        except ValueError as error:
            if self.undo_stack:
                self.undo_stack.pop()
            QMessageBox.warning(
                self,
                "Não foi possível restaurar",
                str(error),
            )
            return

        source_ms = updated["segments"][index]["start_ms"]
        self._apply_plan(
            updated,
            "Corte restaurado.",
            source_ms,
        )

    def _set_mark_in(self):
        self.mark_in_ms = self._current_source_position()
        self._refresh_range_label()

    def _set_mark_out(self):
        self.mark_out_ms = self._current_source_position()
        self._refresh_range_label()

    def _refresh_range_label(self):
        a = (
            self._format_ms(self.mark_in_ms)
            if self.mark_in_ms is not None
            else "—"
        )
        b = (
            self._format_ms(self.mark_out_ms)
            if self.mark_out_ms is not None
            else "—"
        )
        self.range_label.setText(
            f"A: {a}  |  B: {b}"
        )
        self.remove_range_button.setEnabled(
            self.worker is None
            and self.mark_in_ms is not None
            and self.mark_out_ms is not None
            and self.mark_in_ms != self.mark_out_ms
        )

    def _remove_marked_range(self):
        if (
            self.mark_in_ms is None
            or self.mark_out_ms is None
        ):
            return

        try:
            self._push_history()
            updated = remove_range(
                self.plan,
                self.mark_in_ms,
                self.mark_out_ms,
            )
        except ValueError as error:
            if self.undo_stack:
                self.undo_stack.pop()
            QMessageBox.warning(
                self,
                "Não foi possível remover intervalo",
                str(error),
            )
            return

        start = min(
            self.mark_in_ms,
            self.mark_out_ms,
        )
        self._apply_plan(
            updated,
            "Intervalo A → B marcado para remoção.",
            start,
        )

    def _adjust_selected_cut(self):
        index = self.timeline.selected_index()
        if index is None:
            return

        try:
            self._push_history()
            updated = adjust_removed_segment(
                self.plan,
                index,
                new_start_ms=int(
                    round(
                        self.cut_start_spin.value()
                        * 1000
                    )
                ),
                new_end_ms=int(
                    round(
                        self.cut_end_spin.value()
                        * 1000
                    )
                ),
            )
        except ValueError as error:
            if self.undo_stack:
                self.undo_stack.pop()
            QMessageBox.warning(
                self,
                "Não foi possível ajustar o corte",
                str(error),
            )
            return

        source_ms = updated["segments"][index]["start_ms"]
        self._apply_plan(
            updated,
            "Limites do corte ajustados.",
            source_ms,
        )

    def _undo(self):
        if not self.undo_stack or self.worker is not None:
            return

        self.redo_stack.append(deepcopy(self.plan))
        previous = self.undo_stack.pop()
        self._apply_plan(
            previous,
            "Alteração desfeita.",
        )

    def _redo(self):
        if not self.redo_stack or self.worker is not None:
            return

        self.undo_stack.append(deepcopy(self.plan))
        next_plan = self.redo_stack.pop()
        self._apply_plan(
            next_plan,
            "Alteração refeita.",
        )

    def _reset_review_changes(self):
        if (
            self.plan == self.saved_plan
            and self.render_settings
            == self.saved_settings
        ):
            return

        if self.plan != self.saved_plan:
            self._push_history()

        self.plan = deepcopy(self.saved_plan)
        self.render_settings = deepcopy(
            self.saved_settings
        )
        self.timeline.set_plan(self.plan)
        self._apply_settings_to_widgets()
        self._update_dirty_state()
        self.status_label.setText(
            "Alterações voltaram para a última prévia."
        )
        self._refresh_summary()
        self._refresh_edit_controls()

    def _current_render_settings(self):
        return {
            "aspect_ratio": (
                self.aspect_combo.currentData()
            ),
            "captions_enabled": (
                self.captions_checkbox.isChecked()
            ),
            "caption_style": (
                self.caption_style_combo.currentText()
            ),
            "auto_zoom": (
                self.auto_zoom_checkbox.isChecked()
            ),
        }

    def _apply_settings_to_widgets(self):
        controls = (
            self.aspect_combo,
            self.captions_checkbox,
            self.caption_style_combo,
            self.auto_zoom_checkbox,
        )

        for control in controls:
            control.blockSignals(True)

        try:
            aspect_index = (
                self.aspect_combo.findData(
                    self.render_settings[
                        "aspect_ratio"
                    ]
                )
            )
            if aspect_index >= 0:
                self.aspect_combo.setCurrentIndex(
                    aspect_index
                )

            self.captions_checkbox.setChecked(
                self.render_settings[
                    "captions_enabled"
                ]
            )

            caption_index = (
                self.caption_style_combo.findText(
                    self.render_settings[
                        "caption_style"
                    ]
                )
            )
            if caption_index >= 0:
                self.caption_style_combo.setCurrentIndex(
                    caption_index
                )

            self.auto_zoom_checkbox.setChecked(
                self.render_settings[
                    "auto_zoom"
                ]
            )
        finally:
            for control in controls:
                control.blockSignals(False)

    def _settings_changed(self, *args):
        self.render_settings = (
            self._current_render_settings()
        )
        self._update_dirty_state()
        self.status_label.setText(
            "Formato/efeitos alterados. Gere uma nova prévia."
        )
        self._refresh_edit_controls()

    def _update_dirty_state(self):
        self._dirty = (
            self.plan != self.saved_plan
            or self.render_settings
            != self.saved_settings
        )

    def _refresh_content_summary(self):
        analysis = self.content_analysis

        if not analysis:
            self.content_summary_label.setText(
                "Conteúdo ainda não analisado. "
                "A análise V1 gera sugestões de hesitação, "
                "repetição, B-roll e zoom."
            )
            return

        summary = analysis.get(
            "summary",
            {},
        )
        self.content_summary_label.setText(
            "Análise V1 • "
            f"Hesitações: {summary.get('fillers', 0)} • "
            "Palavras repetidas: "
            f"{summary.get('word_repetitions', 0)} • "
            "Frases repetidas: "
            f"{summary.get('possible_repetitions', 0)} • "
            f"B-roll: {summary.get('broll_suggestions', 0)} • "
            f"Zooms: {summary.get('zoom_events', 0)}"
        )

    def _refresh_summary(self):
        stats = self.plan["stats"]

        self.setWindowTitle(
            f"TakeDream — Revisão — "
            f"{self.project_data['name']} • "
            f"{stats['cuts']} cortes"
        )
        self.summary_label.setText(
            f"{stats['cuts']} cortes • "
            f"{self._format_ms(stats['removed_duration_ms'])} "
            f"removidos • "
            f"{self._format_ms(stats['estimated_duration_ms'])} "
            f"estimados"
        )

    def _refresh_edit_controls(self):
        editing_enabled = self.worker is None
        index = self.timeline.selected_index()

        selected_action = None
        if (
            index is not None
            and 0 <= index < len(self.plan["segments"])
        ):
            selected_action = (
                self.plan["segments"][index]["action"]
            )

        self.split_button.setEnabled(editing_enabled)
        self.mark_in_button.setEnabled(editing_enabled)
        self.mark_out_button.setEnabled(editing_enabled)

        self.aspect_combo.setEnabled(editing_enabled)
        self.captions_checkbox.setEnabled(editing_enabled)
        self.caption_style_combo.setEnabled(
            editing_enabled
            and self.captions_checkbox.isChecked()
        )
        self.auto_zoom_checkbox.setEnabled(editing_enabled)
        self.analyze_content_button.setEnabled(editing_enabled)

        self.remove_selected_button.setEnabled(
            editing_enabled
            and selected_action == "keep"
        )
        self.restore_button.setEnabled(
            editing_enabled
            and selected_action == "remove"
        )
        self.adjust_cut_button.setEnabled(
            editing_enabled
            and selected_action == "remove"
        )
        self.cut_start_spin.setEnabled(
            editing_enabled
            and selected_action == "remove"
        )
        self.cut_end_spin.setEnabled(
            editing_enabled
            and selected_action == "remove"
        )

        self.undo_button.setEnabled(
            editing_enabled
            and bool(self.undo_stack)
        )
        self.redo_button.setEnabled(
            editing_enabled
            and bool(self.redo_stack)
        )
        self.reset_button.setEnabled(
            editing_enabled
            and self._dirty
        )
        self.rerender_button.setEnabled(
            editing_enabled
            and self._dirty
        )

        self.remove_range_button.setEnabled(
            editing_enabled
            and self.mark_in_ms is not None
            and self.mark_out_ms is not None
            and self.mark_in_ms != self.mark_out_ms
        )

        self.export_button.setEnabled(
            editing_enabled
            and not self._dirty
        )

    def _start_worker(self, mode):
        if self.worker is not None:
            return

        if mode == "export" and self._dirty:
            QMessageBox.warning(
                self,
                "Alterações pendentes",
                "Gere uma nova prévia antes de exportar.",
            )
            return

        self.player.pause()
        self.play_button.setText("▶ Reproduzir")
        self._set_processing_controls(False)
        self.progress_bar.setRange(0, 0)

        if mode == "rerender":
            if (
                self.auto_zoom_checkbox.isChecked()
                and not self.content_analysis
            ):
                QMessageBox.warning(
                    self,
                    "Análise necessária",
                    "Execute ANALISAR CONTEÚDO / IA V1 "
                    "antes de usar zoom automático.",
                )
                self._set_processing_controls(True)
                self.progress_bar.setRange(0, 100)
                return

            self.status_label.setText(
                "Aplicando timeline, formato e efeitos..."
            )
            self.worker = ReviewWorker(
                self.project_dir,
                "rerender",
                edit_plan=deepcopy(self.plan),
                render_settings=deepcopy(
                    self.render_settings
                ),
                parent=self,
            )

        elif mode == "content":
            self.status_label.setText(
                "Analisando conteúdo e preparando timeline..."
            )
            self.worker = ReviewWorker(
                self.project_dir,
                "content",
                parent=self,
            )

        else:
            export_key = self.export_combo.currentData()
            self.status_label.setText(
                f"Preparando exportação "
                f"{self.export_combo.currentText()}..."
            )
            self.worker = ReviewWorker(
                self.project_dir,
                "export",
                export_key=export_key,
                parent=self,
            )

        self.worker.stage.connect(
            self.status_label.setText
        )
        self.worker.progress.connect(
            self._set_progress
        )
        self.worker.completed.connect(
            self._worker_completed
        )
        self.worker.error.connect(
            self._worker_error
        )
        self.worker.finished.connect(
            self._worker_finished
        )
        self.worker.start()

    def _set_progress(self, value):
        self.progress_bar.setRange(
            0,
            0 if value < 0 else 100,
        )
        if value >= 0:
            self.progress_bar.setValue(value)

    def _worker_completed(self, result):
        if "output_path" in result:
            self.plan = deepcopy(
                result["edit_plan"]
            )
            self.saved_plan = deepcopy(
                result["edit_plan"]
            )
            self.output_path = (
                result["output_path"]
            )

            returned_settings = (
                result.get(
                    "review_settings"
                )
                or self.render_settings
            )
            self.render_settings = deepcopy(
                returned_settings
            )
            self.saved_settings = deepcopy(
                returned_settings
            )
            self._apply_settings_to_widgets()
            self._update_dirty_state()

            self.undo_stack.clear()
            self.redo_stack.clear()

            self.timeline.set_plan(self.plan)
            self.selection_label.setText(
                "Nova prévia gerada com os ajustes."
            )

            encoder = result.get(
                "render_encoder"
            )
            self.status_label.setText(
                "Nova prévia pronta para revisão."
                + (
                    f" Render: {encoder}."
                    if encoder
                    else ""
                )
            )

            QTimer.singleShot(
                0,
                self._load_current_preview,
            )
            self._refresh_summary()

        elif "export_path" in result:
            self.status_label.setText(
                f"Exportação concluída: "
                f"{result['export_path']}"
            )
            QMessageBox.information(
                self,
                "Vídeo exportado",
                f"Vídeo final criado com sucesso.\n\n"
                f"Qualidade: {result['export_label']}\n"
                f"Formato: "
                f"{result.get('export_aspect_ratio', '—')}\n"
                f"Arquivo: {result['export_path']}\n"
                f"Processamento: "
                f"{result.get('render_encoder', '—')}",
            )

        elif "content_analysis" in result:
            self.content_analysis = (
                result["content_analysis"]
            )
            self.timeline.set_content_analysis(
                self.content_analysis
            )
            thumbnails = result.get(
                "thumbnail_paths",
                [],
            )
            if thumbnails:
                self.timeline.set_thumbnails(
                    thumbnails
                )
            self._refresh_content_summary()
            self.status_label.setText(
                "Análise de conteúdo pronta. "
                "Você já pode ativar zoom automático."
            )

        self._set_progress(100)

    def _worker_error(self, message):
        self.status_label.setText(message)
        self._set_progress(0)

        if not self._close_pending and not (
            self.worker
            and self.worker.cancel.is_set()
        ):
            QMessageBox.warning(
                self,
                "Não foi possível concluir",
                message,
            )

    def _worker_finished(self):
        worker = self.worker
        self.worker = None

        if worker is not None:
            worker.deleteLater()

        self.progress_bar.setRange(0, 100)
        self.cancel_button.setEnabled(False)
        self._set_processing_controls(True)

        if self._close_pending:
            self.close()

    def _set_processing_controls(self, enabled):
        self.play_button.setEnabled(enabled)
        self.position_slider.setEnabled(enabled)
        self.open_video_button.setEnabled(enabled)
        self.open_folder_button.setEnabled(enabled)
        self.export_combo.setEnabled(enabled)
        self.zoom_slider.setEnabled(enabled)
        self.aspect_combo.setEnabled(enabled)
        self.captions_checkbox.setEnabled(enabled)
        self.caption_style_combo.setEnabled(
            enabled
            and self.captions_checkbox.isChecked()
        )
        self.auto_zoom_checkbox.setEnabled(enabled)
        self.analyze_content_button.setEnabled(enabled)
        self.cancel_button.setEnabled(not enabled)

        if not enabled:
            self.split_button.setEnabled(False)
            self.remove_selected_button.setEnabled(False)
            self.restore_button.setEnabled(False)
            self.mark_in_button.setEnabled(False)
            self.mark_out_button.setEnabled(False)
            self.remove_range_button.setEnabled(False)
            self.adjust_cut_button.setEnabled(False)
            self.undo_button.setEnabled(False)
            self.redo_button.setEnabled(False)
            self.reset_button.setEnabled(False)
            self.rerender_button.setEnabled(False)
            self.export_button.setEnabled(False)
        else:
            self._refresh_edit_controls()

    def _cancel_worker(self):
        if self.worker is not None:
            self.worker.cancel.set()
            self.cancel_button.setEnabled(False)
            self.status_label.setText(
                "Interrompendo processamento..."
            )

    def _open_external_video(self):
        path = (
            self.project_dir / self.output_path
        ).resolve()
        if path.exists():
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(path))
            )

    def _open_project_folder(self):
        QDesktopServices.openUrl(
            QUrl.fromLocalFile(
                str(self.project_dir.resolve())
            )
        )

    def closeEvent(self, event):
        if self.worker is not None:
            self._close_pending = True
            self._cancel_worker()
            event.ignore()
            return

        if self._dirty:
            answer = QMessageBox.question(
                self,
                "Alterações não aplicadas",
                "Existem alterações na timeline que ainda "
                "não foram renderizadas. Fechar e descartá-las?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if (
                answer
                != QMessageBox.StandardButton.Yes
            ):
                event.ignore()
                return

        self.player.stop()
        event.accept()

    @staticmethod
    def _format_ms(milliseconds):
        if milliseconds is None:
            return "—"

        total_seconds = max(
            0,
            int(milliseconds // 1000),
        )
        hours, remainder = divmod(
            total_seconds,
            3600,
        )
        minutes, seconds = divmod(
            remainder,
            60,
        )

        if hours:
            return (
                f"{hours:02d}:"
                f"{minutes:02d}:"
                f"{seconds:02d}"
            )

        return f"{minutes:02d}:{seconds:02d}"
