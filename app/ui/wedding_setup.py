from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.ui.components import SelectionCardButton
from app.ui.icons import app_icon
from core.deliverables import deliverables_for_profile, get_deliverable_preset


class DurationSpinBox(QSpinBox):
    def textFromValue(self, value):
        minutes, seconds = divmod(int(value), 60)
        if minutes and seconds:
            return f"{minutes}m {seconds:02d}s"
        if minutes:
            return f"{minutes} min"
        return f"{seconds}s"


class WeddingSetupWidget(QFrame):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("WeddingSetup")
        self.setStyleSheet(
            "QFrame#WeddingSetup {"
            "background:#F7F4FF; border:1px solid #D9D0F3;"
            "border-radius:12px;}"
        )

        self.selected_deliverable = "trailer"
        self.reference_video_path = ""
        self.music_path = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(13, 12, 13, 12)
        root.setSpacing(9)

        title = QLabel("Entrega do casamento")
        title.setStyleSheet("font-size:14px; font-weight:800; color:#201B38;")
        subtitle = QLabel(
            "Defina o produto final. A mesma biblioteca pode gerar versões diferentes sem reanalisar tudo."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("font-size:11px; color:#6C6682;")
        root.addWidget(title)
        root.addWidget(subtitle)

        self.deliverable_group = QButtonGroup(self)
        self.deliverable_group.setExclusive(True)
        self.deliverable_buttons = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(7)
        grid.setVerticalSpacing(7)

        icons = {
            "teaser": "dynamic",
            "trailer": "star",
            "film": "video",
            "custom": "settings",
        }
        accents = {
            "teaser": "#E879F9",
            "trailer": "#8B5CF6",
            "film": "#D99A4E",
            "custom": "#64748B",
        }

        for index, preset in enumerate(deliverables_for_profile("Casamento")):
            short = {
                "teaser": "30s–1m30",
                "trailer": "2m30–5m",
                "film": "15–30 min",
                "custom": "30s–60 min",
            }[preset.key]
            button = SelectionCardButton(
                preset.label,
                short,
                icons[preset.key],
                accent=accents[preset.key],
                light=True,
            )
            button.setMinimumHeight(76)
            button.setToolTip(preset.description)
            self.deliverable_group.addButton(button)
            self.deliverable_buttons[preset.key] = button
            button.clicked.connect(
                lambda checked=False, key=preset.key: self.set_deliverable(key)
            )
            grid.addWidget(button, index // 2, index % 2)

        root.addLayout(grid)

        duration_row = QHBoxLayout()
        duration_label = QLabel("Duração alvo")
        duration_label.setStyleSheet("font-weight:700; color:#30294D;")
        self.duration_spin = DurationSpinBox()
        self.duration_spin.setAccelerated(True)
        self.duration_spin.setMinimumWidth(118)
        self.duration_spin.valueChanged.connect(lambda _: self.changed.emit())
        duration_row.addWidget(duration_label)
        duration_row.addStretch(1)
        duration_row.addWidget(self.duration_spin)
        root.addLayout(duration_row)

        self.deliverable_summary = QLabel()
        self.deliverable_summary.setWordWrap(True)
        self.deliverable_summary.setStyleSheet(
            "background:#FFFFFF; border:1px solid #E2DDF1; border-radius:8px;"
            "padding:7px 9px; font-size:11px; color:#5D5674;"
        )
        root.addWidget(self.deliverable_summary)

        separator = QFrame()
        separator.setFixedHeight(1)
        separator.setStyleSheet("background:#E2DDF1;")
        root.addWidget(separator)

        ref_title = QLabel("Editor por referência")
        ref_title.setStyleSheet("font-weight:800; color:#30294D;")
        ref_hint = QLabel(
            "Opcional: escolha um casamento modelo e uma nova música. O TakeDream aprende o ritmo do modelo e adapta os cortes à música escolhida."
        )
        ref_hint.setWordWrap(True)
        ref_hint.setStyleSheet("font-size:11px; color:#6C6682;")
        root.addWidget(ref_title)
        root.addWidget(ref_hint)

        ref_row = QHBoxLayout()
        self.reference_button = QPushButton("Vídeo referência")
        self.reference_button.setIcon(
            app_icon("video", color="#5B4A85", accent="#8B5CF6", size=17)
        )
        self.reference_button.clicked.connect(self.select_reference_video)
        self.reference_label = QLabel("Nenhum")
        self.reference_label.setStyleSheet("font-size:11px; color:#6C6682;")
        self.reference_label.setToolTip("")
        ref_row.addWidget(self.reference_button)
        ref_row.addWidget(self.reference_label, 1)
        root.addLayout(ref_row)

        music_row = QHBoxLayout()
        self.music_button = QPushButton("Escolher música")
        self.music_button.setIcon(
            app_icon("audio", color="#5B4A85", accent="#C084FC", size=17)
        )
        self.music_button.clicked.connect(self.select_music)
        self.music_label = QLabel("Nenhuma")
        self.music_label.setStyleSheet("font-size:11px; color:#6C6682;")
        self.music_label.setToolTip("")
        music_row.addWidget(self.music_button)
        music_row.addWidget(self.music_label, 1)
        root.addLayout(music_row)

        self.reference_status = QLabel(
            "Sem referência: o TakeDream usa o estilo de casamento selecionado."
        )
        self.reference_status.setWordWrap(True)
        self.reference_status.setStyleSheet("font-size:11px; color:#7653A6;")
        root.addWidget(self.reference_status)

        self.set_deliverable("trailer")

    def set_deliverable(self, key):
        preset = get_deliverable_preset("Casamento", key)
        self.selected_deliverable = preset.key

        for name, button in self.deliverable_buttons.items():
            blocked = button.blockSignals(True)
            button.setChecked(name == key)
            button.blockSignals(blocked)

        blocked = self.duration_spin.blockSignals(True)
        self.duration_spin.setRange(preset.minimum_seconds, preset.maximum_seconds)
        self.duration_spin.setValue(preset.target_seconds)
        self.duration_spin.blockSignals(blocked)

        self.deliverable_summary.setText(
            f"{preset.description}  Ritmo: {preset.pacing} • "
            f"take médio ~{preset.average_shot_seconds:.1f}s."
        )
        self.changed.emit()

    def select_reference_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Escolher casamento de referência",
            "",
            "Vídeos (*.mp4 *.mov *.mkv *.avi *.webm *.m4v);;Todos os arquivos (*)",
        )
        if path:
            self.reference_video_path = str(Path(path).expanduser().resolve())
            self.reference_label.setText(Path(path).name)
            self.reference_label.setToolTip(self.reference_video_path)
            self._refresh_reference_status()
            self.changed.emit()

    def select_music(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Escolher música do casamento",
            "",
            "Áudio (*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.opus);;Vídeo com áudio (*.mp4 *.mov *.mkv);;Todos os arquivos (*)",
        )
        if path:
            self.music_path = str(Path(path).expanduser().resolve())
            self.music_label.setText(Path(path).name)
            self.music_label.setToolTip(self.music_path)
            self._refresh_reference_status()
            self.changed.emit()

    def _refresh_reference_status(self):
        if self.reference_video_path and self.music_path:
            text = "Referência + música prontas: o ritmo será remapeado para a nova trilha."
        elif self.reference_video_path:
            text = "Referência pronta: o TakeDream aprenderá o DNA de cortes deste vídeo."
        elif self.music_path:
            text = "Música pronta: a montagem poderá sincronizar cortes aos pontos fortes da trilha."
        else:
            text = "Sem referência: o TakeDream usa o estilo de casamento selecionado."
        self.reference_status.setText(text)

    def data(self):
        return {
            "deliverable_type": self.selected_deliverable,
            "target_duration_seconds": int(self.duration_spin.value()),
            "reference_video": self.reference_video_path or None,
            "music_path": self.music_path or None,
        }
