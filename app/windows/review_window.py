from copy import deepcopy

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import (
    QDesktopServices,
    QKeySequence,
    QShortcut,
)
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
    edited_to_source_ms,
    remove_range,
    remove_segment,
    restore_cut,
    source_to_edited_ms,
    split_segment_at,
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
        self._undo_stack = []
        self._redo_stack = []
        self._mark_in_ms = None
        self._mark_out_ms = None
        self._shortcuts = []

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
        self.video_widget.setMinimumHeight(400)

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
            "linha branca = playhead. Clique para selecionar/posicionar."
        )
        legend.setWordWrap(True)

        timeline_toolbar = QHBoxLayout()

        timeline_toolbar.addWidget(QLabel("Zoom:"))
        self.zoom_combo = QComboBox()
        for label, factor in (
            ("1x", 1.0),
            ("2x", 2.0),
            ("4x", 4.0),
            ("8x", 8.0),
        ):
            self.zoom_combo.addItem(label, factor)
        self.zoom_combo.currentIndexChanged.connect(self._change_timeline_zoom)
        timeline_toolbar.addWidget(self.zoom_combo)

        self.split_button = QPushButton("DIVIDIR NO PLAYHEAD")
        self.split_button.clicked.connect(self._split_at_playhead)
        timeline_toolbar.addWidget(self.split_button)

        self.undo_button = QPushButton("DESFAZER")
        self.undo_button.clicked.connect(self._undo)
        timeline_toolbar.addWidget(self.undo_button)

        self.redo_button = QPushButton("REFAZER")
        self.redo_button.clicked.connect(self._redo)
        timeline_toolbar.addWidget(self.redo_button)

        self.timeline = TimelineWidget()
        self.timeline.set_plan(self.plan)
        self.timeline.segmentSelected.connect(self._select_segment)
        self.timeline.seekRequested.connect(self._seek_source_position)

        self.timeline_scroll = QScrollArea()
        self.timeline_scroll.setWidget(self.timeline)
        self.timeline_scroll.setWidgetResizable(False)
        self.timeline_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.timeline_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.timeline_scroll.setMinimumHeight(125)
        self.timeline_scroll.setMaximumHeight(145)

        self.selection_label = QLabel("Nenhum trecho selecionado.")
        self.selection_label.setWordWrap(True)

        self.restore_button = QPushButton("RESTAURAR CORTE SELECIONADO")
        self.restore_button.clicked.connect(self._restore_selected_cut)

        self.remove_segment_button = QPushButton("REMOVER TRECHO SELECIONADO")
        self.remove_segment_button.clicked.connect(self._remove_selected_segment)

        selection_controls = QHBoxLayout()
        selection_controls.addWidget(self.restore_button)
        selection_controls.addWidget(self.remove_segment_button)

        self.mark_in_button = QPushButton("MARCAR IN")
        self.mark_in_button.clicked.connect(self._mark_in)

        self.mark_out_button = QPushButton("MARCAR OUT")
        self.mark_out_button.clicked.connect(self._mark_out)

        self.remove_range_button = QPushButton("REMOVER IN → OUT")
        self.remove_range_button.clicked.connect(self._remove_marked_range)

        self.clear_marks_button = QPushButton("LIMPAR IN/OUT")
        self.clear_marks_button.clicked.connect(self._clear_marks)

        range_controls = QHBoxLayout()
        range_controls.addWidget(self.mark_in_button)
        range_controls.addWidget(self.mark_out_button)
        range_controls.addWidget(self.remove_range_button)
        range_controls.addWidget(self.clear_marks_button)

        self.mark_label = QLabel("IN: —   OUT: —")
        self.mark_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.reset_button = QPushButton("REVERTER PARA ÚLTIMA PRÉVIA")
        self.reset_button.clicked.connect(self._reset_review_changes)

        self.rerender_button = QPushButton("SALVAR E GERAR NOVA PRÉVIA")
        self.rerender_button.clicked.connect(
            lambda: self._start_worker("rerender")
        )

        revision_controls = QHBoxLayout()
        revision_controls.addWidget(self.reset_button)
        revision_controls.addWidget(self.rerender_button)

        self.open_video_button = QPushButton("ABRIR VÍDEO NO PLAYER DO WINDOWS")
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
        self.cancel_button.clicked.connect(self._cancel_worker)

        self.status_label = QLabel("Prévia carregada. Revise os cortes.")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(self.video_widget, 1)
        layout.addLayout(player_controls)
        layout.addWidget(self.summary_label)
        layout.addWidget(legend)
        layout.addLayout(timeline_toolbar)
        layout.addWidget(self.timeline_scroll)
        layout.addWidget(self.selection_label)
        layout.addLayout(selection_controls)
        layout.addLayout(range_controls)
        layout.addWidget(self.mark_label)
        layout.addLayout(revision_controls)
        layout.addLayout(open_controls)
        layout.addLayout(export_controls)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.cancel_button)
        layout.addWidget(self.status_label)

        self.setCentralWidget(container)

        self._install_shortcuts()
        self._load_current_preview()
        self._refresh_summary()
        self._refresh_controls()

    def _install_shortcuts(self):
        shortcuts = (
            ("Ctrl+Z", self._undo),
            ("Ctrl+Y", self._redo),
            ("Ctrl+K", self._split_at_playhead),
            ("Delete", self._remove_selected_segment),
            ("Space", self._toggle_playback),
        )

        for sequence, callback in shortcuts:
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)

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
        if self.worker is not None or self._dirty:
            return

        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
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
            source_ms = edited_to_source_ms(self.saved_plan, position)
            self.timeline.set_playhead_source_ms(source_ms)

        self._update_time_label(position, self.player.duration())

    def _update_time_label(self, position, duration):
        self.time_label.setText(
            f"{self._format_ms(position)} / {self._format_ms(duration)}"
        )

    def _seek_source_position(self, source_ms):
        if self._dirty:
            return

        edited_ms = source_to_edited_ms(self.saved_plan, source_ms)
        self.player.setPosition(edited_ms)

    def _change_timeline_zoom(self):
        factor = self.zoom_combo.currentData()
        self.timeline.set_zoom_factor(factor)

    def _select_segment(self, index):
        if index < 0 or index >= len(self.plan["segments"]):
            return

        segment = self.plan["segments"][index]
        start = self._format_ms(segment["start_ms"])
        end = self._format_ms(segment["end_ms"])
        duration = self._format_ms(
            segment["end_ms"] - segment["start_ms"]
        )

        if segment["action"] == "remove":
            self.selection_label.setText(
                f"Trecho removido: {start} → {end} ({duration})."
            )
        else:
            self.selection_label.setText(
                f"Trecho mantido: {start} → {end} ({duration})."
            )

        self._refresh_controls()

    def _current_source_ms(self):
        return self.timeline.playhead_source_ms()

    def _split_at_playhead(self):
        if self.worker is not None:
            return

        try:
            new_plan, selected_index = split_segment_at(
                self.plan,
                self._current_source_ms(),
            )
        except ValueError as error:
            QMessageBox.warning(self, "Não foi possível dividir", str(error))
            return

        self._apply_plan_change(
            new_plan,
            "Trecho dividido no playhead.",
            selected_index=selected_index,
        )

    def _remove_selected_segment(self):
        if self.worker is not None:
            return

        index = self.timeline.selected_index()
        if index is None:
            return

        segment = self.plan["segments"][index]
        if segment["action"] != "keep":
            return

        duration = segment["end_ms"] - segment["start_ms"]
        if duration > 5000:
            answer = QMessageBox.question(
                self,
                "Remover trecho longo?",
                f"O trecho selecionado tem {self._format_ms(duration)}. "
                "Deseja removê-lo da edição?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        try:
            new_plan = remove_segment(self.plan, index)
        except ValueError as error:
            QMessageBox.warning(self, "Não foi possível remover", str(error))
            return

        self._apply_plan_change(
            new_plan,
            "Trecho removido manualmente.",
        )

    def _restore_selected_cut(self):
        if self.worker is not None:
            return

        index = self.timeline.selected_index()
        if index is None:
            return

        try:
            new_plan = restore_cut(self.plan, index)
        except ValueError as error:
            QMessageBox.warning(self, "Não foi possível restaurar", str(error))
            return

        self._apply_plan_change(
            new_plan,
            "Corte restaurado manualmente.",
        )

    def _mark_in(self):
        self._mark_in_ms = self._current_source_ms()
        self._refresh_mark_label()
        self.status_label.setText("Ponto IN marcado.")
        self._refresh_controls()

    def _mark_out(self):
        self._mark_out_ms = self._current_source_ms()
        self._refresh_mark_label()
        self.status_label.setText("Ponto OUT marcado.")
        self._refresh_controls()

    def _clear_marks(self):
        self._mark_in_ms = None
        self._mark_out_ms = None
        self._refresh_mark_label()
        self.status_label.setText("Pontos IN/OUT limpos.")
        self._refresh_controls()

    def _remove_marked_range(self):
        if self._mark_in_ms is None or self._mark_out_ms is None:
            return

        try:
            new_plan = remove_range(
                self.plan,
                self._mark_in_ms,
                self._mark_out_ms,
            )
        except ValueError as error:
            QMessageBox.warning(
                self,
                "Não foi possível remover o intervalo",
                str(error),
            )
            return

        self._apply_plan_change(
            new_plan,
            f"Intervalo {self._format_ms(self._mark_in_ms)} → "
            f"{self._format_ms(self._mark_out_ms)} removido.",
        )
        self._mark_in_ms = None
        self._mark_out_ms = None
        self._refresh_mark_label()
        self._refresh_controls()

    def _apply_plan_change(self, new_plan, message, selected_index=None):
        self._undo_stack.append(deepcopy(self.plan))
        if len(self._undo_stack) > self.HISTORY_LIMIT:
            self._undo_stack.pop(0)

        self._redo_stack.clear()
        self.plan = deepcopy(new_plan)
        self._dirty = self.plan != self.saved_plan

        self.player.pause()
        self.play_button.setText("▶ Reproduzir")
        self.timeline.set_plan(self.plan)

        if selected_index is not None:
            self.timeline.select_segment(selected_index)
            self._select_segment(selected_index)
        else:
            self.selection_label.setText("Nenhum trecho selecionado.")

        self.status_label.setText(
            message + " Gere uma nova prévia para visualizar."
        )
        self._refresh_summary()
        self._refresh_controls()

    def _undo(self):
        if self.worker is not None or not self._undo_stack:
            return

        self._redo_stack.append(deepcopy(self.plan))
        self.plan = self._undo_stack.pop()
        self._dirty = self.plan != self.saved_plan

        self.timeline.set_plan(self.plan)
        self.selection_label.setText("Alteração desfeita.")
        self.status_label.setText(
            "Alteração desfeita."
            if not self._dirty
            else "Alteração desfeita. Ainda há mudanças pendentes."
        )
        self._refresh_summary()
        self._refresh_controls()

    def _redo(self):
        if self.worker is not None or not self._redo_stack:
            return

        self._undo_stack.append(deepcopy(self.plan))
        self.plan = self._redo_stack.pop()
        self._dirty = self.plan != self.saved_plan

        self.timeline.set_plan(self.plan)
        self.selection_label.setText("Alteração refeita.")
        self.status_label.setText(
            "Alteração refeita. Gere uma nova prévia para visualizar."
        )
        self._refresh_summary()
        self._refresh_controls()

    def _reset_review_changes(self):
        self.plan = deepcopy(self.saved_plan)
        self._dirty = False
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._mark_in_ms = None
        self._mark_out_ms = None

        self.timeline.set_plan(self.plan)
        self.selection_label.setText("Alterações descartadas.")
        self.status_label.setText("Prévia carregada. Revise os cortes.")
        self._refresh_mark_label()
        self._refresh_summary()
        self._refresh_controls()

    def _refresh_mark_label(self):
        in_text = (
            self._format_ms(self._mark_in_ms)
            if self._mark_in_ms is not None
            else "—"
        )
        out_text = (
            self._format_ms(self._mark_out_ms)
            if self._mark_out_ms is not None
            else "—"
        )
        self.mark_label.setText(f"IN: {in_text}   OUT: {out_text}")

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

    def _refresh_controls(self):
        busy = self.worker is not None
        index = self.timeline.selected_index()

        selected = None
        if index is not None and 0 <= index < len(self.plan["segments"]):
            selected = self.plan["segments"][index]

        self.play_button.setEnabled(not busy and not self._dirty)
        self.position_slider.setEnabled(not busy and not self._dirty)

        self.zoom_combo.setEnabled(not busy)
        self.split_button.setEnabled(not busy)
        self.mark_in_button.setEnabled(not busy)
        self.mark_out_button.setEnabled(not busy)
        self.clear_marks_button.setEnabled(
            not busy
            and (
                self._mark_in_ms is not None
                or self._mark_out_ms is not None
            )
        )
        self.remove_range_button.setEnabled(
            not busy
            and self._mark_in_ms is not None
            and self._mark_out_ms is not None
        )

        self.restore_button.setEnabled(
            not busy
            and selected is not None
            and selected["action"] == "remove"
        )
        self.remove_segment_button.setEnabled(
            not busy
            and selected is not None
            and selected["action"] == "keep"
        )

        self.undo_button.setEnabled(not busy and bool(self._undo_stack))
        self.redo_button.setEnabled(not busy and bool(self._redo_stack))
        self.reset_button.setEnabled(not busy and self._dirty)
        self.rerender_button.setEnabled(not busy and self._dirty)

        self.open_video_button.setEnabled(not busy)
        self.open_folder_button.setEnabled(not busy)
        self.export_combo.setEnabled(not busy)
        self.export_button.setEnabled(not busy and not self._dirty)
        self.cancel_button.setEnabled(busy)

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
                "Aplicando alterações manuais na nova prévia..."
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
                f"Preparando exportação {self.export_combo.currentText()}..."
            )
            self.worker = ReviewWorker(
                self.project_dir,
                "export",
                export_key=export_key,
                parent=self,
            )

        self.worker.stage.connect(self.status_label.setText)
        self.worker.progress.connect(self._set_progress)
        self.worker.completed.connect(self._worker_completed)
        self.worker.error.connect(self._worker_error)
        self.worker.finished.connect(self._worker_finished)
        self.worker.start()

        self._refresh_controls()

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
            self._undo_stack.clear()
            self._redo_stack.clear()
            self._mark_in_ms = None
            self._mark_out_ms = None

            self.timeline.set_plan(self.plan)
            self.selection_label.setText("Nova prévia gerada com os ajustes.")
            self.status_label.setText("Nova prévia pronta para revisão.")
            self._refresh_mark_label()
            self._refresh_summary()
            QTimer.singleShot(0, self._load_current_preview)

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
        self._refresh_controls()

        if self._close_pending:
            self.close()

    def _cancel_worker(self):
        if self.worker is not None:
            self.worker.cancel.set()
            self.cancel_button.setEnabled(False)
            self.status_label.setText("Interrompendo processamento...")

    def _open_external_video(self):
        path = (self.project_dir / self.output_path).resolve()
        if path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

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
                "Existem alterações manuais ainda não renderizadas. "
                "Fechar e descartá-las?",
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
        if milliseconds is None:
            return "—"

        total_seconds = max(0, int(milliseconds // 1000))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        return f"{minutes:02d}:{seconds:02d}"
