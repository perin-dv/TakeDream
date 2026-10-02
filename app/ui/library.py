"""Compact library widgets; consume existing project/export metadata only."""
from datetime import datetime
from pathlib import Path
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from app.ui.icons import app_icon, icon_pixmap


class ElidedLabel(QLabel):
    def __init__(self, text, role="LibraryMeta"):
        super().__init__()
        self.full_text = str(text or "—")
        self.setObjectName(role)
        self.setToolTip(self.full_text)
        self.setAccessibleName(self.full_text)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(23)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.setText(self.fontMetrics().elidedText(
            self.full_text, Qt.TextElideMode.ElideRight, self.width()))


def chip(text, success=False):
    label = QLabel(str(text))
    label.setObjectName("LibraryChip")
    label.setProperty("success", success)
    label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return label


def action(text, icon, callback, primary=False):
    button = QPushButton(text)
    button.setIcon(app_icon(icon, color="#EDE9FE", accent="#C084FC", size=16))
    button.setProperty("primary" if primary else "secondary", True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.clicked.connect(lambda checked=False: callback())
    return button


def date_text(value):
    try:
        date = datetime.fromtimestamp(value).astimezone() if isinstance(value, (float, int)) else datetime.fromisoformat(value).astimezone()
        return date.strftime("%d/%m/%Y · %H:%M")
    except (ValueError, TypeError, OSError, OverflowError):
        return "Data indisponível"


class Thumbnail(QWidget):
    def __init__(self, directory):
        super().__init__()
        self.setFixedHeight(112)
        self.pixmap = QPixmap()
        for path in sorted((Path(directory) / "cache" / "thumbnails").glob("thumb_*.jpg")):
            self.pixmap = QPixmap(str(path))
            if not self.pixmap.isNull():
                break
        self.setAccessibleName("Miniatura do projeto" if not self.pixmap.isNull() else "Projeto sem miniatura")

    def paintEvent(self, event):
        from PySide6.QtGui import QLinearGradient, QPainterPath
        from PySide6.QtCore import QRectF
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 10, 10)
        painter.setClipPath(path)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0, QColor("#30205C"))
        gradient.setColorAt(1, QColor("#173752"))
        painter.fillRect(self.rect(), gradient)
        if not self.pixmap.isNull():
            scaled = self.pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap((self.width()-scaled.width())//2, (self.height()-scaled.height())//2, scaled)
        else:
            painter.setPen(QColor("#65509B"))
            for offset in (0, 40, 80):
                painter.drawEllipse(self.width()-140+offset, -65+offset, 180, 180)
            painter.drawPixmap(20, 28, icon_pixmap("brand", color="#FFFFFF", accent="#C084FC", size=52))


class ProjectCard(QFrame):
    def __init__(self, project, open_project, open_folder):
        super().__init__()
        self.setObjectName("LibraryCard")
        self.setFixedHeight(326)
        self.setMaximumWidth(520)
        box = QVBoxLayout(self)
        box.setContentsMargins(14, 14, 14, 14)
        box.setSpacing(7)
        box.addWidget(Thumbnail(project["project_dir"]))
        box.addWidget(ElidedLabel(project["name"], "LibraryTitle"))
        tags = QHBoxLayout()
        for field in ("profile", "style", "aspect_ratio"):
            tags.addWidget(chip(project.get(field, "—")))
        tags.addStretch()
        box.addLayout(tags)
        box.addWidget(ElidedLabel("Origem: " + project.get("source_filename", "—")))
        status = project.get("status", "created")
        names = {"created": "Criado", "media_analyzed": "Analisado", "transcribed": "Transcrito", "processed": "Processado", "audio_extracted": "Áudio extraído", "transcription_ready": "Transcrição pronta", "content_analyzed": "Conteúdo analisado", "rendered": "Prévia pronta", "review_rendered": "Revisado", "edited": "Editado", "reviewed": "Revisado", "exported": "Exportado", "completed": "Concluído", "error": "Erro", "failed": "Falha"}
        meta = QHBoxLayout()
        meta.addWidget(chip(names.get(status, status.replace("_", " ").capitalize()), status in ("exported", "completed", "reviewed", "review_rendered")))
        meta.addWidget(ElidedLabel(date_text(project.get("updated_at"))), 1)
        box.addLayout(meta)
        buttons = QHBoxLayout()
        buttons.addWidget(action("Abrir projeto", "projects", open_project, True), 1)
        buttons.addWidget(action("Pasta", "folder", open_folder))
        box.addLayout(buttons)


class ExportCard(QFrame):
    def __init__(self, item, open_file, open_folder):
        super().__init__()
        self.setObjectName("LibraryCard")
        self.setFixedHeight(146)
        box = QVBoxLayout(self)
        box.setContentsMargins(16, 12, 16, 12)
        box.setSpacing(6)
        top = QHBoxLayout()
        top.addWidget(ElidedLabel(item["project_name"], "LibraryTitle"), 1)
        top.addWidget(chip("Exportado", True))
        box.addLayout(top)
        box.addWidget(ElidedLabel(item["filename"]))
        bottom = QHBoxLayout()
        quality = re.search(r"(?:^|_)(original|1080p|720p|480p|360p)(?:_|\.)", item["filename"], re.I)
        aspect = re.search(r"(?:^|_)(16x9|9x16|1x1|4x5)(?:_|\.)", item["filename"], re.I)
        if quality:
            bottom.addWidget(chip(quality[1].capitalize() if quality[1].lower() == "original" else quality[1]))
        if aspect:
            bottom.addWidget(chip(aspect[1].lower().replace("x", ":")))
        size = item["size_bytes"] / (1024 * 1024)
        bottom.addWidget(ElidedLabel(f"{size:.1f} MB · {date_text(item.get('modified_at'))}"), 1)
        bottom.addWidget(action("Abrir", "play", open_file, True))
        bottom.addWidget(action("Pasta", "folder", open_folder))
        box.addLayout(bottom)


def library_scroll(body):
    scroll = QScrollArea()
    scroll.setObjectName("AppPageScroll")
    scroll.viewport().setObjectName("AppPageViewport")
    body.setObjectName("AppPage")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidget(body)
    return scroll


class ProjectGrid(QWidget):
    def __init__(self, cards):
        super().__init__()
        self.cards = cards
        self.columns = 0
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 8, 12)
        self.grid.setSpacing(16)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.reflow(1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reflow(max(1, min(3, (self.width() + 16) // 376)))

    def reflow(self, columns):
        if columns == self.columns:
            return
        for column in range(3):
            self.grid.setColumnStretch(column, 0)
            self.grid.setColumnMinimumWidth(column, 0)
        while self.grid.count():
            self.grid.takeAt(0)
        self.columns = columns
        for index, widget in enumerate(self.cards):
            self.grid.addWidget(widget, index // columns, index % columns)
        for column in range(columns):
            self.grid.setColumnStretch(column, 1)
            self.grid.setColumnMinimumWidth(column, 340)
