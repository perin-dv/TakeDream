from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.project_manager import ProjectManager
from media.ffmpeg_tools import (
    FFmpegNotFoundError,
    FFmpegTools,
    MediaProbeError,
)


class ProjectWindow(QMainWindow):
    def __init__(self, project_dir, parent=None):
        super().__init__(parent)

        self.project_manager = ProjectManager()
        self.ffmpeg_tools = FFmpegTools()

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
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        analyze_button = QPushButton("ANALISAR VÍDEO")
        analyze_button.clicked.connect(self.analyze_media)

        close_button = QPushButton("Fechar Projeto")
        close_button.clicked.connect(self.close)

        buttons = QHBoxLayout()
        buttons.addWidget(analyze_button)
        buttons.addWidget(close_button)

        main_layout.addWidget(header)
        main_layout.addWidget(profile_label)
        main_layout.addSpacing(20)
        main_layout.addWidget(info_frame)
        main_layout.addSpacing(20)
        main_layout.addWidget(self.status_label)
        main_layout.addLayout(buttons)

        self.setCentralWidget(container)

        self._update_ffmpeg_status()
        self._load_saved_metadata()

    def analyze_media(self):
        source_path = self.project_data.get("source", {}).get("original_path")

        if not source_path:
            QMessageBox.warning(
                self,
                "Vídeo não encontrado",
                "Este projeto não possui caminho para o vídeo de origem.",
            )
            return

        if not Path(source_path).exists():
            QMessageBox.warning(
                self,
                "Vídeo não encontrado",
                "O vídeo original não está mais no caminho salvo no projeto.",
            )
            return

        self.status_label.setText("Analisando mídia com FFprobe...")

        try:
            metadata = self.ffmpeg_tools.probe(source_path)
            metadata_file = self.project_manager.save_media_metadata(
                self.project_dir,
                metadata,
            )
        except FFmpegNotFoundError as error:
            self.status_label.setText("FFmpeg/FFprobe não encontrado.")
            QMessageBox.warning(self, "FFmpeg necessário", str(error))
            self._update_ffmpeg_status()
            return
        except MediaProbeError as error:
            self.status_label.setText("Falha na análise do vídeo.")
            QMessageBox.critical(self, "Erro ao analisar vídeo", str(error))
            return
        except OSError as error:
            self.status_label.setText("Falha ao salvar a análise.")
            QMessageBox.critical(
                self,
                "Erro ao salvar análise",
                str(error),
            )
            return

        self._apply_metadata(metadata)
        self.status_label.setText(
            f"Análise concluída • {metadata_file.name} salvo."
        )

    def _load_saved_metadata(self):
        metadata = self.project_manager.load_media_metadata(self.project_dir)

        if metadata:
            self._apply_metadata(metadata)
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
