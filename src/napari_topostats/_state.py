"""
State management for napari-TopoStats.
This module contains global state variables used for the representation of the gui across the napari-TopoStats plugin.
It also contains utility functions for ensuring the validity of widgets used in the plugin.
"""

import contextlib

from magicgui.widgets import FunctionGui
from napari.viewer import Viewer
from qtpy.QtWidgets import QWidget

docked_widgets = []
topostats_widget = None
current_error_dialog = None
MIN_TOPOSTATS_VERSION = "2.4.0"  # Oldest compatible version of topostats, should match pyproject.toml
running_function = None  # Currently running function (None if no function is running)
widget_manager = None  # Global instance of WidgetManager

# Dictionary mapping channel names to their assigned colors (maintained between profile viewers)
channel_colours = {}
channel_colour_idx = 0

# Dictionary mapping analysis result names to their assigned colors (maintained between curve viewers)
analysis_result_colours = {}
analysis_result_colour_idx = 0

# Dictionary mapping curve segment names to their assigned colors (maintained between curve viewers)
curve_segment_colours = {}
curve_segment_colour_idx = 0

# Dictionary mapping loaded function names to their source python file path
loaded_function_paths = {}


def get_widget_manager():
    """Get the global widget manager instance."""
    return widget_manager


def set_widget_manager(manager):
    """Set the global widget manager instance."""
    global widget_manager  # pylint:disable=global-statement
    widget_manager = manager


class WidgetManager:
    """Class to manage the state of widgets in napari-TopoStats."""

    def __init__(self, viewer: Viewer):
        global widget_manager  # pylint:disable=global-statement
        self.viewer = viewer
        self.docked_widgets: dict[str, QWidget] = {}
        self.raw_docked_widgets: dict[str, QWidget] = {}

        # Dictionary mapping group names to lists of dock names in that group
        self.dock_groups: dict[str, list[str]] = {}
        # Dictionary mapping dock names to the group they belong to
        self.widget_groups: dict[str, str] = {}

        # Set the global widget manager instance to this instance
        widget_manager = self

    def add_docked_widget(self, widget, area="right", name=None, group=None):
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
        group : str, optional
            A named dock group to tabify this widget with, by default None.
        """
        self.ensure_valid(name)

        # Only add the new widget if there isn't already a valid and visible widget with the same name
        if name not in self.docked_widgets:
            dock = self.viewer.window.add_dock_widget(widget, area=area, name=name)

            # Create the references for the docked widget and its raw widget
            self.docked_widgets[name] = dock
            self.raw_docked_widgets[name] = widget

            # Keep lifecycle cleanup tied to this exact dock so a delayed signal cannot remove a same name replacement
            dock.destroyed.connect(
                lambda _=None, dock_name=name, expected=dock: self._dock_destroyed(dock_name, expected)
            )

            if group is not None:
                # Find an existing dock in the group to tabify with (we can't tabify with a dock that is being added)
                anchor = self._group_anchor(group, excluding=name)

                # Create the references for the dock's group
                self.dock_groups.setdefault(group, []).append(name)
                self.widget_groups[name] = group

                # If an anchor was found (this is not the first dock in the group), tabify the new dock with the anchor
                if anchor is not None:
                    # Add the new dock to the group, by tabifying it with an existing dock in the group
                    self.viewer.window._qt_window.tabifyDockWidget(anchor, dock)  # pylint: disable=protected-access

        return self.reveal_docked_widget(name)

    def reveal_docked_widget(self, name: str) -> QWidget | None:
        """Show and raise a tracked dock, returning it when it is valid."""
        self.ensure_valid(name)
        dock = self.docked_widgets.get(name)
        if dock is not None:
            dock.show()
            dock.raise_()
        return dock

    def _group_anchor(self, group: str, excluding: str | None = None):
        """
        Return any surviving dock in a group that can act as a tab anchor.

        This is required as a group is an arbitary concept and not part of the Qt docking system. We have to
        find a surviving dock to tabify new docks with.

        Parameters
        ----------
        group : str
            The name of the group to find an anchor for.
        excluding : str | None
            A dock name to exclude from consideration, by default None.
        """
        for name in list(self.dock_groups.get(group, [])):
            if name == excluding:
                continue
            self.ensure_valid(name)
            dock = self.docked_widgets.get(name)
            if dock is not None:
                return dock
        return None

    def _clear_widget_references(self, name: str):
        """Remove every manager reference associated with a dock name."""
        self.docked_widgets.pop(name, None)
        self.raw_docked_widgets.pop(name, None)
        group = self.widget_groups.pop(name, None)
        if group is not None:
            members = self.dock_groups.get(group, [])
            self.dock_groups[group] = [member for member in members if member != name]
            if not self.dock_groups[group]:
                self.dock_groups.pop(group)

    def _dock_destroyed(self, name: str, expected):
        """Clear references when Qt destroys a managed dock."""
        if self.docked_widgets.get(name) is expected:
            self._clear_widget_references(name)

    def ensure_valid(self, name: str):
        """
        Ensure that a widget with the same name is still valid.

        Parameters
        ----------
        name : str
            The name of the widget to ensure validity for.
        """
        # If a widget with the given name exists but is no longer valid, remove it from the manager
        if name in self.docked_widgets and not is_valid_widget(self.docked_widgets[name]):
            # Try to destroy the old widget if it still exists
            with contextlib.suppress(RuntimeError):
                self.docked_widgets[name].destroy()
            self._clear_widget_references(name)

    def get_widget(self, name: str, raw: bool = False):
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
        if raw:
            return self.raw_docked_widgets.get(name, None)
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
            self._clear_widget_references(name)


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


def add_colour_for_channel(channel_name: str, current_channels: list[str], palette: list[str]):
    """Add a colour for a specific channel"""
    global channel_colour_idx  # pylint:disable=global-statement
    if len(channel_colours) >= len(palette):
        for key in channel_colours:
            if key not in current_channels:
                channel_colours.pop(key)
                break
    channel_colours[channel_name] = palette[channel_colour_idx % len(palette)]
    channel_colour_idx += 1


def add_colour_for_analysis_result(result_name: str, current_results: list[str], palette: list[str]):
    """Add a colour for a specific analysis result"""
    global analysis_result_colour_idx  # pylint:disable=global-statement
    if len(analysis_result_colours) >= len(palette):
        for key in analysis_result_colours:
            if key not in current_results:
                analysis_result_colours.pop(key)
                break
    analysis_result_colours[result_name] = palette[analysis_result_colour_idx % len(palette)]
    analysis_result_colour_idx += 1


def add_colour_for_curve_segment(segment_name: str, current_segments: list[str], palette: list[str]):
    """Add a colour for a specific curve segment"""
    global curve_segment_colour_idx  # pylint:disable=global-statement
    if len(curve_segment_colours) >= len(palette):
        for key in curve_segment_colours:
            if key not in current_segments:
                curve_segment_colours.pop(key)
                break
    curve_segment_colours[segment_name] = palette[curve_segment_colour_idx % len(palette)]
    curve_segment_colour_idx += 1


def get_channel_colours() -> dict[str, str]:
    """Get the current channel colours"""
    return channel_colours


def get_analysis_result_colours() -> dict[str, str]:
    """Get the current analysis result colours"""
    return analysis_result_colours


def get_curve_segment_colours() -> dict[str, str]:
    """Get the current curve segment colours"""
    return curve_segment_colours


def record_loaded_function_path(func_name: str, file_path: str):
    """Record the source python file path for a dynamically loaded function."""
    loaded_function_paths[func_name] = file_path


def get_loaded_function_path(func_name: str) -> str | None:
    """Get the source python file path for a dynamically loaded function."""
    return loaded_function_paths.get(func_name)
