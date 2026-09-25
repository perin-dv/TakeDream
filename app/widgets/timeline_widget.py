from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
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
        self.setMinimumHeight(98)
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
        self.setMinimumWidth(width)
        self.resize(width, max(self.height(), 98))
        self.updateGeometry()
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
        painter.fillRect(area, QColor("#20242b"))

        if self._plan is None:
            painter.setPen(QColor("#9aa4b2"))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Nenhum plano de edição carregado",
            )
            return

        duration = self._plan["source_duration_ms"]
        if duration <= 0:
            return

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

            fill = (
                QColor("#d95d5d")
                if segment["action"] == "remove"
                else QColor("#4aa889")
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
                painter.setPen(QPen(QColor("#ffffff"), 2))
                painter.drawRect(rect)

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
