"""Centralized module for design tokens, color palettes, and layout styles."""

# Image viewer shape overlay colors (e.g. selected pixel marker and profile line)
COLOR_SELECTED_CURVE = "#FFC107"
COLOR_PROFILE_LINE = "#FF7043"

# Widget layout margins
CURVE_VIEWER_MARGIN = 2
CURVE_VIEWER_RIGHT_MARGIN = 5
PROFILE_VIEWER_MARGIN = 2

SEGMENT_COLOURS = [
    "#87CEFA",
    "#1E90FF",
]

# Color palette for multi-channel plotting (MultiPlotWidget)
VIBRANT_PALETTE = [
    "#FF00FF",
    "#00FFFF",
    "#FFFF00",
    "#00FF00",
    "#FF8000",
    "#FF0000",
    "#0080FF",
    "#80FF00",
    "#FF0080",
]

BUTTON_GRID_STYLE = r"""
    QListWidget {
    min-width: 200px;
    background: none;
    font-size: 10pt;
    margin: 0px;
    padding: 0px;
    color: #eee;
    }
    QListWidget::item {
        height: 22px;
        margin: 1px;
        padding: 2px 4px;
    }
    QListWidget::item:hover {
        background: #8A929C;
    }

"""

ERROR_DIALOG_LABEL_STYLE = """
    QLabel {
        font-size: 13px;
        color: #333333;
        padding: 10px;
    }
"""

ERROR_DIALOG_BUTTON_STYLE = """
    QPushButton {
        background-color: #0078d4;
        color: white;
        border: none;
        border-radius: 4px;
        padding: 8px 16px;
        font-size: 13px;
    }
    QPushButton:hover {
        background-color: #106ebe;
    }
    QPushButton:pressed {
        background-color: #005a9e;
    }
"""

ERROR_DIALOG_STYLE = """
    QDialog {
        background-color: white;
    }
"""

STATUS_LABEL_STYLE = """
    QLabel {
        border: none;
        padding: 0px;
        margin: 0px;
    }
"""

STATUS_LABEL_HIDDEN_STYLE = """
    QLabel {
        font-size: 4px
    }
"""

STATUS_LABEL_VISIBLE_STYLE = """
    QLabel {
        font-size: 12px
    }
"""

CONFIG_OPTIONS_LABEL_STYLE = "font-size: 10px;"

LOADING_OVERLAY_STYLE = "background-color: rgba(0, 0, 0, 120);"

LOADING_CONTAINER_STYLE = """
    QWidget {
        background-color: rgba(40, 40, 40, 240);
        border-radius: 15px;
        padding: 30px;
    }
"""

LOADING_LABEL_STYLE = """
    QLabel {
        color: white;
        font-size: 18px;
        font-weight: bold;
        background-color: transparent;
    }
"""

COLLAPSIBLE_BOX_SUBTLE_BUTTON_STYLE = """
    QPushButton {
        text-align: left;
        font-weight: bold;
        padding: 0.15em 0;
        border: none;
        background: transparent;
    }
    QPushButton:hover {
        background: transparent;
        text-decoration: underline;
    }
"""

COLLAPSIBLE_BOX_BUTTON_STYLE = """
    QPushButton {
        text-align: left;
        font-weight: bold;
        padding: 0.5em;
        border: none;
    }
    QPushButton:hover {
        background-color: #555d68;
    }
"""

PARAMETER_WARNING_LABEL_STYLE = "font-weight: bold; color: #ffaa00; margin-bottom: 10px;"
