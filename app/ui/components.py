from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


def card(parent=None, object_name="Card"):
    frame = QFrame(parent)
    frame.setObjectName(object_name)
    return frame


def section_title(text):
    label = QLabel(text)
    label.setObjectName("SectionTitle")
    return label


def muted_label(text, word_wrap=False):
    label = QLabel(text)
    label.setObjectName("Muted")
    label.setProperty("muted", True)
    label.setWordWrap(word_wrap)
    return label


def nav_button(icon_text, text, *, active=False):
    button = QPushButton(f"{icon_text}   {text}")
    button.setProperty("nav", True)
    button.setProperty("navActive", active)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def option_button(text, *, checked=False):
    button = QPushButton(text)
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


def info_row(title, subtitle, action_text=None):
    frame = QFrame()
    frame.setObjectName("Card")
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(10)

    badge = QLabel(title[:1].upper())
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setFixedSize(30, 30)
    badge.setStyleSheet(
        "background:#2D215F; color:#E9D5FF; border-radius:8px; "
        "font-weight:800;"
    )

    texts = QVBoxLayout()
    texts.setSpacing(1)
    title_label = QLabel(title)
    title_label.setStyleSheet("font-weight:700; color:#FFFFFF;")
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
