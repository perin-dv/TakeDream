from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from editor.edit_plan import validate_edit_plan


class TimelineWidget(QWidget):
    segmentSelected = Signal(int)
    seekRequested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._plan = None
        self._selected_index = None
        self._playhead_source_ms = 0
        self._mark_in_ms = None
        self._mark_out_ms = None
        self._zoom_factor = 1
        self._base_width = 1080
        self.setMinimumHeight(104)
        self.setMinimumWidth(self._base_width)
        self.setMouseTracking(True)

    def set_plan(self, plan):
        self._plan = validate_edit_plan(plan)
        self._selected_index = None
        self._playhead_source_ms = min(
            self._playhead_source_ms,
            self._plan["source_duration_ms"],
        )
        self.update()

    def set_playhead_source_ms(self, value):
        if self._plan is None:
            return

        duration = self._plan["source_duration_ms"]
        self._playhead_source_ms = max(0, min(int(value), duration))
        self.update()

    def set_markers(self, mark_in_ms=None, mark_out_ms=None):
        self._mark_in_ms = (
            None if mark_in_ms is None else int(mark_in_ms)
        )
        self._mark_out_ms = (
            None if mark_out_ms is None else int(mark_out_ms)
        )
        self.update()

    def set_zoom_factor(self, factor):
        factor = max(1, min(int(factor), 8))
        self._zoom_factor = factor
        self.setMinimumWidth(self._base_width * factor)
        self.resize(
            max(self.width(), self.minimumWidth()),
            self.height(),
        )
        self.updateGeometry()
        self.update()

    def selected_index(self):
        return self._selected_index

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        area = self.rect().adjusted(12, 22, -12, -28)
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
            width = max(1.0, area.width() * (end_ratio - start_ratio))
            rect = QRectF(x, area.top(), width, area.height())

            fill = (
                QColor("#d95d5d")
                if segment["action"] == "remove"
                else QColor("#4aa889")
            )
            painter.fillRect(rect, fill)

            if index == self._selected_index:
                painter.setPen(QPen(QColor("#ffffff"), 2))
                painter.drawRect(rect)

        self._draw_marker(
            painter,
            area,
            duration,
            self._mark_in_ms,
            QColor("#52a8ff"),
            "IN",
        )
        self._draw_marker(
            painter,
            area,
            duration,
            self._mark_out_ms,
            QColor("#f4c95d"),
            "OUT",
        )

        playhead_ratio = self._playhead_source_ms / duration
        playhead_x = area.left() + area.width() * playhead_ratio
        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.drawLine(
            int(playhead_x),
            area.top() - 8,
            int(playhead_x),
            area.bottom() + 8,
        )

        painter.setPen(QColor("#9aa4b2"))
        painter.drawText(area.left(), self.height() - 8, "0:00")
        painter.drawText(
            area.right() - 54,
            self.height() - 8,
            self._format_ms(duration),
        )

    def _draw_marker(self, painter, area, duration, value, color, label):
        if value is None:
            return

        ratio = max(0.0, min(1.0, value / duration))
        x = area.left() + area.width() * ratio
        painter.setPen(QPen(color, 2))
        painter.drawLine(
            int(x),
            area.top() - 12,
            int(x),
            area.bottom() + 12,
        )
        painter.drawText(
            int(x) + 3,
            area.top() - 4,
            label,
        )

    def mousePressEvent(self, event):
        if self._plan is None:
            return

        area = self.rect().adjusted(12, 22, -12, -28)
        if not area.contains(event.position().toPoint()):
            return

        ratio = (event.position().x() - area.left()) / max(1, area.width())
        ratio = max(0.0, min(1.0, ratio))
        source_ms = int(round(self._plan["source_duration_ms"] * ratio))

        selected = None
        for index, segment in enumerate(self._plan["segments"]):
            if segment["start_ms"] <= source_ms < segment["end_ms"]:
                selected = index
                break

        if selected is None and self._plan["segments"]:
            selected = len(self._plan["segments"]) - 1

        self._selected_index = selected
        self.update()

        if selected is None:
            return

        self.segmentSelected.emit(selected)

        segment = self._plan["segments"][selected]
        if segment["action"] == "keep":
            self.seekRequested.emit(source_ms)

    @staticmethod
    def _format_ms(milliseconds):
        total_seconds = max(0, int(milliseconds // 1000))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"

        return f"{minutes}:{seconds:02d}"
