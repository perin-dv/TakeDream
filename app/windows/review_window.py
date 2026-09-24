from copy import deepcopy

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QComboBox,
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
from core.edit_pipeline import load_edit_state
from core.project_manager import ProjectManager
from editor.review import (
    add_manual_cut,
    adjust_cut,
    edited_to_source_ms,
    restore_cut,
    source_to_edited_ms,
)
from renderer.export_profiles import EXPORT_PROFILES


class ReviewWindow(QMainWindow):
    HISTORY_LIMIT = 50

    def __init__(self, project_dir, parent=None):
        super().__init__(parent)

        self.project_manager = ProjectManager()
        self.project_dir, self.project_data = self.project_manager.load_project(
            project_dir
        )

        state = load_edit_state(self.project_dir)
        if state["edit_errors"]:
            raise ValueError("\n".join(state["edit_errors"]))
        if state["edit_plan"] is None:
            raise ValueError("Nenhum edit_plan.json válido foi encontrado.")
        if not state["output_path"]:
            raise ValueError("Nenhuma prévia renderizada foi encontrada.")

        self.plan = deepcopy(state["edit_plan"])
        self.saved_plan = deepcopy(state["edit_plan"])
        self.output_path = state["output_path"]

        self.worker = None
        self._close_pending = False
        self._dirty = False
        self._mark_in_ms = None
        self._mark_out_ms = None
        self.undo_stack = []
        self.redo_stack = []

        self.setWindowTitle(
            f"TakeDream — Revisão — {self.project_data['name']}"
        )
        self.resize(1220, 900)

        container = QWidget()
        layout = QVBoxLayout(container)

        title = QLabel(
            f"Revisão da edição • "
            f"{self.project_data.get('profile', '—')} / "
            f"{self.project_data.get('style', '—')}"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumHeight(410)

        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.8)

        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)

        self.play_button = QPushButton("▶ Reproduzir")
        self.play_button.clicked.connect(self._toggle_playback)

        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.sliderMoved.connect(self.player.setPosition)

        self.time_label = QLabel("00:00 / 00:00")

        player_controls = QHBoxLayout()
        player_controls.addWidget(self.play_button)
        player_controls.addWidget(self.position_slider, 1)
        player_controls.addWidget(self.time_label)

        self.summary_label = QLabel()
        self.summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        legend = QLabel(
            "Timeline do original: verde = mantido • vermelho = removido • "
            "azul = IN • amarelo = OUT. Clique para selecionar um trecho."
        )
        legend.setWordWrap(True)

        self.timeline = TimelineWidget()
        self.timeline.set_plan(self.plan)
        self.timeline.segmentSelected.connect(self._select_segment)
        self.timeline.seekRequested.connect(self._seek_source_position)

        self.timeline_scroll = QScrollArea()
        self.timeline_scroll.setWidgetResizable(False)
        self.timeline_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.timeline_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.timeline_scroll.setMinimumHeight(132)
        self.timeline_scroll.setWidget(self.timeline)

        zoom_label = QLabel("Zoom da timeline:")
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(1, 8)
        self.zoom_slider.setValue(1)
        self.zoom_slider.setMaximumWidth(260)
        self.zoom_value_label = QLabel("1x")
        self.zoom_slider.valueChanged.connect(self._change_timeline_zoom)

        zoom_controls = QHBoxLayout()
        zoom_controls.addWidget(zoom_label)
        zoom_controls.addWidget(self.zoom_slider)
        zoom_controls.addWidget(self.zoom_value_label)
        zoom_controls.addStretch()

        self.selection_label = QLabel("Nenhum trecho selecionado.")
        self.selection_label.setWordWrap(True)

        self.mark_in_button = QPushButton("MARCAR IN (I)")
        self.mark_in_button.clicked.connect(self._mark_in)

        self.mark_out_button = QPushButton("MARCAR OUT (O)")
        self.mark_out_button.clicked.connect(self._mark_out)

        self.clear_marks_button = QPushButton("LIMPAR IN/OUT")
        self.clear_marks_button.clicked.connect(self._clear_marks)

        self.manual_cut_button = QPushButton("CRIAR CORTE MANUAL")
        self.manual_cut_button.setEnabled(False)
        self.manual_cut_button.clicked.connect(self._create_manual_cut)

        self.marks_label = QLabel("IN: —   OUT: —")
        self.marks_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        mark_controls = QHBoxLayout()
        mark_controls.addWidget(self.mark_in_button)
        mark_controls.addWidget(self.mark_out_button)
        mark_controls.addWidget(self.clear_marks_button)
        mark_controls.addWidget(self.manual_cut_button)

        self.restore_button = QPushButton("RESTAURAR CORTE")
        self.restore_button.setEnabled(False)
        self.restore_button.clicked.connect(self._restore_selected_cut)

        self.start_minus_button = QPushButton("INÍCIO -0,1s")
        self.start_plus_button = QPushButton("INÍCIO +0,1s")
        self.end_minus_button = QPushButton("FIM -0,1s")
        self.end_plus_button = QPushButton("FIM +0,1s")

        self.start_minus_button.clicked.connect(
            lambda: self._adjust_selected_cut(start_delta=-100)
        )
        self.start_plus_button.clicked.connect(
            lambda: self._adjust_selected_cut(start_delta=100)
        )
        self.end_minus_button.clicked.connect(
            lambda: self._adjust_selected_cut(end_delta=-100)
        )
        self.end_plus_button.clicked.connect(
            lambda: self._adjust_selected_cut(end_delta=100)
        )

        adjustment_controls = QHBoxLayout()
        adjustment_controls.addWidget(self.restore_button)
        adjustment_controls.addWidget(self.start_minus_button)
        adjustment_controls.addWidget(self.start_plus_button)
        adjustment_controls.addWidget(self.end_minus_button)
        adjustment_controls.addWidget(self.end_plus_button)

        self.undo_button = QPushButton("DESFAZER (Ctrl+Z)")
        self.undo_button.clicked.connect(self._undo)

        self.redo_button = QPushButton("REFAZER (Ctrl+Y)")
        self.redo_button.clicked.connect(self._redo)

        self.reset_button = QPushButton("DESCARTAR ALTERAÇÕES PENDENTES")
        self.reset_button.clicked.connect(self._reset_review_changes)

        history_controls = QHBoxLayout()
        history_controls.addWidget(self.undo_button)
        history_controls.addWidget(self.redo_button)
        history_controls.addWidget(self.reset_button)

        self.rerender_button = QPushButton("SALVAR E GERAR NOVA PRÉVIA")
        self.rerender_button.clicked.connect(
            lambda: self._start_worker("rerender")
        )

        self.open_video_button = QPushButton(
            "ABRIR VÍDEO NO PLAYER DO WINDOWS"
        )
        self.open_video_button.clicked.connect(self._open_external_video)

        self.open_folder_button = QPushButton("ABRIR PASTA DO PROJETO")
        self.open_folder_button.clicked.connect(self._open_project_folder)

        open_controls = QHBoxLayout()
        open_controls.addWidget(self.open_video_button)
        open_controls.addWidget(self.open_folder_button)

        export_label = QLabel("Exportação final:")

        self.export_combo = QComboBox()
        for profile in EXPORT_PROFILES:
            self.export_combo.addItem(profile.label, profile.key)

        self.export_button = QPushButton("EXPORTAR VÍDEO FINAL")
        self.export_button.clicked.connect(
            lambda: self._start_worker("export")
        )

        export_controls = QHBoxLayout()
        export_controls.addWidget(export_label)
        export_controls.addWidget(self.export_combo)
        export_controls.addWidget(self.export_button)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)

        self.cancel_button = QPushButton("Cancelar processamento")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel_worker)

        self.status_label = QLabel("Prévia carregada. Revise os cortes.")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(self.video_widget, 1)
        layout.addLayout(player_controls)
        layout.addWidget(self.summary_label)
        layout.addWidget(legend)
        layout.addWidget(self.timeline_scroll)
        layout.addLayout(zoom_controls)
        layout.addWidget(self.selection_label)
        layout.addWidget(self.marks_label)
        layout.addLayout(mark_controls)
        layout.addLayout(adjustment_controls)
        layout.addLayout(history_controls)
        layout.addWidget(self.rerender_button)
        layout.addLayout(open_controls)
        layout.addLayout(export_controls)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.cancel_button)
        layout.addWidget(self.status_label)

        self.setCentralWidget(container)

        self._install_shortcuts()
        self._load_current_preview()
        self._refresh_summary()
        self._refresh_interaction_controls()

    def _install_shortcuts(self):
        self.play_shortcut = QShortcut(QKeySequence("Space"), self)
        self.play_shortcut.activated.connect(self._toggle_playback)

        self.mark_in_shortcut = QShortcut(QKeySequence("I"), self)
        self.mark_in_shortcut.activated.connect(self._mark_in)

        self.mark_out_shortcut = QShortcut(QKeySequence("O"), self)
        self.mark_out_shortcut.activated.connect(self._mark_out)

        self.undo_shortcut = QShortcut(
            QKeySequence(QKeySequence.StandardKey.Undo),
            self,
        )
        self.undo_shortcut.activated.connect(self._undo)

        self.redo_shortcut = QShortcut(
            QKeySequence("Ctrl+Y"),
            self,
        )
        self.redo_shortcut.activated.connect(self._redo)

    def _load_current_preview(self):
        path = (self.project_dir / self.output_path).resolve()

        if not path.exists():
            self.status_label.setText(
                "A prévia renderizada não foi encontrada no disco."
            )
            return

        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(str(path)))

    def _toggle_playback(self):
        if not self.play_button.isEnabled():
            return

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
        self.position_slider.setRange(0, max(0, int(duration)))
        self._update_time_label(self.player.position(), duration)

    def _on_position_changed(self, position):
        if not self.position_slider.isSliderDown():
            self.position_slider.setValue(int(position))

        if not self._dirty:
            source_ms = edited_to_source_ms(self.plan, position)
            self.timeline.set_playhead_source_ms(source_ms)

        self._update_time_label(position, self.player.duration())

    def _update_time_label(self, position, duration):
        self.time_label.setText(
            f"{self._format_ms(position)} / {self._format_ms(duration)}"
        )

    def _seek_source_position(self, source_ms):
        if self._dirty or self.worker is not None:
            return

        edited_ms = source_to_edited_ms(self.plan, source_ms)
        self.player.setPosition(edited_ms)

    def _current_source_position(self):
        if self._dirty:
            raise ValueError(
                "Gere uma nova prévia antes de marcar outro corte manual."
            )

        return edited_to_source_ms(
            self.plan,
            self.player.position(),
        )

    def _mark_in(self):
        if not self.mark_in_button.isEnabled():
            return

        try:
            self._mark_in_ms = self._current_source_position()
        except ValueError as error:
            self.status_label.setText(str(error))
            return

        self._update_markers()

    def _mark_out(self):
        if not self.mark_out_button.isEnabled():
            return

        try:
            self._mark_out_ms = self._current_source_position()
        except ValueError as error:
            self.status_label.setText(str(error))
            return

        self._update_markers()

    def _clear_marks(self):
        self._mark_in_ms = None
        self._mark_out_ms = None
        self._update_markers()

    def _update_markers(self):
        self.timeline.set_markers(
            self._mark_in_ms,
            self._mark_out_ms,
        )

        mark_in = (
            "—"
            if self._mark_in_ms is None
            else self._format_ms_precise(self._mark_in_ms)
        )
        mark_out = (
            "—"
            if self._mark_out_ms is None
            else self._format_ms_precise(self._mark_out_ms)
        )
        self.marks_label.setText(
            f"IN: {mark_in}   OUT: {mark_out}"
        )
        self._refresh_interaction_controls()

    def _create_manual_cut(self):
        if self._mark_in_ms is None or self._mark_out_ms is None:
            return

        start = min(self._mark_in_ms, self._mark_out_ms)
        end = max(self._mark_in_ms, self._mark_out_ms)

        self._push_undo()

        try:
            updated = add_manual_cut(self.plan, start, end)
        except ValueError as error:
            self.undo_stack.pop()
            QMessageBox.warning(
                self,
                "Não foi possível criar o corte",
                str(error),
            )
            return

        self._clear_marks()
        self._apply_pending_plan(
            updated,
            f"Corte manual criado: "
            f"{self._format_ms_precise(start)} → "
            f"{self._format_ms_precise(end)}.",
        )

    def _select_segment(self, index):
        if index < 0 or index >= len(self.plan["segments"]):
            return

        segment = self.plan["segments"][index]
        start = self._format_ms_precise(segment["start_ms"])
        end = self._format_ms_precise(segment["end_ms"])
        duration = self._format_ms_precise(
            segment["end_ms"] - segment["start_ms"]
        )

        if segment["action"] == "remove":
            reason = segment.get("reason", "cut")
            self.selection_label.setText(
                f"Corte selecionado: {start} → {end} "
                f"({duration}) • {reason}"
            )
        else:
            self.selection_label.setText(
                f"Trecho mantido: {start} → {end} ({duration})."
            )

        self._refresh_interaction_controls()

    def _restore_selected_cut(self):
        index = self.timeline.selected_index()
        if index is None:
            return

        self._push_undo()

        try:
            updated = restore_cut(self.plan, index)
        except ValueError as error:
            self.undo_stack.pop()
            QMessageBox.warning(
                self,
                "Não foi possível restaurar",
                str(error),
            )
            return

        self._apply_pending_plan(
            updated,
            "Corte restaurado. Gere uma nova prévia para aplicar.",
        )

    def _adjust_selected_cut(self, *, start_delta=0, end_delta=0):
        index = self.timeline.selected_index()
        if index is None:
            return

        self._push_undo()

        try:
            updated = adjust_cut(
                self.plan,
                index,
                start_delta_ms=start_delta,
                end_delta_ms=end_delta,
            )
        except ValueError as error:
            self.undo_stack.pop()
            QMessageBox.warning(
                self,
                "Não foi possível ajustar o corte",
                str(error),
            )
            return

        self._apply_pending_plan(
            updated,
            "Borda do corte ajustada em 0,1 s. "
            "Gere uma nova prévia para aplicar.",
        )

    def _push_undo(self):
        self.undo_stack.append(deepcopy(self.plan))
        if len(self.undo_stack) > self.HISTORY_LIMIT:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def _undo(self):
        if not self.undo_stack or self.worker is not None:
            return

        self.redo_stack.append(deepcopy(self.plan))
        self.plan = self.undo_stack.pop()
        self._after_history_change("Alteração desfeita.")

    def _redo(self):
        if not self.redo_stack or self.worker is not None:
            return

        self.undo_stack.append(deepcopy(self.plan))
        self.plan = self.redo_stack.pop()
        self._after_history_change("Alteração refeita.")

    def _after_history_change(self, message):
        self._dirty = self.plan != self.saved_plan
        self.timeline.set_plan(self.plan)
        self.selection_label.setText(message)
        self._clear_marks()

        if self._dirty:
            self.player.pause()
            self.play_button.setText("▶ Reproduzir")

        self._refresh_summary()
        self._refresh_interaction_controls()

    def _apply_pending_plan(self, plan, message):
        self.plan = deepcopy(plan)
        self._dirty = self.plan != self.saved_plan

        self.player.pause()
        self.play_button.setText("▶ Reproduzir")
        self.timeline.set_plan(self.plan)
        self.selection_label.setText(message)
        self.status_label.setText(
            "Alterações pendentes. Gere uma nova prévia antes de exportar."
        )

        self._refresh_summary()
        self._refresh_interaction_controls()

    def _reset_review_changes(self):
        if not self._dirty:
            return

        self._push_undo()
        self.plan = deepcopy(self.saved_plan)
        self._dirty = False
        self.timeline.set_plan(self.plan)
        self._clear_marks()
        self.selection_label.setText(
            "Alterações pendentes descartadas."
        )
        self.status_label.setText(
            "Prévia carregada. Revise os cortes."
        )
        self._refresh_summary()
        self._refresh_interaction_controls()

    def _change_timeline_zoom(self, value):
        self.zoom_value_label.setText(f"{value}x")
        self.timeline.set_zoom_factor(value)

    def _refresh_summary(self):
        stats = self.plan["stats"]
        self.setWindowTitle(
            f"TakeDream — Revisão — {self.project_data['name']} • "
            f"{stats['cuts']} cortes"
        )
        self.summary_label.setText(
            f"{stats['cuts']} cortes • "
            f"{self._format_ms(stats['removed_duration_ms'])} removidos • "
            f"{self._format_ms(stats['estimated_duration_ms'])} estimados"
        )

    def _refresh_interaction_controls(self):
        busy = self.worker is not None

        if busy:
            for widget in (
                self.play_button,
                self.position_slider,
                self.mark_in_button,
                self.mark_out_button,
                self.clear_marks_button,
                self.manual_cut_button,
                self.restore_button,
                self.start_minus_button,
                self.start_plus_button,
                self.end_minus_button,
                self.end_plus_button,
                self.undo_button,
                self.redo_button,
                self.reset_button,
                self.rerender_button,
                self.open_video_button,
                self.open_folder_button,
                self.export_combo,
                self.export_button,
                self.zoom_slider,
            ):
                widget.setEnabled(False)
            self.cancel_button.setEnabled(True)
            return

        self.cancel_button.setEnabled(False)
        self.zoom_slider.setEnabled(True)
        self.open_folder_button.setEnabled(True)

        self.undo_button.setEnabled(bool(self.undo_stack))
        self.redo_button.setEnabled(bool(self.redo_stack))
        self.reset_button.setEnabled(self._dirty)
        self.rerender_button.setEnabled(self._dirty)

        self.play_button.setEnabled(not self._dirty)
        self.position_slider.setEnabled(not self._dirty)
        self.mark_in_button.setEnabled(not self._dirty)
        self.mark_out_button.setEnabled(not self._dirty)
        self.clear_marks_button.setEnabled(
            not self._dirty
            and (
                self._mark_in_ms is not None
                or self._mark_out_ms is not None
            )
        )

        marks_ready = (
            not self._dirty
            and self._mark_in_ms is not None
            and self._mark_out_ms is not None
            and abs(self._mark_out_ms - self._mark_in_ms) >= 80
        )
        self.manual_cut_button.setEnabled(marks_ready)

        self.open_video_button.setEnabled(not self._dirty)
        self.export_combo.setEnabled(not self._dirty)
        self.export_button.setEnabled(not self._dirty)

        selected = self.timeline.selected_index()
        selected_remove = (
            selected is not None
            and 0 <= selected < len(self.plan["segments"])
            and self.plan["segments"][selected]["action"] == "remove"
        )

        self.restore_button.setEnabled(selected_remove)
        self.start_minus_button.setEnabled(selected_remove)
        self.start_plus_button.setEnabled(selected_remove)
        self.end_minus_button.setEnabled(selected_remove)
        self.end_plus_button.setEnabled(selected_remove)

    def _start_worker(self, mode):
        if self.worker is not None:
            return

        if mode == "export" and self._dirty:
            QMessageBox.warning(
                self,
                "Alterações pendentes",
                "Gere uma nova prévia antes de exportar o vídeo final.",
            )
            return

        self.player.pause()
        self.play_button.setText("▶ Reproduzir")
        self.progress_bar.setRange(0, 0)

        if mode == "rerender":
            self.status_label.setText(
                "Aplicando ajustes da timeline..."
            )
            self.worker = ReviewWorker(
                self.project_dir,
                "rerender",
                edit_plan=deepcopy(self.plan),
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

        self._refresh_interaction_controls()
        self.worker.stage.connect(self.status_label.setText)
        self.worker.progress.connect(self._set_progress)
        self.worker.completed.connect(self._worker_completed)
        self.worker.error.connect(self._worker_error)
        self.worker.finished.connect(self._worker_finished)
        self.worker.start()

    def _set_progress(self, value):
        self.progress_bar.setRange(0, 0 if value < 0 else 100)
        if value >= 0:
            self.progress_bar.setValue(value)

    def _worker_completed(self, result):
        if "output_path" in result:
            self.plan = deepcopy(result["edit_plan"])
            self.saved_plan = deepcopy(result["edit_plan"])
            self.output_path = result["output_path"]
            self._dirty = False
            self.undo_stack.clear()
            self.redo_stack.clear()
            self._mark_in_ms = None
            self._mark_out_ms = None

            self.timeline.set_plan(self.plan)
            self.timeline.set_markers(None, None)
            self.selection_label.setText(
                "Nova prévia gerada com os ajustes."
            )
            self.status_label.setText(
                "Nova prévia pronta para revisão."
            )
            QTimer.singleShot(0, self._load_current_preview)
            self._refresh_summary()

        elif "export_path" in result:
            self.status_label.setText(
                f"Exportação concluída: {result['export_path']}"
            )
            QMessageBox.information(
                self,
                "Vídeo exportado",
                f"Vídeo final criado com sucesso.\n\n"
                f"Qualidade: {result['export_label']}\n"
                f"Arquivo: {result['export_path']}",
            )

        self._set_progress(100)

    def _worker_error(self, message):
        self.status_label.setText(message)
        self._set_progress(0)

        if not self._close_pending and not (
            self.worker and self.worker.cancel.is_set()
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
        self._refresh_interaction_controls()

        if self._close_pending:
            self.close()

    def _cancel_worker(self):
        if self.worker is not None:
            self.worker.cancel.set()
            self.cancel_button.setEnabled(False)
            self.status_label.setText(
                "Interrompendo processamento..."
            )

    def _open_external_video(self):
        path = (self.project_dir / self.output_path).resolve()
        if path.exists():
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(path))
            )

    def _open_project_folder(self):
        QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.project_dir.resolve()))
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
                "Existem alterações na timeline que ainda não foram "
                "renderizadas. Fechar e descartar essas alterações?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

        self.player.stop()
        event.accept()

    @staticmethod
    def _format_ms(milliseconds):
        total_seconds = max(0, int(milliseconds // 1000))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        return f"{minutes:02d}:{seconds:02d}"

    @staticmethod
    def _format_ms_precise(milliseconds):
        total = max(0, int(milliseconds))
        seconds, ms = divmod(total, 1000)
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{ms:03d}"

        return f"{minutes:02d}:{seconds:02d}.{ms:03d}"
