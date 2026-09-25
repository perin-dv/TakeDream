from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from editor.edit_plan import validate_edit_plan


class TimelineWidget(QWidget):
    segmentSelected = Signal(int)
    seekRequested = Signal(int)
    sourcePositionSelected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._plan = None
        self._selected_index = None
        self._playhead_source_ms = 0
        self._zoom = 1.0
        self._base_width = 1080
        self._waveform = []
        self._thumbnails = []
        self._content_analysis = None
        self.setFixedHeight(98)
        self.setMouseTracking(True)
        self._apply_zoom()

    def sizeHint(self):
        return QSize(
            int(self._base_width * self._zoom),
            98,
        )

    def set_plan(self, plan):
        self._plan = validate_edit_plan(plan)
        self._selected_index = None
        self._playhead_source_ms = 0
        self.update()

    def set_zoom(self, zoom):
        self._zoom = max(1.0, min(float(zoom), 10.0))
        self._apply_zoom()

    def zoom(self):
        return self._zoom

    def _apply_zoom(self):
        width = int(self._base_width * self._zoom)
        self.setFixedWidth(width)
        self.updateGeometry()
        self.update()

    def set_waveform(self, peaks):
        self._waveform = list(peaks or [])
        self.update()

    def set_thumbnails(self, paths):
        thumbnails = []

        for path in paths or []:
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                thumbnails.append(pixmap)

        self._thumbnails = thumbnails
        self.update()

    def set_content_analysis(self, analysis):
        self._content_analysis = (
            analysis
            if isinstance(analysis, dict)
            else None
        )
        self.update()

    def set_playhead_source_ms(self, value):
        if self._plan is None:
            return

        duration = self._plan["source_duration_ms"]
        self._playhead_source_ms = max(
            0,
            min(int(value), duration),
        )
        self.update()

    def selected_index(self):
        return self._selected_index

    def select_index(self, index):
        if self._plan is None:
            return

        if index is None:
            self._selected_index = None
        elif 0 <= index < len(self._plan["segments"]):
            self._selected_index = index
        else:
            return

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        area = self.rect().adjusted(12, 20, -12, -24)
        painter.fillRect(area, QColor("#0F1530"))

        if self._plan is None:
            painter.setPen(QColor("#9AA6CF"))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Nenhum plano de edição carregado",
            )
            return

        duration = self._plan["source_duration_ms"]
        if duration <= 0:
            return

        if self._thumbnails:
            thumb_width = (
                area.width()
                / len(self._thumbnails)
            )

            for thumb_index, pixmap in enumerate(
                self._thumbnails
            ):
                target = QRectF(
                    area.left()
                    + thumb_index
                    * thumb_width,
                    area.top(),
                    thumb_width + 1,
                    area.height(),
                )
                painter.drawPixmap(
                    target.toRect(),
                    pixmap,
                )

        for index, segment in enumerate(self._plan["segments"]):
            start_ratio = segment["start_ms"] / duration
            end_ratio = segment["end_ms"] / duration

            x = area.left() + area.width() * start_ratio
            width = max(
                1.0,
                area.width() * (end_ratio - start_ratio),
            )
            rect = QRectF(
                x,
                area.top(),
                width,
                area.height(),
            )

            if segment["action"] == "remove":
                fill = QColor(
                    255,
                    92,
                    122,
                    190 if self._thumbnails else 235,
                )
            else:
                fill = QColor(
                    139,
                    92,
                    246,
                    72 if self._thumbnails else 150,
                )

            painter.fillRect(rect, fill)

            if segment.get("reason", "").startswith("manual"):
                painter.setPen(QPen(QColor("#ffd166"), 1))
                painter.drawLine(
                    int(rect.left()),
                    int(rect.top()),
                    int(rect.left()),
                    int(rect.bottom()),
                )

            if index == self._selected_index:
                painter.setPen(QPen(QColor("#D8B4FE"), 2))
                painter.drawRect(rect)

        if self._waveform:
            center_y = area.center().y()
            half_height = area.height() * 0.42
            painter.setPen(
                QPen(QColor(255, 255, 255, 155), 1)
            )

            count = len(self._waveform)
            for wave_index, peak in enumerate(self._waveform):
                x = area.left() + (
                    area.width()
                    * wave_index
                    / max(1, count - 1)
                )
                amplitude = (
                    max(0, min(int(peak), 1000))
                    / 1000
                ) * half_height
                painter.drawLine(
                    int(x),
                    int(center_y - amplitude),
                    int(x),
                    int(center_y + amplitude),
                )

        if self._content_analysis:
            marker_groups = (
                (
                    self._content_analysis.get(
                        "speech_suggestions",
                        [],
                    ),
                    QColor("#ff9f1c"),
                ),
                (
                    self._content_analysis.get(
                        "broll_suggestions",
                        [],
                    ),
                    QColor("#3a86ff"),
                ),
                (
                    self._content_analysis.get(
                        "zoom_events",
                        [],
                    ),
                    QColor("#c77dff"),
                ),
            )

            for items, marker_color in marker_groups:
                painter.setPen(
                    QPen(marker_color, 2)
                )
                for item in items:
                    start_ms = item.get(
                        "start_ms"
                    )
                    if type(start_ms) is not int:
                        continue
                    ratio = (
                        start_ms / duration
                    )
                    x = (
                        area.left()
                        + area.width() * ratio
                    )
                    painter.drawLine(
                        int(x),
                        area.top(),
                        int(x),
                        area.top() + 12,
                    )

        playhead_ratio = self._playhead_source_ms / duration
        playhead_x = area.left() + area.width() * playhead_ratio
        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.drawLine(
            int(playhead_x),
            area.top() - 6,
            int(playhead_x),
            area.bottom() + 6,
        )

        painter.setPen(QColor("#9aa4b2"))
        painter.drawText(
            area.left(),
            self.height() - 6,
            "0:00",
        )
        painter.drawText(
            area.right() - 55,
            self.height() - 6,
            self._format_ms(duration),
        )

    def mousePressEvent(self, event):
        if self._plan is None:
            return

        area = self.rect().adjusted(12, 20, -12, -24)
        if not area.contains(event.position().toPoint()):
            return

        ratio = (
            event.position().x() - area.left()
        ) / max(1, area.width())
        ratio = max(0.0, min(1.0, ratio))

        source_ms = int(
            round(self._plan["source_duration_ms"] * ratio)
        )
        source_ms = min(
            source_ms,
            self._plan["source_duration_ms"] - 1,
        )

        selected = None
        for index, segment in enumerate(self._plan["segments"]):
            if (
                segment["start_ms"]
                <= source_ms
                < segment["end_ms"]
            ):
                selected = index
                break

        if selected is None and self._plan["segments"]:
            selected = len(self._plan["segments"]) - 1

        self._selected_index = selected
        self._playhead_source_ms = source_ms
        self.update()

        self.sourcePositionSelected.emit(source_ms)
        self.seekRequested.emit(source_ms)

        if selected is not None:
            self.segmentSelected.emit(selected)

    @staticmethod
    def _format_ms(milliseconds):
        total_seconds = max(0, int(milliseconds // 1000))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"

        return f"{minutes}:{seconds:02d}"
