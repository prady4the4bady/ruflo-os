"""PRADY TRADER — Dark trading terminal theme (QSS)."""

DARK_THEME = """
QMainWindow, QWidget {
    background-color: #0b1118;
    color: #ecf3fb;
    font-family: "Aptos", "Bahnschrift", "Segoe UI", sans-serif;
    font-size: 13px;
}

QMainWindow {
    background-color: #0b1118;
}

#sidebar {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #101925,
        stop:0.55 #0c141d,
        stop:1 #081018);
    border-right: 1px solid #223142;
}

#brandMark {
    font-size: 11px;
    font-weight: 700;
    color: #7cf2d0;
}

#brandWord {
    font-size: 24px;
    font-weight: 700;
    color: #f7fbff;
}

#brandSubtitle {
    font-size: 12px;
    color: #94a8bc;
}

#sidebarSectionLabel {
    font-size: 10px;
    font-weight: 700;
    color: #6e8398;
}

#sidebarPanel {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #121b25,
        stop:1 #0e1620);
    border: 1px solid #223142;
    border-radius: 18px;
}

#sidebarStat {
    font-size: 12px;
    color: #99acc0;
}

#sidebarStatValue {
    font-size: 14px;
    font-weight: 700;
    color: #f2f7fc;
}

#sidebarTicker {
    font-size: 12px;
    color: #d6e3ef;
    padding: 2px 0;
}

#sidebarFooter {
    font-size: 10px;
    color: #62778d;
}

#navButton {
    background: transparent;
    color: #c8d6e4;
    border: 1px solid transparent;
    border-radius: 14px;
    padding: 12px 14px;
    text-align: left;
    font-size: 13px;
    font-weight: 600;
}

#navButton:hover {
    background-color: #142131;
    border: 1px solid #26394c;
    color: #f7fbff;
}

#navButton[checked="true"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #16313a,
        stop:1 #122631);
    border: 1px solid #2d4a57;
    color: #7cf2d0;
}

#contentShell {
    background: transparent;
}

#shellHero {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #121b26,
        stop:0.55 #0f1822,
        stop:1 #131d29);
    border: 1px solid #223142;
    border-radius: 24px;
}

#shellEyebrow {
    font-size: 11px;
    font-weight: 700;
    color: #7cf2d0;
}

#shellTitle {
    font-size: 32px;
    font-weight: 700;
    color: #f7fbff;
}

#shellSubtitle {
    font-size: 13px;
    color: #99aec2;
}

#shellChip {
    background-color: #162534;
    color: #f7fbff;
    border: 1px solid #2b4256;
    border-radius: 14px;
    padding: 6px 10px;
    font-size: 11px;
    font-weight: 700;
}

#stackShell {
    background: transparent;
    border: none;
}

#metricCard {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #121b25,
        stop:1 #0f1720);
    border: 1px solid #223142;
    border-radius: 18px;
}

#metricLabel {
    font-size: 11px;
    color: #8ea2b6;
}

#metricValue {
    font-size: 20px;
    font-weight: 700;
    color: #f4f8fc;
}

#metricDelta {
    font-size: 12px;
}

#separator {
    background-color: #223142;
    min-height: 1px;
    max-height: 1px;
}

#pageTitle {
    font-size: 26px;
    font-weight: 700;
    color: #f7fbff;
    padding: 6px 0 2px 0;
}

#sectionHeader {
    font-size: 11px;
    font-weight: 700;
    color: #7cf2d0;
    padding: 14px 0 2px 0;
}

#statusBannerOk {
    background: #0f241e;
    border: 1px solid #256858;
    border-radius: 12px;
    color: #9af7de;
    font-size: 12px;
    font-weight: 700;
    padding: 10px 12px;
}

#statusBannerWarn {
    background: #2a190d;
    border: 1px solid #7f5c2c;
    border-radius: 12px;
    color: #ffd890;
    font-size: 12px;
    font-weight: 700;
    padding: 10px 12px;
}

QTableWidget {
    background-color: #111923;
    border: 1px solid #223142;
    border-radius: 12px;
    gridline-color: #162331;
    color: #d4e2ee;
    selection-background-color: #1d3440;
    selection-color: #7cf2d0;
}

QTextEdit, QTextBrowser {
    background-color: #111923;
    border: 1px solid #223142;
    border-radius: 12px;
    color: #d4e2ee;
    padding: 8px;
}

QTableWidget::item {
    padding: 6px 8px;
}

QHeaderView::section {
    background-color: #16212e;
    color: #8ea2b6;
    border: none;
    padding: 8px;
    font-weight: 700;
    font-size: 11px;
}

QScrollBar:vertical {
    background: #0b1118;
    width: 10px;
}

QScrollBar::handle:vertical {
    background: #2a3e53;
    border-radius: 5px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background: #39516a;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background: #0b1118;
    height: 10px;
}

QScrollBar::handle:horizontal {
    background: #2a3e53;
    border-radius: 5px;
    min-width: 30px;
}

QPushButton {
    background-color: #162230;
    color: #d4e2ee;
    border: 1px solid #27394a;
    border-radius: 10px;
    padding: 9px 16px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #1c2b3c;
    color: #f4f8fc;
}

QPushButton:pressed {
    background-color: #23384d;
}

#killButton {
    background-color: #5b201f;
    color: #fff4f4;
    border: 1px solid #c74d46;
    border-radius: 12px;
    padding: 14px 28px;
    font-size: 15px;
    font-weight: 700;
}

#killButton:hover {
    background-color: #73302d;
}

#successButton {
    background-color: #11342d;
    color: #7cf2d0;
    border: 1px solid #2b7d67;
}

#successButton:hover {
    background-color: #164238;
}

#warningButton {
    background-color: #3a2b13;
    color: #ffd27a;
    border: 1px solid #8b6b2a;
}

#warningButton:hover {
    background-color: #463418;
}

#dangerButton {
    background-color: #3f1c1d;
    color: #ffb4ae;
    border: 1px solid #a7484d;
}

#dangerButton:hover {
    background-color: #4d2224;
}

QGroupBox {
    border: 1px solid #223142;
    border-radius: 16px;
    margin-top: 14px;
    padding-top: 14px;
    font-weight: 700;
}

QGroupBox::title {
    subcontrol-origin: margin;
    padding: 0 6px;
    color: #7cf2d0;
}

QTextBrowser, QTextEdit, QPlainTextEdit {
    background-color: #111923;
    color: #d4e2ee;
    border: 1px solid #223142;
    border-radius: 12px;
    padding: 8px;
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 12px;
}

QStatusBar {
    background-color: #0e1620;
    color: #8da1b6;
    border-top: 1px solid #223142;
    font-size: 12px;
    padding: 3px 10px;
}

QScrollArea {
    border: none;
    background: transparent;
}

QScrollArea > QWidget > QWidget {
    background: transparent;
}

#statusBannerOk {
    background-color: #14322d;
    color: #7cf2d0;
    border: 1px solid #245549;
    border-radius: 12px;
    padding: 10px 12px;
    font-size: 13px;
    font-weight: 700;
}

#statusBannerWarn {
    background-color: #3a2d16;
    color: #ffd27a;
    border: 1px solid #7f6530;
    border-radius: 12px;
    padding: 10px 12px;
    font-size: 13px;
    font-weight: 600;
}
"""
