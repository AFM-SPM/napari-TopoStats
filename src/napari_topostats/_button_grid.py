"""
This module defines the custom widget button grid which is responsible for rendering the correct image for
each function which is accessible from the root widget, as well as formatting and arranging those functions
and correctly linking the backend with those functions being clicked
"""

import inspect
from contextlib import suppress
from pathlib import Path

from magicgui.widgets import FunctionGui
from napari.viewer import Viewer
from qtpy.QtCore import QSize
from qtpy.QtGui import QBrush, QColor, QIcon
from qtpy.QtWidgets import QListWidget, QListWidgetItem

from napari_topostats._widget_function import (
    WidgetFunction,
    get_selected_image,
)

from ._alerts import show_error_dialog
from ._state import is_valid_widget, is_visible_widget

RUN_IMMEDIATELY_EXEMPTIONS = {}
ICON_ROOT = Path(__file__).parent / "icons"
STYLES = r"""
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


def _get_background_brush():
    """
    Sets the background colour for each button in the grid.

    Returns
    -------
    QBrush
        A QBrush object with the specified background color.
    """
    background_color = QColor()
    background_color.setNamedColor("#414851")
    background = QBrush(1)
    background.setColor(background_color)

    return background


def _get_icon(name):
    """
    Get the file path for the icon associated with a given function name.

    Parameters
    ----------
    name : str
        The name of the function for which to retrieve the icon.

    Returns
    -------
    str
        The file path to the icon image, or an empty string if the icon does not exist
    """
    path = ICON_ROOT / f'{name.lower().replace(" ", "_")}.png'
    if not path.exists():
        return ""
    return str(path)


class ButtonGrid(QListWidget):
    """
    A QListWidget that displays a grid of buttons, each representing a function.
    Each button can be clicked to execute the corresponding function, and open a docked widget in the viewer.
    """

    def __init__(
        self,
        parent=None,
        functions: dict[str, WidgetFunction] | None = None,
        viewer: Viewer = None,
    ):
        super().__init__(parent=parent)
        # Set style and properties for the QListWidget
        self.setMovement(self.Static)  # The items cannot be moved by the user.
        self.setViewMode(self.IconMode)  # make items icons
        self.setResizeMode(self.Adjust)  # relayout when view is resized.
        self.setUniformItemSizes(True)  # better performance
        self.setIconSize(QSize(90, 40))  # set icon size
        self.setWordWrap(True)  # allow text to wrap
        self.setStyleSheet(STYLES)  # set the style sheet
        self.setSpacing(2)  # set spacing between items

        self.viewer = viewer
        # Initialize the list of functions
        self.update_functions(functions)
        # List to keep track of docked functions
        self.docked_functions = {}

    def update_functions(self, functions: dict[str, WidgetFunction] | None):
        """
        Update the list of functions in the button grid.
        Parameters
        ----------
        functions : dict[str, WidgetFunction] | None
            A dictionary of function names and their corresponding WidgetFunction objects.
        """
        self.functions = functions or {}
        for label, function in functions.items():
            if function.tooltip:
                self.addFunctionButton(label, function.tooltip)
            else:
                self.addFunctionButton(label)
        with suppress(TypeError):
            self.itemClicked.disconnect()
        self.itemClicked.connect(self.add_function_as_widget)

    # pylint: disable=too-many-branches
    def add_function_as_widget(self, item):
        """
        Handle the click event on a list item.
        If the item corresponds to a WidgetFunction, it will be added as a docked widget
        in the viewer (if it is not already added). If the function is not in the RUN_IMMEDIATELY_EXEMPTIONS list,
        it will be executed with the appropriate parameters.
        Parameters
        ----------
        item : QListWidgetItem
            The item that was clicked.
        """

        if item.text() in self.docked_functions and (
            not is_valid_widget(self.docked_functions[item.text()])
            or not is_visible_widget(self.docked_functions[item.text()])
        ):
            # Try to destroy the old widget if it still exists
            try:
                if hasattr(self.docked_functions[item.text()], "native"):
                    self.docked_functions[item.text()].native.destroy()
            except RuntimeError:
                # Already deleted
                pass
            self.docked_functions.pop(item.text())

        # Check if the widget is already docked and add it if not
        if item.text() not in self.docked_functions:
            if self.functions[item.text()].overide_get_widget:
                func = self.functions[item.text()].function_to_run
                sig = inspect.signature(func)
                params = list(sig.parameters.values())
                if len(params) == 1 and params[0].name == "viewer":
                    widget = func(self.viewer)
                elif len(params) == 0:
                    widget = func()
                else:
                    show_error_dialog(
                        f"Function {item.text()} expected input when none was given.",
                        raise_exception=True,
                        topostats_error=True,
                    )
                # pylint: disable=used-before-assignment
                self.viewer.window.add_dock_widget(widget, name=item.text())
                self.docked_functions[item.text()] = widget
                return
            widget = self.get_widget_from_function(item.text())
            for param in widget:
                if param.name != "call_button":
                    self.viewer.window.add_dock_widget(widget, name=item.text())
                    self.docked_functions[item.text()] = widget
                    break

        widget = self.docked_functions[item.text()]
        if self.functions[item.text()].overide_get_widget:
            return

        if item.text() not in RUN_IMMEDIATELY_EXEMPTIONS:
            # If the function is not in the RUN_IMMEDIATELY_EXEMPTIONS list, run it with the appropriate parameters,
            # using the selected image layer as the image parameter
            if hasattr(widget, "image") and widget.image.value is None:
                selected_image = get_selected_image(self.viewer)
                if selected_image is not None:
                    widget.image.value = selected_image
            if hasattr(widget, "viewer"):
                widget.viewer.value = self.viewer
            widget()

    def get_widget_from_function(self, function_name: str) -> FunctionGui | None:
        """
        Get the widget representation of the passed function by selecting between generating it or returning the
        passed function if it is already a widget

        Parameters
        ----------
        function_name : str
            The name of the function to retrieve.

        Returns
        -------
        FunctionGui or None
            The widget for the function, or None if the function is not valid.
        """
        function_from_list = self.functions.get(function_name)
        if isinstance(function_from_list, WidgetFunction):
            # If the function is a WidgetFunction, get its GUI representation.
            widget = function_from_list.get_function_gui()
        else:
            show_error_dialog(
                f"Function {function_name} is not a valid WidgetFunction or FunctionGui.",
                raise_exception=True,
            )
            return None
        return widget

    def addFunctionButton(self, label: str, tool_tip: str | None = None):
        """
        Add a button to the grid with the specified label and tooltip.

        Parameters
        ----------
        label : str | QListWidgetItem
            The label for the button. If a QListWidgetItem is provided, it will be used directly.
        tool_tip : str | None
            The tooltip for the button. If None, no tooltip will be set."""
        if isinstance(label, QListWidgetItem):
            super().addItem(label)

        item = QListWidgetItem(QIcon(_get_icon(label)), label)
        item.setBackground(_get_background_brush())

        if tool_tip is not None:
            item.setToolTip(tool_tip)
        super().addItem(item)

    def remove_all_items(self):
        """
        Remove all items from the QListWidget.
        """
        self.clear()
