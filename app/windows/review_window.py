from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices
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
    restore_cut,
    source_to_edited_ms,
)
from renderer.export_profiles import EXPORT_PROFILES


class ReviewWindow(QMainWindow):
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

        self.setWindowTitle(
            f"TakeDream — Revisão — {self.project_data['name']}"
        )
        self.resize(1180, 820)

        container = QWidget()
        layout = QVBoxLayout(container)

        title = QLabel(
            f"Revisão da edição • "
            f"{self.project_data.get('profile', '—')} / "
            f"{self.project_data.get('style', '—')}"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumHeight(420)

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

        legend = QLabel(
            "Linha do tempo do original: verde = mantido • vermelho = corte automático. "
            "Clique em um corte vermelho para restaurá-lo."
        )
        legend.setWordWrap(True)

        self.timeline = TimelineWidget()
        self.timeline.set_plan(self.plan)
        self.timeline.segmentSelected.connect(self._select_segment)
        self.timeline.seekRequested.connect(self._seek_source_position)

        self.selection_label = QLabel("Nenhum corte selecionado.")
        self.selection_label.setWordWrap(True)

        self.restore_button = QPushButton("RESTAURAR CORTE SELECIONADO")
        self.restore_button.setEnabled(False)
        self.restore_button.clicked.connect(self._restore_selected_cut)

        self.reset_button = QPushButton("DESFAZER ALTERAÇÕES DA REVISÃO")
        self.reset_button.setEnabled(False)
        self.reset_button.clicked.connect(self._reset_review_changes)

        edit_controls = QHBoxLayout()
        edit_controls.addWidget(self.restore_button)
        edit_controls.addWidget(self.reset_button)

        self.rerender_button = QPushButton("SALVAR E GERAR NOVA PRÉVIA")
        self.rerender_button.setEnabled(False)
        self.rerender_button.clicked.connect(
            lambda: self._start_worker("rerender")
        )

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
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel_worker)

        self.status_label = QLabel("Prévia carregada. Revise os cortes.")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(self.video_widget, 1)
        layout.addLayout(player_controls)
        layout.addWidget(legend)
        layout.addWidget(self.timeline)
        layout.addWidget(self.selection_label)
        layout.addLayout(edit_controls)
        layout.addWidget(self.rerender_button)
        layout.addLayout(open_controls)
        layout.addLayout(export_controls)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.cancel_button)
        layout.addWidget(self.status_label)

        self.setCentralWidget(container)

        self._load_current_preview()
        self._refresh_summary()

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

        source_ms = edited_to_source_ms(self.plan, position)
        self.timeline.set_playhead_source_ms(source_ms)
        self._update_time_label(position, self.player.duration())

    def _update_time_label(self, position, duration):
        self.time_label.setText(
            f"{self._format_ms(position)} / {self._format_ms(duration)}"
        )

    def _seek_source_position(self, source_ms):
        edited_ms = source_to_edited_ms(self.plan, source_ms)
        self.player.setPosition(edited_ms)

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
                f"Corte automático selecionado: {start} → {end} "
                f"({duration}). Você pode restaurar este trecho."
            )
            self.restore_button.setEnabled(self.worker is None)
        else:
            self.selection_label.setText(
                f"Trecho mantido: {start} → {end} ({duration})."
            )
            self.restore_button.setEnabled(False)

    def _restore_selected_cut(self):
        index = self.timeline.selected_index()
        if index is None:
            return

        try:
            self.plan = restore_cut(self.plan, index)
        except ValueError as error:
            QMessageBox.warning(self, "Não foi possível restaurar", str(error))
            return

        self._dirty = True
        self.timeline.set_plan(self.plan)
        self.restore_button.setEnabled(False)
        self.reset_button.setEnabled(True)
        self.rerender_button.setEnabled(True)
        self.export_button.setEnabled(False)
        self.selection_label.setText(
            "Corte restaurado na revisão. Gere uma nova prévia para aplicar."
        )
        self.status_label.setText(
            "Alterações pendentes na linha do tempo."
        )
        self._refresh_summary()

    def _reset_review_changes(self):
        self.plan = deepcopy(self.saved_plan)
        self._dirty = False
        self.timeline.set_plan(self.plan)
        self.restore_button.setEnabled(False)
        self.reset_button.setEnabled(False)
        self.rerender_button.setEnabled(False)
        self.export_button.setEnabled(True)
        self.selection_label.setText("Alterações da revisão desfeitas.")
        self.status_label.setText("Prévia carregada. Revise os cortes.")
        self._refresh_summary()

    def _refresh_summary(self):
        stats = self.plan["stats"]
        self.setWindowTitle(
            f"TakeDream — Revisão — {self.project_data['name']} • "
            f"{stats['cuts']} cortes"
        )

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
        self._set_processing_controls(False)
        self.progress_bar.setRange(0, 0)

        if mode == "rerender":
            self.status_label.setText("Aplicando ajustes da linha do tempo...")
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
            self.timeline.set_plan(self.plan)
            self.reset_button.setEnabled(False)
            self.rerender_button.setEnabled(False)
            self.export_button.setEnabled(True)
            self.selection_label.setText("Nova prévia gerada com os ajustes.")
            self.status_label.setText("Nova prévia pronta para revisão.")
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
        self.cancel_button.setEnabled(not enabled)

        if enabled:
            index = self.timeline.selected_index()
            can_restore = (
                index is not None
                and self.plan["segments"][index]["action"] == "remove"
            )
            self.restore_button.setEnabled(can_restore)
            self.reset_button.setEnabled(self._dirty)
            self.rerender_button.setEnabled(self._dirty)
            self.export_button.setEnabled(not self._dirty)
        else:
            self.restore_button.setEnabled(False)
            self.reset_button.setEnabled(False)
            self.rerender_button.setEnabled(False)
            self.export_button.setEnabled(False)

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
                "Existem cortes restaurados que ainda não foram renderizados. "
                "Fechar e descartar essas alterações?",
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
