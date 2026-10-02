from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)


DEFAULT_FG = "#EDE9FE"
DEFAULT_ACCENT = "#A855F7"


def _pen(color, width):
    pen = QPen(QColor(color))
    pen.setWidthF(width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _triangle(cx, cy, width, height):
    return QPolygonF(
        [
            QPointF(cx - width * 0.35, cy - height / 2),
            QPointF(cx + width * 0.5, cy),
            QPointF(cx - width * 0.35, cy + height / 2),
        ]
    )


@lru_cache(maxsize=256)
def app_icon(name, color=DEFAULT_FG, accent=DEFAULT_ACCENT, size=24):
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    scale = size / 24.0
    painter.scale(scale, scale)
    painter.setPen(_pen(color, 1.8))
    painter.setBrush(Qt.BrushStyle.NoBrush)

    n = str(name).lower().strip()

    if n in {"home", "inicio"}:
        roof = QPolygonF(
            [
                QPointF(4.5, 11),
                QPointF(12, 4.5),
                QPointF(19.5, 11),
            ]
        )
        painter.drawPolyline(roof)
        painter.drawRoundedRect(QRectF(6.5, 10, 11, 9), 1.5, 1.5)
        painter.drawLine(10, 19, 10, 14)
        painter.drawLine(14, 14, 14, 19)

    elif n in {"plus", "new", "novo"}:
        painter.drawEllipse(QRectF(3.5, 3.5, 17, 17))
        painter.drawLine(12, 7.5, 12, 16.5)
        painter.drawLine(7.5, 12, 16.5, 12)

    elif n in {"projects", "folder"}:
        path = QPainterPath()
        path.moveTo(3.5, 7.5)
        path.lineTo(9, 7.5)
        path.lineTo(11, 9.5)
        path.lineTo(20.5, 9.5)
        path.lineTo(19, 18.5)
        path.lineTo(4.5, 18.5)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawLine(4.5, 6, 9.5, 6)

    elif n in {"review", "scissors", "split"}:
        painter.drawEllipse(QRectF(3.5, 5, 5, 5))
        painter.drawEllipse(QRectF(3.5, 14, 5, 5))
        painter.drawLine(8, 8, 20, 16.5)
        painter.drawLine(8, 16.5, 13.2, 12.8)
        painter.drawLine(15.2, 11.3, 20, 8)

    elif n in {"exports", "export"}:
        painter.drawRoundedRect(QRectF(4, 13, 16, 7), 2, 2)
        painter.drawLine(12, 15.5, 12, 5)
        painter.drawLine(8.5, 8.5, 12, 5)
        painter.drawLine(15.5, 8.5, 12, 5)

    elif n in {"settings", "gear"}:
        painter.drawEllipse(QRectF(7.5, 7.5, 9, 9))
        painter.drawEllipse(QRectF(10.2, 10.2, 3.6, 3.6))
        for angle in range(0, 360, 45):
            painter.save()
            painter.translate(12, 12)
            painter.rotate(angle)
            painter.drawLine(0, -8.3, 0, -10)
            painter.restore()

    elif n in {"play"}:
        painter.setBrush(QColor(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(_triangle(12, 12, 11, 13))

    elif n in {"pause"}:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawRoundedRect(QRectF(6.5, 5, 4, 14), 1, 1)
        painter.drawRoundedRect(QRectF(13.5, 5, 4, 14), 1, 1)

    elif n in {"volume"}:
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(4, 10),
                    QPointF(8, 10),
                    QPointF(12, 6),
                    QPointF(12, 18),
                    QPointF(8, 14),
                    QPointF(4, 14),
                ]
            )
        )
        painter.drawArc(QRectF(10, 8, 7, 8), -55 * 16, 110 * 16)
        painter.drawArc(QRectF(8.5, 5.5, 12, 13), -50 * 16, 100 * 16)

    elif n in {"fullscreen"}:
        for x, y, sx, sy in (
            (5, 5, 1, 1),
            (19, 5, -1, 1),
            (5, 19, 1, -1),
            (19, 19, -1, -1),
        ):
            painter.drawLine(x, y, x + sx * 5, y)
            painter.drawLine(x, y, x, y + sy * 5)

    elif n in {"eye", "preview"}:
        path = QPainterPath()
        path.moveTo(3.5, 12)
        path.cubicTo(7, 6.5, 17, 6.5, 20.5, 12)
        path.cubicTo(17, 17.5, 7, 17.5, 3.5, 12)
        painter.drawPath(path)
        painter.drawEllipse(QRectF(9, 9, 6, 6))

    elif n in {"youtube", "video"}:
        painter.setPen(_pen(color, 1.6))
        painter.drawRoundedRect(QRectF(3, 6, 18, 12), 4, 4)
        painter.setBrush(QColor(accent))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(_triangle(12, 12, 7, 8))

    elif n in {"shorts", "dynamic", "bolt"}:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(accent))
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(13, 2.8),
                    QPointF(6.5, 13),
                    QPointF(11, 13),
                    QPointF(9.5, 21),
                    QPointF(17.5, 10),
                    QPointF(13, 10),
                ]
            )
        )

    elif n in {"podcast", "mic"}:
        painter.drawRoundedRect(QRectF(8, 3, 8, 12), 4, 4)
        painter.drawArc(QRectF(5.5, 8, 13, 10), 180 * 16, 180 * 16)
        painter.drawLine(12, 18, 12, 21)
        painter.drawLine(8.5, 21, 15.5, 21)

    elif n in {"wedding", "rings"}:
        painter.drawEllipse(QRectF(4.5, 8, 9, 9))
        painter.drawEllipse(QRectF(10.5, 8, 9, 9))
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(14.8, 5),
                    QPointF(17, 2.8),
                    QPointF(19.2, 5),
                    QPointF(17, 7.2),
                ]
            )
        )

    elif n in {"gaming", "gamepad"}:
        path = QPainterPath()
        path.moveTo(5, 9)
        path.cubicTo(3.5, 12, 3.5, 17.5, 6.5, 19)
        path.cubicTo(8.5, 19.8, 9.5, 16.5, 11, 16.5)
        path.lineTo(13, 16.5)
        path.cubicTo(14.5, 16.5, 15.5, 19.8, 17.5, 19)
        path.cubicTo(20.5, 17.5, 20.5, 12, 19, 9)
        path.cubicTo(16.5, 6.5, 7.5, 6.5, 5, 9)
        painter.drawPath(path)
        painter.drawLine(8, 10, 8, 14)
        painter.drawLine(6, 12, 10, 12)
        painter.setBrush(QColor(accent))
        painter.drawEllipse(QRectF(15, 10, 2.2, 2.2))
        painter.drawEllipse(QRectF(17.5, 12.2, 2.2, 2.2))

    elif n in {"course", "book"}:
        painter.drawRoundedRect(QRectF(4, 5, 7.5, 14), 1.5, 1.5)
        painter.drawRoundedRect(QRectF(12.5, 5, 7.5, 14), 1.5, 1.5)
        painter.drawLine(12, 6, 12, 19)
        painter.drawLine(6, 8, 9.5, 8)
        painter.drawLine(14.5, 8, 18, 8)

    elif n in {"vsl", "sparkles", "ai"}:
        painter.setPen(_pen(accent, 1.7))
        painter.drawLine(12, 3, 12, 9)
        painter.drawLine(12, 15, 12, 21)
        painter.drawLine(3, 12, 9, 12)
        painter.drawLine(15, 12, 21, 12)
        painter.drawLine(6, 6, 9, 9)
        painter.drawLine(15, 15, 18, 18)
        painter.drawLine(18, 6, 15, 9)
        painter.drawLine(9, 15, 6, 18)

    elif n in {"institutional", "building"}:
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(4, 8),
                    QPointF(12, 4),
                    QPointF(20, 8),
                ]
            )
        )
        painter.drawLine(5, 9, 19, 9)
        for x in (7, 11, 15):
            painter.drawLine(x, 10, x, 18)
        painter.drawLine(4, 19, 20, 19)

    elif n in {"clean"}:
        path = QPainterPath()
        path.moveTo(5, 16)
        path.cubicTo(8, 7, 14, 5, 20, 5)
        path.cubicTo(18, 12, 14, 18, 5, 16)
        painter.drawPath(path)
        painter.drawLine(6, 16, 16, 8)

    elif n in {"premium", "crown"}:
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(4, 8),
                    QPointF(8, 13),
                    QPointF(12, 6),
                    QPointF(16, 13),
                    QPointF(20, 8),
                    QPointF(18.5, 18),
                    QPointF(5.5, 18),
                ]
            )
        )
        painter.drawLine(6, 15, 18, 15)

    elif n in {"highlights", "star"}:
        points = []
        import math
        for i in range(10):
            angle = -math.pi / 2 + i * math.pi / 5
            radius = 8 if i % 2 == 0 else 3.8
            points.append(
                QPointF(
                    12 + radius * math.cos(angle),
                    12 + radius * math.sin(angle),
                )
            )
        painter.drawPolygon(QPolygonF(points))

    elif n in {"captions", "cc"}:
        painter.drawRoundedRect(QRectF(3, 5, 18, 14), 3, 3)
        painter.setFont(painter.font())
        painter.drawText(QRectF(4, 5, 16, 14), Qt.AlignmentFlag.AlignCenter, "CC")

    elif n in {"zoom"}:
        painter.drawEllipse(QRectF(4, 4, 11, 11))
        painter.drawLine(13.5, 13.5, 20, 20)
        painter.drawLine(9.5, 6.5, 9.5, 12.5)
        painter.drawLine(6.5, 9.5, 12.5, 9.5)

    elif n in {"undo", "redo"}:
        if n == "undo":
            painter.drawArc(QRectF(6, 6, 13, 13), 35 * 16, 255 * 16)
            painter.drawLine(7, 6, 3.5, 9)
            painter.drawLine(7, 6, 8.5, 10)
        else:
            painter.drawArc(QRectF(5, 6, 13, 13), -110 * 16, 255 * 16)
            painter.drawLine(17, 6, 20.5, 9)
            painter.drawLine(17, 6, 15.5, 10)

    elif n in {"delete", "trash"}:
        painter.drawRoundedRect(QRectF(7, 8, 10, 12), 2, 2)
        painter.drawLine(5.5, 7, 18.5, 7)
        painter.drawLine(9, 4.5, 15, 4.5)
        painter.drawLine(10, 11, 10, 17)
        painter.drawLine(14, 11, 14, 17)

    elif n in {"restore"}:
        painter.drawArc(QRectF(4, 4, 16, 16), 20 * 16, 290 * 16)
        painter.drawLine(4.5, 6.5, 4.5, 12)
        painter.drawLine(4.5, 6.5, 10, 6.5)

    elif n in {"broll"}:
        painter.drawRoundedRect(QRectF(4, 6, 16, 12), 2, 2)
        painter.drawLine(8, 6, 8, 18)
        painter.drawLine(16, 6, 16, 18)
        painter.drawLine(4, 10, 8, 10)
        painter.drawLine(16, 14, 20, 14)

    elif n in {"check"}:
        painter.setPen(_pen(accent, 2.2))
        painter.drawLine(5, 12.5, 10, 17)
        painter.drawLine(10, 17, 19, 7)

    elif n in {"refresh"}:
        painter.drawArc(QRectF(4, 4, 16, 16), 40 * 16, 280 * 16)
        painter.drawLine(17, 4.8, 20, 5)
        painter.drawLine(20, 5, 19.2, 8)

    elif n in {"cloud", "cloud_play", "brand"}:
        path = QPainterPath()
        path.moveTo(6, 17.5)
        path.cubicTo(2, 17.5, 2, 11.5, 6.5, 11)
        path.cubicTo(7, 6.5, 13, 5.5, 15.5, 9)
        path.cubicTo(20.5, 8.5, 22, 15.5, 18, 17.5)
        path.closeSubpath()
        painter.setBrush(QColor(accent))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(path)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawPolygon(_triangle(12.5, 13, 5.5, 6.5))

    else:
        painter.drawEllipse(QRectF(5, 5, 14, 14))
        painter.drawLine(12, 8, 12, 14)
        painter.drawPoint(12, 17)

    painter.end()
    return QIcon(pixmap)


def icon_pixmap(name, color=DEFAULT_FG, accent=DEFAULT_ACCENT, size=24):
    return app_icon(name, color, accent, size).pixmap(QSize(size, size))
