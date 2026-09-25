from pathlib import Path

from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from app.processing_worker import ProcessingWorker
from app.ui.components import (
    card,
    muted_label,
    section_title,
)
from app.ui.shell import TakeDreamSidebar
from app.ui.theme import apply_app_theme
from app.ui.windows import enable_dark_title_bar
from app.windows.review_window import ReviewWindow
from core.project_manager import ProjectManager
from media.ffmpeg_tools import FFmpegTools


class ProjectWindow(QMainWindow):
    def __init__(
        self,
        project_dir,
        parent=None,
        *,
        embedded=False,
        host=None,
    ):
        super().__init__(parent)

        self.embedded = embedded
        self.host = host

        if embedded:
            self.setWindowFlags(
                Qt.WindowType.Widget
            )

        self.project_manager = ProjectManager()
        self.ffmpeg_tools = FFmpegTools()
        self.worker = None
        self._close_pending = False
        self._can_edit = False
        self._can_review = False
        self._current_mode = None
        self.review_windows = []

        self.project_dir, self.project_data = (
            self.project_manager.load_project(project_dir)
        )

        self.setWindowTitle(
            f"TakeDream — {self.project_data['name']}"
        )
        self.resize(1380, 850)
        self.setMinimumSize(1100, 700)

        root = QWidget()
        root.setObjectName("Root")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.sidebar = TakeDreamSidebar("projects")
        self.sidebar.navigate.connect(self._sidebar_nav)
        root_layout.addWidget(self.sidebar)

        content = QWidget()
        content.setObjectName("AppPage")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(22, 20, 22, 18)
        content_layout.setSpacing(14)

        # --------------------------------------------------------------
        # HEADER
        # --------------------------------------------------------------
        header = QHBoxLayout()

        icon = QLabel("✦")
        icon.setFixedSize(44, 44)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            "background:#6D28D9; border-radius:22px;"
            "font-size:20px; font-weight:800; color:#FFFFFF;"
        )

        header_text = QVBoxLayout()
        header_text.setSpacing(0)
        project_title = QLabel(self.project_data["name"])
        project_title.setObjectName("PageTitle")

        profile_text = (
            f"{self.project_data.get('profile', '—')}  •  "
            f"{self.project_data.get('style', '—')}  •  "
            f"{self.project_data.get('aspect_ratio', '16:9')}"
        )
        profile_label = QLabel(profile_text)
        profile_label.setObjectName("PageSubtitle")

        header_text.addWidget(project_title)
        header_text.addWidget(profile_label)

        header.addWidget(icon)
        header.addSpacing(8)
        header.addLayout(header_text)
        header.addStretch(1)

        self.status_label = QLabel(
            "Preparando o projeto..."
        )
        self.status_label.setProperty("muted", True)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        self.status_label.setMaximumWidth(390)
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignVCenter
        )
        header.addWidget(self.status_label)

        content_layout.addLayout(header)

        # --------------------------------------------------------------
        # MAIN BODY
        # --------------------------------------------------------------
        body = QHBoxLayout()
        body.setSpacing(12)

        # Preview / media information.
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        preview_card = card(object_name="PlayerCard")
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_layout.setSpacing(8)

        preview_header = QHBoxLayout()
        preview_header.addWidget(
            section_title("◉  Vídeo do projeto")
        )
        preview_header.addStretch(1)
        aspect_badge = QLabel(
            self.project_data.get(
                "aspect_ratio",
                "16:9",
            )
        )
        aspect_badge.setStyleSheet(
            "background:#241C52; border:1px solid #7C5CE7;"
            "border-radius:8px; padding:5px 9px; font-weight:800;"
        )
        preview_header.addWidget(aspect_badge)
        preview_layout.addLayout(preview_header)

        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumHeight(330)
        self.video_widget.setStyleSheet(
            "background:#050814; border-radius:10px;"
        )

        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.55)

        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)

        source_path = Path(
            self.project_data.get(
                "source",
                {},
            ).get("original_path", "")
        )
        if source_path.exists():
            self.player.setSource(
                QUrl.fromLocalFile(
                    str(source_path.resolve())
                )
            )

        preview_controls = QHBoxLayout()
        self.preview_play_button = QPushButton("▶  Reproduzir")
        self.preview_play_button.clicked.connect(
            self._toggle_preview
        )
        preview_controls.addWidget(
            self.preview_play_button
        )
        preview_controls.addStretch(1)

        self.source_label = QLabel(
            self.project_data.get(
                "source",
                {},
            ).get("filename", "—")
        )
        self.source_label.setProperty("muted", True)
        self.source_label.setWordWrap(True)
        preview_controls.addWidget(self.source_label)

        preview_layout.addWidget(self.video_widget, 1)
        preview_layout.addLayout(preview_controls)
        left_layout.addWidget(preview_card, 2)

        info_card = card()
        info_layout = QGridLayout(info_card)
        info_layout.setContentsMargins(14, 12, 14, 12)
        info_layout.setHorizontalSpacing(12)
        info_layout.setVerticalSpacing(9)

        self.duration_value = self._metric_value("Ainda não analisado")
        self.resolution_value = self._metric_value("—")
        self.fps_value = self._metric_value("—")
        self.video_codec_value = self._metric_value("—")
        self.audio_codec_value = self._metric_value("—")
        self.audio_value = self._metric_value("—")
        self.ffmpeg_value = self._metric_value("Verificando...")

        metrics = (
            ("Duração", self.duration_value),
            ("Resolução", self.resolution_value),
            ("FPS", self.fps_value),
            ("Vídeo", self.video_codec_value),
            ("Áudio", self.audio_value),
            ("Codec áudio", self.audio_codec_value),
            ("FFmpeg", self.ffmpeg_value),
        )

        for index, (name, value) in enumerate(metrics):
            row = index // 4
            column = index % 4

            metric = QFrame()
            metric.setStyleSheet(
                "background:#171F3D; border:1px solid #2B3762;"
                "border-radius:10px;"
            )
            metric_layout = QVBoxLayout(metric)
            metric_layout.setContentsMargins(10, 8, 10, 8)
            metric_layout.setSpacing(1)

            label = QLabel(name)
            label.setProperty("muted", True)
            metric_layout.addWidget(label)
            metric_layout.addWidget(value)
            info_layout.addWidget(metric, row, column)

        left_layout.addWidget(info_card)

        # Pipeline.
        right = QWidget()
        right.setFixedWidth(430)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        pipeline_card = card()
        pipeline_layout = QVBoxLayout(pipeline_card)
        pipeline_layout.setContentsMargins(14, 14, 14, 14)
        pipeline_layout.setSpacing(10)

        pipeline_layout.addWidget(
            section_title("⚡  Fluxo do projeto")
        )
        pipeline_layout.addWidget(
            muted_label(
                "Do vídeo bruto à revisão em quatro etapas.",
                True,
            )
        )

        self.analyze_button = self._pipeline_button(
            "1",
            "Analisar vídeo",
            "Lê resolução, FPS, codecs e duração.",
        )
        self.analyze_button.clicked.connect(
            self.analyze_media
        )

        self.process_button = self._pipeline_button(
            "2",
            "Transcrever e analisar áudio",
            "Extrai WAV, transcreve e encontra silêncios.",
        )
        self.process_button.clicked.connect(
            lambda: self._start_worker("process")
        )

        self.edit_button = self._pipeline_button(
            "3",
            "Gerar primeira edição",
            "Cria o plano de cortes e renderiza a prévia.",
        )
        self.edit_button.setEnabled(False)
        self.edit_button.clicked.connect(
            lambda: self._start_worker("edit")
        )

        self.review_button = self._pipeline_button(
            "4",
            "Revisar na linha do tempo",
            "Ajuste cortes, legenda, formato, zoom e exportação.",
            primary=True,
        )
        self.review_button.setEnabled(False)
        self.review_button.clicked.connect(
            self.open_review
        )

        for button in (
            self.analyze_button,
            self.process_button,
            self.edit_button,
            self.review_button,
        ):
            pipeline_layout.addWidget(button)

        right_layout.addWidget(pipeline_card)

        results_card = card()
        results_layout = QVBoxLayout(results_card)
        results_layout.setContentsMargins(14, 12, 14, 12)
        results_layout.setSpacing(7)
        results_layout.addWidget(
            section_title("▤  Resultado do processamento")
        )

        self.result_label = QLabel(
            "Transcrição: ainda não processada"
        )
        self.result_label.setProperty("muted", True)
        self.result_label.setWordWrap(True)
        self.result_label.setTextFormat(
            Qt.TextFormat.PlainText
        )

        self.edit_result_label = QLabel(
            "Edição automática: aguardando transcrição e silêncios."
        )
        self.edit_result_label.setProperty("muted", True)
        self.edit_result_label.setWordWrap(True)
        self.edit_result_label.setTextFormat(
            Qt.TextFormat.PlainText
        )

        results_layout.addWidget(self.result_label)
        results_layout.addWidget(self.edit_result_label)
        right_layout.addWidget(results_card, 1)

        body.addWidget(left, 1)
        body.addWidget(right)
        content_layout.addLayout(body, 1)

        # --------------------------------------------------------------
        # FOOTER / PROGRESS
        # --------------------------------------------------------------
        footer_card = card(object_name="ExportCard")
        footer = QHBoxLayout(footer_card)
        footer.setContentsMargins(14, 11, 14, 11)
        footer.setSpacing(10)

        progress_text = QVBoxLayout()
        progress_text.setSpacing(2)
        progress_text.addWidget(
            section_title("Processamento")
        )
        progress_text.addWidget(
            muted_label(
                "Acompanhe o progresso sem travar a interface."
            )
        )
        footer.addLayout(progress_text)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setMinimumWidth(320)
        footer.addWidget(self.progress_bar, 1)

        self.cancel_button = QPushButton(
            "Cancelar"
        )
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(
            self._cancel_processing
        )
        footer.addWidget(self.cancel_button)

        close_button = QPushButton(
            "Voltar ao dashboard"
        )
        close_button.clicked.connect(
            self._go_home
        )
        footer.addWidget(close_button)

        content_layout.addWidget(footer_card)

        root_layout.addWidget(content, 1)
        self.setCentralWidget(root)

        apply_app_theme(self)
        if not embedded:
            enable_dark_title_bar(self)

        self._update_ffmpeg_status()
        self._load_saved_metadata()
        QTimer.singleShot(
            0,
            lambda: self._start_worker("load"),
        )

    def _metric_value(self, text):
        label = QLabel(text)
        label.setStyleSheet(
            "font-size:14px; font-weight:800; color:#FFFFFF;"
        )
        return label

    def _pipeline_button(
        self,
        number,
        title,
        description,
        primary=False,
    ):
        button = QPushButton(
            f"{number}   {title}\n      {description}"
        )
        button.setMinimumHeight(66)
        button.setStyleSheet(
            "QPushButton {text-align:left; padding:10px 12px;"
            "background:#171F3D; border:1px solid #34416F;"
            "border-radius:11px; color:#F8F8FF; font-weight:700;}"
            "QPushButton:hover {background:#242F5D;"
            "border-color:#8B5CF6;}"
            "QPushButton:disabled {color:#69739A;"
            "background:#121932; border-color:#263158;}"
        )
        if primary:
            button.setProperty("primary", True)
        return button

    def _toggle_preview(self):
        if (
            self.player.playbackState()
            == QMediaPlayer.PlaybackState.PlayingState
        ):
            self.player.pause()
            self.preview_play_button.setText(
                "▶  Reproduzir"
            )
        else:
            self.player.play()
            self.preview_play_button.setText(
                "Ⅱ  Pausar"
            )

    def _sidebar_nav(self, target):
        if target == "review":
            self.open_review()
            return

        if self.host is not None and hasattr(
            self.host,
            "_navigate",
        ):
            self.player.stop()
            self.host._navigate(target)
            return

        parent = self.parent()
        if parent is not None and hasattr(
            parent,
            "_navigate",
        ):
            if target == "new":
                self.close()
                parent.create_project()
            elif target in (
                "home",
                "projects",
                "exports",
                "settings",
            ):
                self.close()
                parent._navigate(target)

    def _go_home(self):
        self.player.stop()

        if self.host is not None and hasattr(
            self.host,
            "_navigate",
        ):
            self.host._navigate("home")
            return

        self.close()

    def analyze_media(self):
        self._start_worker("analyze")

    def _start_worker(self, mode):
        if self.worker is not None or self._close_pending:
            return

        self._current_mode = mode
        self.analyze_button.setEnabled(False)
        self.process_button.setEnabled(False)
        self.edit_button.setEnabled(False)
        self.review_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setRange(0, 0)

        if mode == "analyze":
            status = "Analisando mídia com FFprobe..."
        elif mode == "load":
            status = "Carregando resultados..."
        elif mode == "edit":
            status = "Preparando primeira edição automática..."
        else:
            status = "Iniciando processamento..."

        self.status_label.setText(status)

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
            self.status_label.setText(
                "Análise concluída • media_metadata.json salvo."
            )
        else:
            transcript = result.get("transcript")
            silences = result.get("silences")
            errors = result.get("errors", [])
            edit_errors = result.get("edit_errors", [])
            edit_plan = result.get("edit_plan")
            output_path = result.get("output_path")

            lines = [
                "Áudio: "
                + ("OK" if result.get("audio_path") else "não extraído")
            ]

            if transcript is not None:
                lines.extend(
                    [
                        "Transcrição: OK",
                        f"Idioma: {transcript['language']['detected']}",
                        f"Segmentos: {len(transcript['segments'])}",
                    ]
                )
            else:
                lines.append("Transcrição: ainda não processada")

            lines.append(
                f"Silêncios encontrados: {len(silences['silences'])}"
                if silences is not None
                else "Silêncios: ainda não analisados"
            )

            if transcript is not None:
                lines.append(transcript["text"][:400])

            self.result_label.setText("\n".join(lines))

            edit_lines = []
            if edit_plan is not None:
                stats = edit_plan["stats"]
                original = self._format_ms(
                    edit_plan["source_duration_ms"]
                )
                estimated = self._format_ms(
                    stats["estimated_duration_ms"]
                )
                removed = self._format_ms(
                    stats["removed_duration_ms"]
                )

                edit_lines.extend(
                    [
                        "Plano de edição: OK",
                        f"Cortes automáticos: {stats['cuts']}",
                        f"Duração original: {original}",
                        f"Duração estimada: {estimated}",
                        f"Tempo removido: {removed}",
                    ]
                )

            if output_path:
                edit_lines.append(f"Vídeo editado: {output_path}")
                if result.get("render_encoder"):
                    edit_lines.append(
                        f"Render: {result['render_encoder']}"
                    )
                self._can_review = True
                self.review_button.setEnabled(self.worker is None)

            if not edit_lines:
                edit_lines.append(
                    "Edição automática: aguardando transcrição e silêncios."
                )

            self.edit_result_label.setText("\n".join(edit_lines))

            self._can_edit = (
                bool(result.get("audio_path"))
                and transcript is not None
                and silences is not None
                and not errors
                and not edit_errors
            )

            all_errors = list(errors) + list(edit_errors)

            if all_errors:
                self.status_label.setText(
                    "Resultados inválidos. Faça backup dos arquivos "
                    "indicados antes de reprocessar."
                )
                if not self._close_pending:
                    QMessageBox.warning(
                        self,
                        "Resultados inválidos",
                        "\n".join(all_errors),
                    )
            elif output_path:
                self.status_label.setText(
                    "Edição pronta. Revise os cortes na linha do tempo."
                )
                if self._current_mode == "edit":
                    QTimer.singleShot(150, self.open_review)
            elif transcript is not None and silences is not None:
                self.status_label.setText(
                    "Transcrição pronta. Já pode gerar a primeira edição automática."
                )
            else:
                self.status_label.setText(
                    "Pronto para continuar o processamento."
                )

        self._set_progress(100)

        try:
            _, self.project_data = self.project_manager.load_project(
                self.project_dir
            )
        except ValueError as error:
            self._processing_error(str(error))

    def _processing_error(self, message):
        self.status_label.setText(message)
        self.status_label.setWordWrap(True)
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

        self.analyze_button.setEnabled(True)
        self.process_button.setEnabled(True)
        self.edit_button.setEnabled(self._can_edit)
        self.review_button.setEnabled(self._can_review)
        self.cancel_button.setEnabled(False)
        self.progress_bar.setRange(0, 100)

        if self._close_pending:
            self.close()

    def open_review(self):
        if not self._can_review:
            return

        if self.host is not None and hasattr(
            self.host,
            "_show_review_page",
        ):
            self.player.pause()
            self.host._show_review_page(
                self.project_dir
            )
            return

        try:
            window = ReviewWindow(self.project_dir, self)
        except ValueError as error:
            QMessageBox.warning(
                self,
                "Não foi possível abrir a revisão",
                str(error),
            )
            return

        self.review_windows.append(window)
        window.destroyed.connect(
            lambda: self._remove_review_window(window)
        )
        window.show()

    def _remove_review_window(self, window):
        if window in self.review_windows:
            self.review_windows.remove(window)

    def _cancel_processing(self):
        if self.worker is not None:
            self.worker.cancel.set()
            self.cancel_button.setEnabled(False)
            self.status_label.setText(
                "Interrompendo processamento com segurança..."
            )

    def closeEvent(self, event):
        if self.worker is not None:
            self._close_pending = True
            self._cancel_processing()
            event.ignore()
        else:
            event.accept()

    def _load_saved_metadata(self):
        metadata = self.project_manager.load_media_metadata(
            self.project_dir
        )

        if metadata:
            try:
                self._apply_metadata(metadata)
            except (AttributeError, TypeError, ValueError):
                self.status_label.setText(
                    "Metadados inválidos. Analise o vídeo novamente."
                )
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

            self.ffmpeg_value.setText(
                "Ausente: " + ", ".join(missing)
            )

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
        self.fps_value.setText(
            f"{fps:g}" if fps is not None else "—"
        )

        self.video_codec_value.setText(
            video.get("codec") or "—"
        )

        has_audio = bool(audio.get("present"))
        self.audio_value.setText(
            "Sim" if has_audio else "Não"
        )
        self.audio_codec_value.setText(
            audio.get("codec") if has_audio else "—"
        )

        self._update_ffmpeg_status()

    @staticmethod
    def _format_ms(milliseconds):
        if type(milliseconds) is not int:
            return "—"

        total_seconds = max(0, int(round(milliseconds / 1000)))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        return f"{minutes:02d}:{seconds:02d}"
