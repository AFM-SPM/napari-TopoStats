"""
State management for napari-TopoStats.
This module contains global state variables used for the representation of the gui across the napari-TopoStats plugin.
It also contains utility functions for ensuring the validity of widgets used in the plugin.
"""

import contextlib

from magicgui.widgets import FunctionGui
from qtpy.QtWidgets import QWidget

docked_widgets = []
topostats_widget = None
current_error_dialog = None
MIN_TOPOSTATS_VERSION = "2.4.0"  # Oldest compatible version of topostats, should match pyproject.toml
running_function = None  # Currently running function (None if no function is running)
widget_manager = None  # Global instance of WidgetManager


def get_widget_manager():
    """Get the global widget manager instance."""
    return widget_manager


def set_widget_manager(manager):
    """Set the global widget manager instance."""
    global widget_manager  # pylint:disable=global-statement
    widget_manager = manager


class WidgetManager:
    """Class to manage the state of widgets in napari-TopoStats."""

    def __init__(self, viewer):
        global widget_manager  # pylint:disable=global-statement
        self.viewer = viewer
        self.docked_widgets = {}

        # Set the global widget manager instance to this instance
        widget_manager = self

    def add_docked_widget(self, widget, area="right", name=None):
        """
        Add a widget to the dock

        Parameters
        ----------
        widget : FunctionGui | QWidget
            The widget to add.
        area : str, optional
            The area to dock the widget in, by default "right".
        name : str, optional
            The name of the widget, by default None.
        """
        self.ensure_valid(name)

        # Only add the new widget if there isn't already a valid and visible widget with the same name
        if name not in self.docked_widgets:
            self.docked_widgets[name] = self.viewer.window.add_dock_widget(widget, area=area, name=name)
        return self.docked_widgets[name]

    def ensure_valid(self, name):
        """
        Ensure that if a widget with the same name already exists, it is valid and visible.
        If not, remove it from the docked widgets list.

        Parameters
        ----------
        name : str
            The name of the widget to ensure validity for.
        """
        # If a widget with the same name already exists and is not valid or visible, remove it before adding the new one
        if name in self.docked_widgets and (
            not is_valid_widget(self.docked_widgets[name]) or not is_visible_widget(self.docked_widgets[name])
        ):
            # Try to destroy the old widget if it still exists
            with contextlib.suppress(RuntimeError):
                if hasattr(self.docked_widgets[name], "native"):
                    self.docked_widgets[name].native.destroy()
                elif hasattr(self.docked_widgets[name], "destroy"):
                    self.docked_widgets[name].destroy()
            self.docked_widgets.pop(name)

    def record_docked_widget(self, widget, name):
        """
        Record a widget in the docked widgets list.

        Parameters
        ----------
        widget : FunctionGui | QWidget
            The widget to record.
        name : str
            The name of the widget.
        """
        self.docked_widgets[name] = widget

    def get_widget(self, name):
        """
        Get a widget by name.

        Parameters
        ----------
        name : str
            The name of the widget to get.

        Returns
        -------
        FunctionGui | QWidget | None
            The widget with the specified name, or None if no such widget exists.
        """
        return self.docked_widgets.get(name, None)

    def get_docked_widgets(self):
        """
        Get the list of currently docked widgets.

        Returns
        -------
        dict[str, FunctionGui | QWidget]
            A dictionary mapping widget names to their corresponding widgets.
        """
        return self.docked_widgets

    def remove_docked_widget(self, name):
        """
        Remove a widget from the docked widgets list.

        Parameters
        ----------
        name : str
            The name of the widget to remove.
        """
        if name in self.docked_widgets:
            # Try to destroy the widget if it still exists
            with contextlib.suppress(RuntimeError):
                self.viewer.window.remove_dock_widget(self.docked_widgets[name])
                # if hasattr(self.docked_widgets[name], "native"):
                #     self.docked_widgets[name].native.destroy()
                # elif hasattr(self.docked_widgets[name], "destroy"):
                #     self.docked_widgets[name].destroy()
            self.docked_widgets.pop(name)


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


# Dictionary mapping loaded function names to their source python file path
loaded_function_paths = {}


def record_loaded_function_path(func_name: str, file_path: str):
    """Record the source python file path for a dynamically loaded function."""
    loaded_function_paths[func_name] = file_path


def get_loaded_function_path(func_name: str) -> str | None:
    """Get the source python file path for a dynamically loaded function."""
    return loaded_function_paths.get(func_name)
