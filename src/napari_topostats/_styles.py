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
    QListWidget{
        min-width: 200;
        background: none;
        font-size: 14pt;
        margin: 0;
        padding: 0;
        color: #eee;
    }
    QListWidget::item {
        width: 80;
        height: 100;
        margin: 1;
        padding: 4;
    }
    QListWidget::item::hover {
        background: #8A929C;
        width: 80;
        height: 100;
        margin: 1;
        padding: 4;
    }

"""
