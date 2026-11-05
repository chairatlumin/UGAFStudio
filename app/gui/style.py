STYLE = """
* {
    font-family: "Segoe UI";
    font-size: 10pt;
}

QMainWindow, QWidget {
    background: #f3f6f9;
    color: #243442;
}

QMenuBar {
    background: #233447;
    color: #f7fafc;
    padding: 5px 8px;
}

QMenuBar::item {
    background: transparent;
    padding: 7px 12px;
    border-radius: 5px;
}

QMenuBar::item:selected {
    background: #344c62;
}

QMenu {
    background: #ffffff;
    color: #243442;
    border: 1px solid #d7e0e8;
    padding: 5px;
}

QMenu::item {
    padding: 7px 24px;
    border-radius: 4px;
}

QMenu::item:selected {
    background: #e5f4f1;
    color: #12695e;
}

QTabWidget::pane {
    background: #ffffff;
    border: 1px solid #d5dee7;
    border-radius: 7px;
    top: -1px;
}

QTabBar::tab {
    background: #e7edf2;
    color: #465968;
    border: 1px solid #d5dee7;
    border-bottom: 3px solid transparent;
    padding: 9px 14px;
    margin-right: 3px;
    min-height: 20px;
}

QTabBar::tab:hover {
    background: #f6f9fb;
    color: #173b50;
}

QTabBar::tab:selected {
    background: #ffffff;
    color: #11695f;
    border-bottom: 3px solid #168779;
    font-weight: 600;
}

QPushButton {
    background: #11796f;
    color: #ffffff;
    border: 1px solid #0d6a62;
    border-radius: 5px;
    padding: 7px 13px;
    min-height: 18px;
}

QPushButton:hover {
    background: #0e6c64;
}

QPushButton:pressed {
    background: #0a5c56;
}

QPushButton:disabled {
    background: #dce4e9;
    color: #768692;
    border-color: #dce4e9;
}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {
    background: #ffffff;
    color: #243442;
    border: 1px solid #cbd6df;
    border-radius: 5px;
    padding: 6px 8px;
    selection-background-color: #a9d9d1;
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #168779;
}

QTableWidget, QTreeWidget, QListWidget {
    background: #ffffff;
    color: #243442;
    alternate-background-color: #f5f8fa;
    border: 1px solid #d7e0e8;
    border-radius: 5px;
    gridline-color: #e8edf1;
    selection-background-color: #d7eeea;
    selection-color: #173b50;
}

QHeaderView::section {
    background: #edf2f6;
    color: #3c5262;
    border: none;
    border-bottom: 1px solid #d5dee7;
    padding: 8px 10px;
    font-weight: 600;
}

QStatusBar {
    background: #233447;
    color: #eaf1f6;
}

QToolTip {
    background: #233447;
    color: #ffffff;
    border: 1px solid #455e73;
    padding: 5px 7px;
}
"""
