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
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
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
        self.resize(1280, 900)

        container = QWidget()
        layout = QVBoxLayout(container)

        title = QLabel(
            f"Revisão da edição • "
            f"{self.project_data.get('profile', '—')} / "
            f"{self.project_data.get('style', '—')}"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumHeight(400)

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

        self.play_button = QPushButton("▶ Reproduzir")
        self.play_button.clicked.connect(self._toggle_playback)

        self.position_slider = QSlider(
            Qt.Orientation.Horizontal
        )
        self.position_slider.setRange(0, 0)
        self.position_slider.sliderMoved.connect(
            self.player.setPosition
        )

        self.time_label = QLabel("00:00 / 00:00")

        player_controls = QHBoxLayout()
        player_controls.addWidget(self.play_button)
        player_controls.addWidget(
            self.position_slider,
            1,
        )
        player_controls.addWidget(self.time_label)

        self.summary_label = QLabel()
        self.summary_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        visual_controls = QHBoxLayout()
        visual_controls.addWidget(QLabel("Formato:"))

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
            self.aspect_combo.setCurrentIndex(
                aspect_index
            )

        self.captions_checkbox = QCheckBox(
            "Legendas"
        )
        self.captions_checkbox.setChecked(
            self.render_settings[
                "captions_enabled"
            ]
        )

        self.caption_style_combo = QComboBox()
        self.caption_style_combo.addItems(
            CAPTION_STYLES
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

        self.auto_zoom_checkbox = QCheckBox(
            "Zoom automático"
        )
        self.auto_zoom_checkbox.setChecked(
            self.render_settings[
                "auto_zoom"
            ]
        )

        visual_controls.addWidget(
            self.aspect_combo
        )
        visual_controls.addWidget(
            self.captions_checkbox
        )
        visual_controls.addWidget(
            self.caption_style_combo
        )
        visual_controls.addWidget(
            self.auto_zoom_checkbox
        )

        self.aspect_combo.currentIndexChanged.connect(
            self._settings_changed
        )
        self.captions_checkbox.toggled.connect(
            self._settings_changed
        )
        self.caption_style_combo.currentIndexChanged.connect(
            self._settings_changed
        )
        self.auto_zoom_checkbox.toggled.connect(
            self._settings_changed
        )

        self.analyze_content_button = QPushButton(
            "ANALISAR CONTEÚDO / IA V1"
        )
        self.analyze_content_button.clicked.connect(
            lambda: self._start_worker("content")
        )

        self.content_summary_label = QLabel()
        self.content_summary_label.setWordWrap(True)
        self._refresh_content_summary()

        legend = QLabel(
            "Timeline do original: verde = mantido • "
            "vermelho = removido • borda amarela = ajuste manual. "
            "Clique para selecionar e posicionar."
        )
        legend.setWordWrap(True)

        zoom_controls = QHBoxLayout()
        zoom_controls.addWidget(QLabel("Zoom da timeline:"))

        self.zoom_slider = QSlider(
            Qt.Orientation.Horizontal
        )
        self.zoom_slider.setRange(1, 10)
        self.zoom_slider.setValue(1)
        self.zoom_slider.valueChanged.connect(
            self._change_timeline_zoom
        )

        self.zoom_label = QLabel("1x")

        zoom_controls.addWidget(self.zoom_slider, 1)
        zoom_controls.addWidget(self.zoom_label)

        self.timeline = TimelineWidget()
        self.timeline.set_plan(self.plan)
        self.timeline.segmentSelected.connect(
            self._select_segment
        )
        self.timeline.seekRequested.connect(
            self._seek_source_position
        )

        self.timeline_scroll = QScrollArea()
        self.timeline_scroll.setWidget(self.timeline)
        self.timeline_scroll.setWidgetResizable(False)
        self.timeline_scroll.setMinimumHeight(130)
        self.timeline_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.selection_label = QLabel(
            "Nenhum trecho selecionado."
        )
        self.selection_label.setWordWrap(True)

        self.split_button = QPushButton(
            "DIVIDIR NO CURSOR"
        )
        self.split_button.clicked.connect(
            self._split_at_cursor
        )

        self.remove_selected_button = QPushButton(
            "REMOVER TRECHO SELECIONADO"
        )
        self.remove_selected_button.setEnabled(False)
        self.remove_selected_button.clicked.connect(
            self._remove_selected_segment
        )

        self.restore_button = QPushButton(
            "RESTAURAR CORTE SELECIONADO"
        )
        self.restore_button.setEnabled(False)
        self.restore_button.clicked.connect(
            self._restore_selected_cut
        )

        selected_controls = QHBoxLayout()
        selected_controls.addWidget(self.split_button)
        selected_controls.addWidget(
            self.remove_selected_button
        )
        selected_controls.addWidget(self.restore_button)

        self.mark_in_button = QPushButton(
            "MARCAR ENTRADA (A)"
        )
        self.mark_in_button.clicked.connect(
            self._set_mark_in
        )

        self.mark_out_button = QPushButton(
            "MARCAR SAÍDA (B)"
        )
        self.mark_out_button.clicked.connect(
            self._set_mark_out
        )

        self.remove_range_button = QPushButton(
            "REMOVER INTERVALO A → B"
        )
        self.remove_range_button.setEnabled(False)
        self.remove_range_button.clicked.connect(
            self._remove_marked_range
        )

        self.range_label = QLabel(
            "A: —  |  B: —"
        )

        range_controls = QHBoxLayout()
        range_controls.addWidget(self.mark_in_button)
        range_controls.addWidget(self.mark_out_button)
        range_controls.addWidget(
            self.remove_range_button
        )
        range_controls.addWidget(self.range_label)

        self.cut_start_spin = QDoubleSpinBox()
        self.cut_start_spin.setDecimals(3)
        self.cut_start_spin.setSuffix(" s")
        self.cut_start_spin.setSingleStep(0.050)

        self.cut_end_spin = QDoubleSpinBox()
        self.cut_end_spin.setDecimals(3)
        self.cut_end_spin.setSuffix(" s")
        self.cut_end_spin.setSingleStep(0.050)

        duration_seconds = (
            self.plan["source_duration_ms"] / 1000
        )
        self.cut_start_spin.setRange(
            0,
            duration_seconds,
        )
        self.cut_end_spin.setRange(
            0,
            duration_seconds,
        )

        self.adjust_cut_button = QPushButton(
            "APLICAR INÍCIO / FIM DO CORTE"
        )
        self.adjust_cut_button.setEnabled(False)
        self.adjust_cut_button.clicked.connect(
            self._adjust_selected_cut
        )

        adjust_controls = QHBoxLayout()
        adjust_controls.addWidget(QLabel("Início:"))
        adjust_controls.addWidget(self.cut_start_spin)
        adjust_controls.addWidget(QLabel("Fim:"))
        adjust_controls.addWidget(self.cut_end_spin)
        adjust_controls.addWidget(
            self.adjust_cut_button
        )

        self.undo_button = QPushButton(
            "↶ DESFAZER"
        )
        self.undo_button.setEnabled(False)
        self.undo_button.clicked.connect(self._undo)

        self.redo_button = QPushButton(
            "↷ REFAZER"
        )
        self.redo_button.setEnabled(False)
        self.redo_button.clicked.connect(self._redo)

        self.reset_button = QPushButton(
            "VOLTAR À ÚLTIMA PRÉVIA"
        )
        self.reset_button.setEnabled(False)
        self.reset_button.clicked.connect(
            self._reset_review_changes
        )

        history_controls = QHBoxLayout()
        history_controls.addWidget(self.undo_button)
        history_controls.addWidget(self.redo_button)
        history_controls.addWidget(self.reset_button)

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

        self.rerender_button = QPushButton(
            "SALVAR ALTERAÇÕES E GERAR NOVA PRÉVIA"
        )
        self.rerender_button.setEnabled(False)
        self.rerender_button.clicked.connect(
            lambda: self._start_worker("rerender")
        )

        self.open_video_button = QPushButton(
            "ABRIR VÍDEO NO PLAYER DO WINDOWS"
        )
        self.open_video_button.clicked.connect(
            self._open_external_video
        )

        self.open_folder_button = QPushButton(
            "ABRIR PASTA DO PROJETO"
        )
        self.open_folder_button.clicked.connect(
            self._open_project_folder
        )

        open_controls = QHBoxLayout()
        open_controls.addWidget(self.open_video_button)
        open_controls.addWidget(self.open_folder_button)

        export_label = QLabel("Exportação final:")

        self.export_combo = QComboBox()
        for profile in EXPORT_PROFILES:
            self.export_combo.addItem(
                profile.label,
                profile.key,
            )

        self.export_button = QPushButton(
            "EXPORTAR VÍDEO FINAL"
        )
        self.export_button.clicked.connect(
            lambda: self._start_worker("export")
        )

        export_controls = QHBoxLayout()
        export_controls.addWidget(export_label)
        export_controls.addWidget(self.export_combo)
        export_controls.addWidget(self.export_button)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)

        self.cancel_button = QPushButton(
            "Cancelar processamento"
        )
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(
            self._cancel_worker
        )

        self.status_label = QLabel(
            "Prévia carregada. Revise os cortes."
        )
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.status_label.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(self.video_widget, 1)
        layout.addLayout(player_controls)
        layout.addWidget(self.summary_label)
        layout.addLayout(visual_controls)
        layout.addWidget(self.analyze_content_button)
        layout.addWidget(self.content_summary_label)
        layout.addWidget(legend)
        layout.addLayout(zoom_controls)
        layout.addWidget(self.timeline_scroll)
        layout.addWidget(self.selection_label)
        layout.addLayout(selected_controls)
        layout.addLayout(range_controls)
        layout.addLayout(adjust_controls)
        layout.addLayout(history_controls)
        layout.addWidget(self.rerender_button)
        layout.addLayout(open_controls)
        layout.addLayout(export_controls)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.cancel_button)
        layout.addWidget(self.status_label)

        self.setCentralWidget(container)

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

        self._refresh_summary()
        self._refresh_edit_controls()

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
            "Repetições prováveis: "
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
