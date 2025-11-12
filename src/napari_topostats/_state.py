"""
State management for napari-TopoStats.
This module contains global state variables used for the representation of the gui across the napari-TopoStats plugin.
"""

import importlib.metadata

docked_widgets = []
topostats_widget = None
current_error_dialog = None

MIN_TOPOSTATS_VERSION = "2.3.2"
TOPOSTATS_VERSION = importlib.metadata.version("topostats")
