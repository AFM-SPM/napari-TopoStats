"""
State management for napari-TopoStats.
This module contains global state variables used for the representation of the gui across the napari-TopoStats plugin.
It also contains utility functions for ensuring the validity of widgets used in the plugin.
"""

from magicgui.widgets import FunctionGui
from qtpy.QtWidgets import QWidget

docked_widgets = []
topostats_widget = None
current_error_dialog = None
MIN_TOPOSTATS_VERSION = "2.4.0"  # Oldest compatible version of topostats, should match pyproject.toml
running_function = None  # Currently running function (None if no function is running)


def set_running_function(function_name: str | None):
    """
    Set the currently running function.

    Parameters
    ----------
    function_name : str | None
        The name of the function that is currently running, or None if no function is running.
    """
    # pylint: disable=global-statement
    global running_function
    running_function = function_name


def get_running_function() -> str | None:
    """
    Get the currently running function.

    Returns
    -------
    str | None
        The name of the function that is currently running, or None if no function is running.
    """
    return running_function


def is_valid_widget(widget: FunctionGui | QWidget) -> bool:
    """
    Check if widget's native Qt object exists.

    Parameters
    ----------
    widget : FunctionGui | QWidget
        The widget to check

    Returns
    -------
    bool
        True if widget is valid, False otherwise
    """
    try:
        if isinstance(widget, FunctionGui):
            if not hasattr(widget, "native"):
                return False
            # Try to access a property to check if C++ object still exists
            widget.native.isVisible()
        else:
            widget.isVisible()
        return True
    except RuntimeError:
        # C++ object has been deleted
        return False


def is_visible_widget(widget: FunctionGui | QWidget) -> bool:
    """
    Safely check if the widget is visible.

    Parameters
    ----------
    widget : FunctionGui | QWidget
        The widget to check

    Returns
    -------
    bool
        True if widget is visible, False otherwise
    """
    try:
        if isinstance(widget, FunctionGui):
            return widget.native.isVisible()
        return widget.isVisible()
    except RuntimeError:
        # C++ object has been deleted
        return False


def set_topostats_widget(widget):
    """Update the topostats widget"""
    global topostats_widget  # pylint:disable=global-statement
    topostats_widget = widget


def get_topostats_widget():
    """Get the topostats widget"""
    return topostats_widget
