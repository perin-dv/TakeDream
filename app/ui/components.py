from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui.icons import app_icon, icon_pixmap


def card(parent=None, object_name="Card"):
    frame = QFrame(parent)
    frame.setObjectName(object_name)
    return frame


def section_title(text, icon_name=None):
    if icon_name is None:
        label = QLabel(text)
        label.setObjectName("SectionTitle")
        return label

    frame = QWidget()
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(7)

    icon_label = QLabel()
    icon_label.setPixmap(
        icon_pixmap(
            icon_name,
            color="#EDE9FE",
            accent="#A855F7",
            size=18,
        )
    )
    title = QLabel(text)
    title.setObjectName("SectionTitle")

    layout.addWidget(icon_label)
    layout.addWidget(title)
    layout.addStretch(1)
    return frame


def muted_label(text, word_wrap=False):
    label = QLabel(text)
    label.setObjectName("Muted")
    label.setProperty("muted", True)
    label.setWordWrap(word_wrap)
    return label


class BrandWidget(QWidget):
    def __init__(self, compact=False, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        icon = QLabel()
        size = 36 if compact else 42
        icon.setFixedSize(size, size)
        icon.setPixmap(
            icon_pixmap(
                "brand",
                color="#FFFFFF",
                accent="#C056F7",
                size=size,
            )
        )
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        texts = QVBoxLayout()
        texts.setSpacing(0)

        brand = QLabel(
            '<span style="color:#FFFFFF;">Take</span>'
            '<span style="color:#C084FC;">Dream</span>'
        )
        brand.setTextFormat(Qt.TextFormat.RichText)
        brand.setStyleSheet(
            "font-family:'Segoe UI Variable','Segoe UI';"
            f"font-size:{20 if compact else 23}px;"
            "font-weight:800;"
        )

        tagline = QLabel("edição inteligente")
        tagline.setProperty("muted", True)
        tagline.setStyleSheet(
            "font-size:10px; font-weight:600; letter-spacing:.4px;"
        )

        texts.addWidget(brand)
        if not compact:
            texts.addWidget(tagline)

        layout.addWidget(icon)
        layout.addLayout(texts)
        layout.addStretch(1)


def nav_button(icon_name, text, *, active=False):
    button = QPushButton(text)
    button.setIcon(
        app_icon(
            icon_name,
            color="#D8DDF8",
            accent="#C084FC",
            size=19,
        )
    )
    button.setIconSize(QSize(19, 19))
    button.setProperty("nav", True)
    button.setProperty("navActive", active)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def option_button(text, *, checked=False, icon_name=None):
    button = QPushButton(text)
    if icon_name:
        button.setIcon(
            app_icon(
                icon_name,
                color="#EDE9FE",
                accent="#A855F7",
                size=18,
            )
        )
        button.setIconSize(QSize(18, 18))
    button.setCheckable(True)
    button.setChecked(checked)
    button.setProperty("tile", True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def quality_button(title, subtitle="", *, checked=False):
    text = title if not subtitle else f"{title}\n{subtitle}"
    button = QPushButton(text)
    button.setCheckable(True)
    button.setChecked(checked)
    button.setProperty("quality", True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


class ModernSwitch(QCheckBox):
    """QCheckBox-compatible switch with a custom modern visual."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(28)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

    def sizeHint(self):
        base = super().sizeHint()
        return QSize(max(base.width() + 20, 150), 30)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        enabled = self.isEnabled()
        checked = self.isChecked()

        track = QRectF(0, 4, 38, 20)
        track_color = (
            QColor("#8B5CF6")
            if checked
            else QColor("#35405F")
        )
        if not enabled:
            track_color.setAlpha(120)

        painter.setPen(
            QPen(
                QColor("#BDA8FF" if checked else "#53617F"),
                1,
            )
        )
        painter.setBrush(track_color)
        painter.drawRoundedRect(track, 10, 10)

        thumb_x = 21 if checked else 3
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(
            QColor("#FFFFFF" if enabled else "#9AA5C2")
        )
        painter.drawEllipse(QRectF(thumb_x, 7, 14, 14))

        painter.setPen(
            QColor("#F8FAFF" if enabled else "#7E88A7")
        )
        font = painter.font()
        font.setFamily("Segoe UI")
        font.setPointSize(9)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.drawText(
            QRectF(49, 0, max(0, self.width() - 49), 28),
            Qt.AlignmentFlag.AlignVCenter
            | Qt.AlignmentFlag.AlignLeft,
            self.text(),
        )


class SelectionCardButton(QAbstractButton):
    """Premium selectable card used for profile/style choices."""

    def __init__(
        self,
        title,
        subtitle,
        icon_name,
        *,
        accent="#8B5CF6",
        light=True,
        parent=None,
    ):
        super().__init__(parent)
        self.title = title
        self.subtitle = subtitle
        self.icon_name = icon_name
        self.accent = QColor(accent)
        self.light = light
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(104)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

    def sizeHint(self):
        return QSize(150, 108)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        selected = self.isChecked()
        hover = self.underMouse()
        enabled = self.isEnabled()

        if self.light:
            bg = QColor("#FFFFFF")
            hover_bg = QColor("#FBF9FF")
            text = QColor("#211B38")
            muted = QColor("#746D8A")
            border = QColor("#DDD8EB")
        else:
            bg = QColor("#171F3D")
            hover_bg = QColor("#1D2850")
            text = QColor("#F8FAFF")
            muted = QColor("#AAB3D5")
            border = QColor("#34416F")

        if selected:
            bg = QColor("#F7F1FF") if self.light else QColor("#2B1D63")
            border = self.accent
        elif hover:
            bg = hover_bg
            border = QColor("#A78BFA")

        if not enabled:
            bg.setAlpha(120)
            text.setAlpha(110)
            muted.setAlpha(95)

        p.setPen(QPen(border, 2 if selected else 1))
        p.setBrush(bg)
        p.drawRoundedRect(rect, 12, 12)

        icon_size = 30
        icon = icon_pixmap(
            self.icon_name,
            color="#34255A" if self.light else "#F4EEFF",
            accent=self.accent.name(),
            size=icon_size,
        )
        icon_x = (self.width() - icon_size) // 2
        p.drawPixmap(icon_x, 13, icon)

        if selected:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self.accent)
            p.drawEllipse(QRectF(self.width() - 26, 8, 18, 18))
            check = icon_pixmap(
                "check",
                color="#FFFFFF",
                accent="#FFFFFF",
                size=12,
            )
            p.drawPixmap(self.width() - 23, 11, check)

        title_font = p.font()
        title_font.setFamily("Segoe UI")
        title_font.setPointSize(9)
        title_font.setWeight(QFont.Weight.Bold)
        p.setFont(title_font)
        p.setPen(text)
        p.drawText(
            QRectF(8, 52, self.width() - 16, 22),
            Qt.AlignmentFlag.AlignCenter,
            self.title,
        )

        subtitle_font = p.font()
        subtitle_font.setPointSize(8)
        subtitle_font.setWeight(QFont.Weight.Normal)
        p.setFont(subtitle_font)
        p.setPen(muted)
        p.drawText(
            QRectF(8, 73, self.width() - 16, 25),
            Qt.AlignmentFlag.AlignHCenter
            | Qt.AlignmentFlag.AlignTop
            | Qt.TextFlag.TextWordWrap,
            self.subtitle,
        )


class AspectCardButton(QAbstractButton):
    def __init__(self, ratio, subtitle, parent=None):
        super().__init__(parent)
        self.ratio = ratio
        self.subtitle = subtitle
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(94)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

    def sizeHint(self):
        return QSize(150, 96)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        selected = self.isChecked()
        hover = self.underMouse()
        rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)

        bg = QColor("#FFFFFF")
        border = QColor("#DDD8EB")
        if hover:
            bg = QColor("#FBF9FF")
            border = QColor("#BFA6FF")
        if selected:
            bg = QColor("#F7F1FF")
            border = QColor("#8B5CF6")

        p.setPen(QPen(border, 2 if selected else 1))
        p.setBrush(bg)
        p.drawRoundedRect(rect, 12, 12)

        ratio_map = {
            "16:9": (42, 24),
            "9:16": (18, 32),
            "1:1": (29, 29),
            "4:5": (25, 31),
        }
        w, h = ratio_map.get(self.ratio, (35, 26))
        preview = QRectF(
            (self.width() - w) / 2,
            10,
            w,
            h,
        )
        p.setPen(QPen(QColor("#4C3B72"), 1.5))
        p.setBrush(QColor("#E9DDFE" if selected else "#EEF1FA"))
        p.drawRoundedRect(preview, 4, 4)

        font = p.font()
        font.setFamily("Segoe UI")
        font.setPointSize(9)
        font.setWeight(QFont.Weight.Bold)
        p.setFont(font)
        p.setPen(QColor("#211B38"))
        p.drawText(
            QRectF(6, 45, self.width() - 12, 20),
            Qt.AlignmentFlag.AlignCenter,
            self.ratio,
        )

        font.setPointSize(8)
        font.setWeight(QFont.Weight.Normal)
        p.setFont(font)
        p.setPen(QColor("#746D8A"))
        p.drawText(
            QRectF(8, 64, self.width() - 16, 24),
            Qt.AlignmentFlag.AlignHCenter
            | Qt.AlignmentFlag.AlignTop
            | Qt.TextFlag.TextWordWrap,
            self.subtitle,
        )

        if selected:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#8B5CF6"))
            p.drawEllipse(QRectF(self.width() - 25, 7, 17, 17))
            check = icon_pixmap(
                "check",
                color="#FFFFFF",
                accent="#FFFFFF",
                size=11,
            )
            p.drawPixmap(self.width() - 22, 10, check)


class QualityCardButton(QAbstractButton):
    def __init__(self, title, badge, subtitle, parent=None):
        super().__init__(parent)
        self.title = title
        self.badge = badge
        self.subtitle = subtitle
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(76, 78)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        selected = self.isChecked()
        hover = self.underMouse()
        rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)

        bg = QColor("#171F3D")
        border = QColor("#34416F")
        if hover:
            bg = QColor("#1F2A52")
            border = QColor("#6F62A7")
        if selected:
            bg = QColor("#2C1D67")
            border = QColor("#A56BFF")

        p.setPen(QPen(border, 2 if selected else 1))
        p.setBrush(bg)
        p.drawRoundedRect(rect, 11, 11)

        badge_rect = QRectF(
            self.width() / 2 - 18,
            8,
            36,
            18,
        )
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(
            QColor("#6D4FD6" if selected else "#27345E")
        )
        p.drawRoundedRect(badge_rect, 5, 5)

        font = p.font()
        font.setFamily("Segoe UI")
        font.setPointSize(7)
        font.setWeight(QFont.Weight.Bold)
        p.setFont(font)
        p.setPen(QColor("#F8FAFF"))
        p.drawText(
            badge_rect,
            Qt.AlignmentFlag.AlignCenter,
            self.badge,
        )

        font.setPointSize(9)
        font.setWeight(QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(
            QRectF(4, 31, self.width() - 8, 19),
            Qt.AlignmentFlag.AlignCenter,
            self.title,
        )

        font.setPointSize(7)
        font.setWeight(QFont.Weight.Normal)
        p.setFont(font)
        p.setPen(QColor("#AAB3D5"))
        p.drawText(
            QRectF(5, 50, self.width() - 10, 20),
            Qt.AlignmentFlag.AlignCenter,
            self.subtitle,
        )

        if selected:
            p.setBrush(QColor("#A855F7"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(self.width() - 20, 5, 14, 14))
            check = icon_pixmap(
                "check",
                color="#FFFFFF",
                accent="#FFFFFF",
                size=9,
            )
            p.drawPixmap(self.width() - 17, 8, check)


def info_row(title, subtitle, action_text=None, icon_name=None):
    frame = QFrame()
    frame.setObjectName("Card")
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(10)

    badge = QLabel()
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setFixedSize(32, 32)
    badge.setStyleSheet(
        "background:#2D215F; border-radius:8px;"
    )
    badge.setPixmap(
        icon_pixmap(
            icon_name or "sparkles",
            color="#F4EEFF",
            accent="#C084FC",
            size=18,
        )
    )

    texts = QVBoxLayout()
    texts.setSpacing(1)
    title_label = QLabel(title)
    title_label.setStyleSheet(
        "font-weight:700; color:#FFFFFF;"
    )
    subtitle_label = QLabel(subtitle)
    subtitle_label.setProperty("muted", True)
    subtitle_label.setWordWrap(True)

    texts.addWidget(title_label)
    texts.addWidget(subtitle_label)

    layout.addWidget(badge)
    layout.addLayout(texts, 1)

    button = None
    if action_text:
        button = QPushButton(action_text)
        button.setProperty("secondary", True)
        layout.addWidget(button)

    return frame, button
