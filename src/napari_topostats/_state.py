"""
State management for napari-TopoStats.
This module contains global state variables used for the representation of the gui across the napari-TopoStats plugin.
It also contains utility functions for ensuring the validity of widgets used in the plugin.
"""

docked_widgets = []
topostats_widget = None
current_error_dialog = None
DELEATED = "DELEATED"
VISIBLE = "VISIBLE"
INVISIBLE = "INVISIBLE"
INVALID = "INVALID"
MIN_TOPOSTATS_VERSION = "2.3.2"  # The oldest compatible version of topostats for this plugin


def widget_valid_and_visible(widget):
    """
    Check if widget's native Qt object exists and is visible.

    Parameters
    ----------
    widget : FunctionGui
        The widget to check

    Returns
    -------
    bool
        True if widget is valid and visible, False otherwise
    """
    try:
        if not hasattr(widget, "native"):
            return INVALID
        # Try to access a property to check if C++ object still exists
        if widget.native.isVisible():
            return VISIBLE
        return INVISIBLE
    except RuntimeError:
        # C++ object has been deleted
        return DELEATED
