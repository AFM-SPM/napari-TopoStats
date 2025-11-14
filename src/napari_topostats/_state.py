"""
State management for napari-TopoStats.
This module contains global state variables used for the representation of the gui across the napari-TopoStats plugin.
"""

docked_widgets = []
topostats_widget = None
current_error_dialog = None

MIN_TOPOSTATS_VERSION = (
    "2.3.2"  # The oldest compatible version of topostats for this plugin
)
# The most recent confirmed compatible version of topostats for this plugin.
# Update if a later version is confirmed as working.
MAX_TOPOSTATS_VERSION = "2.3.2"
