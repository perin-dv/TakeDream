COLORS = {
    "bg": "#0B1020",
    "panel": "#121932",
    "panel_alt": "#171F3D",
    "card": "#1B2344",
    "card_hover": "#222C55",
    "border": "#313D6A",
    "border_soft": "#263158",
    "text": "#F8F8FF",
    "muted": "#AAB2D8",
    "purple": "#8B5CF6",
    "purple_2": "#A855F7",
    "magenta": "#E879F9",
    "cyan": "#4CC9F0",
    "green": "#4FD1A5",
    "danger": "#FF6B81",
    "warning": "#F6C85F",
}


REVIEW_STYLESHEET = r"""
QMainWindow, QDialog, QWidget#Root, QWidget#AppPage {
    background: #0B1020;
    color: #F8F8FF;
    font-family: "Segoe UI";
    font-size: 12px;
}

QWidget {
    color: #F8F8FF;
    font-family: "Segoe UI";
}

QFrame#Sidebar {
    background: #0E1530;
    border-right: 1px solid #252F55;
}

QFrame#FantasyPromo {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 #24155B,
        stop:1 #3B1C70
    );
    border: 1px solid #7C5CE7;
    border-radius: 14px;
}

QFrame#HeroCard {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 #121B3C,
        stop:0.55 #18224B,
        stop:1 #2A1754
    );
    border: 1px solid #34416F;
    border-radius: 18px;
}

QFrame#SoftCard {
    background: #F7F5FF;
    border: 1px solid #DDD6FE;
    border-radius: 16px;
}

QFrame#SoftCard QLabel {
    color: #17152A;
}

QFrame#SoftCard QLabel[muted="true"] {
    color: #66647A;
}

QLabel#Brand {
    font-size: 24px;
    font-weight: 800;
    color: #FFFFFF;
}

QLabel#BrandAccent {
    color: #C084FC;
}

QLabel#Muted,
QLabel[muted="true"] {
    color: #AAB2D8;
}

QLabel#PageTitle {
    font-size: 24px;
    font-weight: 800;
    color: #FFFFFF;
}

QLabel#PageSubtitle {
    font-size: 12px;
    color: #AAB2D8;
}

QLabel#ProjectTitle {
    font-size: 18px;
    font-weight: 700;
    color: #FFFFFF;
}

QLabel#SectionTitle {
    font-size: 13px;
    font-weight: 700;
    color: #FFFFFF;
}

QFrame#Card,
QFrame#PlayerCard,
QFrame#TimelineCard,
QFrame#ExportCard {
    background: #141C39;
    border: 1px solid #2B3762;
    border-radius: 14px;
}

QFrame#Card:hover {
    border: 1px solid #46558A;
}

QPushButton {
    background: #1B2447;
    border: 1px solid #34416F;
    border-radius: 10px;
    padding: 8px 12px;
    color: #F8F8FF;
    font-weight: 600;
}

QPushButton:hover {
    background: #242F5D;
    border-color: #6D5DEB;
}

QPushButton:pressed {
    background: #2C3970;
}

QPushButton:disabled {
    color: #687197;
    background: #151C37;
    border-color: #252D4E;
}

QPushButton[primary="true"] {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #7C3AED,
        stop:0.55 #9D4EDD,
        stop:1 #C026D3
    );
    border: 1px solid #D8B4FE;
    color: white;
    font-weight: 800;
    padding: 11px 18px;
}

QPushButton[primary="true"]:hover {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #8B5CF6,
        stop:0.55 #A855F7,
        stop:1 #D946EF
    );
}

QPushButton[secondary="true"] {
    background: #171F3D;
    border: 1px solid #7C5CE7;
    color: #E9D5FF;
    font-weight: 700;
}

QPushButton[nav="true"] {
    text-align: left;
    padding: 10px 13px;
    border: none;
    border-radius: 10px;
    background: transparent;
    color: #C7CDED;
    font-size: 13px;
}

QPushButton[nav="true"]:hover {
    background: #171F3D;
    color: white;
}

QPushButton[navActive="true"] {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #7C3AED,
        stop:1 #9333EA
    );
    color: #FFFFFF;
    border: 1px solid #B794F4;
    font-weight: 800;
}

QPushButton[tile="true"] {
    min-height: 44px;
    padding: 7px 10px;
    background: #171F3D;
    border: 1px solid #34416F;
    border-radius: 10px;
}

QPushButton[tile="true"]:checked {
    background: #2A1F5D;
    border: 2px solid #9B6CFF;
    color: white;
}

QPushButton[quality="true"] {
    min-width: 82px;
    min-height: 50px;
    background: #171F3D;
    border: 1px solid #34416F;
    border-radius: 10px;
    font-weight: 700;
}

QPushButton[quality="true"]:checked {
    background: #2B1D63;
    border: 2px solid #A56BFF;
    color: white;
}

QComboBox,
QDoubleSpinBox,
QLineEdit {
    background: #171F3D;
    border: 1px solid #34416F;
    border-radius: 8px;
    padding: 7px 10px;
    color: #F8F8FF;
}

QComboBox:hover,
QDoubleSpinBox:hover,
QLineEdit:hover,
QLineEdit:focus {
    border-color: #7C5CE7;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox QAbstractItemView {
    background: #11182F;
    color: #F8F8FF;
    border: 1px solid #34416F;
    selection-background-color: #6D28D9;
}

QCheckBox {
    spacing: 9px;
    color: #F8F8FF;
    font-weight: 600;
}

QCheckBox::indicator {
    width: 36px;
    height: 20px;
    border-radius: 10px;
    background: #313957;
    border: 1px solid #465174;
}

QCheckBox::indicator:checked {
    background: #8B5CF6;
    border-color: #C4B5FD;
}

QSlider::groove:horizontal {
    height: 5px;
    background: #293252;
    border-radius: 2px;
}

QSlider::sub-page:horizontal {
    background: #8B5CF6;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    background: #FFFFFF;
    border: 2px solid #8B5CF6;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}

QProgressBar {
    border: 1px solid #2A345C;
    border-radius: 5px;
    background: #11182D;
    height: 8px;
    text-align: center;
    color: transparent;
}

QProgressBar::chunk {
    border-radius: 4px;
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #7C3AED,
        stop:1 #D946EF
    );
}

QScrollArea {
    border: none;
    background: transparent;
}

QScrollBar:horizontal {
    background: #10162A;
    height: 10px;
    border-radius: 5px;
}

QScrollBar::handle:horizontal {
    background: #4D5782;
    min-width: 30px;
    border-radius: 5px;
}

QListWidget,
QTreeWidget,
QTableWidget {
    background: #11182F;
    color: #F8F8FF;
    border: 1px solid #2B3762;
    border-radius: 10px;
    alternate-background-color: #141C39;
}

QMessageBox {
    background: #0B1020;
}

QMessageBox QLabel {
    color: #F8F8FF;
}

QToolTip {
    background: #141C39;
    color: #FFFFFF;
    border: 1px solid #7C5CE7;
    padding: 5px;
}
"""


APP_STYLESHEET = REVIEW_STYLESHEET


def apply_review_theme(widget):
    widget.setStyleSheet(APP_STYLESHEET)


def apply_app_theme(widget):
    widget.setStyleSheet(APP_STYLESHEET)
