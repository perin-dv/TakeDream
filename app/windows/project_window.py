from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from core.project_manager import ProjectManager
from media.ffmpeg_tools import FFmpegTools
from app.processing_worker import ProcessingWorker


class ProjectWindow(QMainWindow):
    def __init__(self, project_dir, parent=None):
        super().__init__(parent)

        self.project_manager = ProjectManager()
        self.ffmpeg_tools = FFmpegTools()
        self.worker = None
        self._close_pending = False

        self.project_dir, self.project_data = self.project_manager.load_project(
            project_dir
        )

        self.setWindowTitle(f"TakeDream — {self.project_data['name']}")
        self.resize(920, 620)

        container = QWidget()
        main_layout = QVBoxLayout(container)

        header = QLabel(self.project_data["name"])
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)

        profile_text = (
            f"{self.project_data.get('profile', '—')}  •  "
            f"{self.project_data.get('style', '—')}"
        )
        profile_label = QLabel(profile_text)
        profile_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        source_name = self.project_data.get("source", {}).get("filename", "—")
        self.source_label = QLabel(source_name)
        self.source_label.setWordWrap(True)

        info_frame = QFrame()
        info_layout = QFormLayout(info_frame)

        self.duration_value = QLabel("Ainda não analisado")
        self.resolution_value = QLabel("—")
        self.fps_value = QLabel("—")
        self.video_codec_value = QLabel("—")
        self.audio_codec_value = QLabel("—")
        self.audio_value = QLabel("—")
        self.ffmpeg_value = QLabel("Verificando...")

        info_layout.addRow("Arquivo:", self.source_label)
        info_layout.addRow("Duração:", self.duration_value)
        info_layout.addRow("Resolução:", self.resolution_value)
        info_layout.addRow("FPS:", self.fps_value)
        info_layout.addRow("Codec de vídeo:", self.video_codec_value)
        info_layout.addRow("Áudio:", self.audio_value)
        info_layout.addRow("Codec de áudio:", self.audio_codec_value)
        info_layout.addRow("FFmpeg / FFprobe:", self.ffmpeg_value)

        self.status_label = QLabel("Pronto para analisar o vídeo.")
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.analyze_button = QPushButton("ANALISAR VÍDEO")
        self.analyze_button.clicked.connect(self.analyze_media)
        self.process_button = QPushButton("PROCESSAR ÁUDIO E TRANSCREVER")
        self.process_button.clicked.connect(lambda: self._start_worker("process"))
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.result_label = QLabel("Transcrição: ainda não processada")
        self.result_label.setWordWrap(True)
        self.cancel_button = QPushButton("Cancelar processamento")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel_processing)

        close_button = QPushButton("Fechar Projeto")
        close_button.clicked.connect(self.close)

        buttons = QHBoxLayout()
        buttons.addWidget(self.analyze_button)
        buttons.addWidget(close_button)

        main_layout.addWidget(header)
        main_layout.addWidget(profile_label)
        main_layout.addSpacing(20)
        main_layout.addWidget(info_frame)
        main_layout.addSpacing(20)
        main_layout.addWidget(self.result_label)
        main_layout.addWidget(self.process_button)
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(self.cancel_button)
        main_layout.addWidget(self.status_label)
        main_layout.addLayout(buttons)

        self.setCentralWidget(container)

        self._update_ffmpeg_status()
        self._load_saved_metadata()
        QTimer.singleShot(0, lambda: self._start_worker("load"))

    def analyze_media(self):
        self._start_worker("analyze")

    def _start_worker(self, mode):
        if self.worker is not None or self._close_pending:
            return
        self.analyze_button.setEnabled(False)
        self.process_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setRange(0, 0)
        self.status_label.setText("Analisando mídia com FFprobe..." if mode == "analyze"
                                  else "Carregando resultados..." if mode == "load"
                                  else "Iniciando processamento...")
        self.worker = ProcessingWorker(self.project_dir, mode, self)
        self.worker.stage.connect(self.status_label.setText)
        self.worker.progress.connect(self._set_progress)
        self.worker.completed.connect(self._processing_completed)
        self.worker.error.connect(self._processing_error)
        self.worker.finished.connect(self._worker_finished)
        self.worker.start()

    def _set_progress(self, value):
        self.progress_bar.setRange(0, 0 if value < 0 else 100)
        if value >= 0:
            self.progress_bar.setValue(value)

    def _processing_completed(self, result):
        if "metadata" in result:
            self._apply_metadata(result["metadata"])
            self.status_label.setText("Análise concluída • media_metadata.json salvo.")
        else:
            transcript = result["transcript"]
            silences = result["silences"]
            lines = ["Áudio: " + ("OK" if result["audio_path"] else "não extraído")]
            if transcript is not None:
                lines.extend(["Transcrição: OK", f"Idioma: {transcript['language']['detected']}",
                              f"Segmentos: {len(transcript['segments'])}"])
            else:
                lines.append("Transcrição: ainda não processada")
            lines.append(f"Silêncios encontrados: {len(silences['silences'])}"
                         if silences is not None else "Silêncios: ainda não analisados")
            if transcript is not None:
                lines.append(transcript["text"][:400])
            self.result_label.setText("\n".join(lines))
            self.result_label.setTextFormat(Qt.TextFormat.PlainText)
            if result["errors"]:
                self.status_label.setText("Resultados inválidos. Faça backup dos arquivos indicados antes de reprocessar.")
                if not self._close_pending:
                    QMessageBox.warning(self, "Resultados inválidos", "\n".join(result["errors"]))
            else:
                self.status_label.setText("Concluído." if transcript is not None and silences is not None
                                          else "Pronto para continuar o processamento.")
        self._set_progress(100)
        try:
            _, self.project_data = self.project_manager.load_project(self.project_dir)
        except ValueError as error:
            self._processing_error(str(error))

    def _processing_error(self, message):
        self.status_label.setText(message)
        self.status_label.setWordWrap(True)
        self._set_progress(0)
        if not self._close_pending and not (self.worker and self.worker.cancel.is_set()):
            QMessageBox.warning(self, "Não foi possível concluir", message)

    def _worker_finished(self):
        worker = self.worker
        self.worker = None
        worker.deleteLater()
        self.analyze_button.setEnabled(True)
        self.process_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.setRange(0, 100)
        if self._close_pending:
            self.close()

    def _cancel_processing(self):
        if self.worker is not None:
            self.worker.cancel.set()
            self.cancel_button.setEnabled(False)
            self.status_label.setText("Interrompendo... Aguardando a operação atual do Whisper terminar, se houver.")

    def closeEvent(self, event):
        if self.worker is not None:
            self._close_pending = True
            self._cancel_processing()
            event.ignore()
        else:
            event.accept()

    def _load_saved_metadata(self):
        metadata = self.project_manager.load_media_metadata(self.project_dir)

        if metadata:
            try:
                self._apply_metadata(metadata)
            except (AttributeError, TypeError, ValueError):
                self.status_label.setText("Metadados inválidos. Analise o vídeo novamente.")
                return
            self.status_label.setText(
                "Metadados carregados. Você pode analisar novamente se quiser."
            )

    def _update_ffmpeg_status(self):
        availability = self.ffmpeg_tools.availability()

        if availability["available"]:
            self.ffmpeg_value.setText("OK")
        else:
            missing = []

            if not availability["ffmpeg"]:
                missing.append("FFmpeg")

            if not availability["ffprobe"]:
                missing.append("FFprobe")

            self.ffmpeg_value.setText("Ausente: " + ", ".join(missing))

    def _apply_metadata(self, metadata):
        container = metadata.get("container", {})
        video = metadata.get("video", {})
        audio = metadata.get("audio", {})

        self.duration_value.setText(
            container.get("duration_display") or "Desconhecida"
        )
        self.resolution_value.setText(
            video.get("resolution") or "Desconhecida"
        )

        fps = video.get("fps")
        self.fps_value.setText(f"{fps:g}" if fps is not None else "—")

        self.video_codec_value.setText(video.get("codec") or "—")

        has_audio = bool(audio.get("present"))
        self.audio_value.setText("Sim" if has_audio else "Não")
        self.audio_codec_value.setText(
            audio.get("codec") if has_audio else "—"
        )

        self._update_ffmpeg_status()
