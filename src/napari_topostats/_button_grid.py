"""
This module defines the custom widget button grid which is responsible for rendering the correct image for
each function which is accessible from the root widget, as well as formatting and arranging those functions
and correctly linking the backend with those functions being clicked
"""

from contextlib import suppress
from pathlib import Path

from napari.viewer import Viewer
from qtpy.QtCore import QSize
from qtpy.QtGui import QBrush, QColor, QIcon
from qtpy.QtWidgets import QListWidget, QListWidgetItem

from napari_topostats._alerts import show_error_dialog
from napari_topostats._styles import BUTTON_GRID_STYLE
from napari_topostats._widget_function import WidgetFunction, WidgetFunctionManager

ICON_ROOT = Path(__file__).parent / "icons"


def _get_background_brush() -> QBrush:
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


def _get_icon(name: str) -> str:
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
        parent: QListWidget | None = None,
        functions: dict[str, WidgetFunction] | None = None,
        viewer: Viewer = None,
        function_manager: WidgetFunctionManager = None,
    ):
        super().__init__(parent=parent)
        # Set style and properties for the QListWidget
        self.setMovement(self.Static)  # The items cannot be moved by the user.
        self.setViewMode(self.IconMode)  # make items icons
        self.setResizeMode(self.Adjust)  # relayout when view is resized.
        self.setUniformItemSizes(True)  # better performance
        self.setIconSize(QSize(90, 40))  # set icon size
        self.setWordWrap(True)  # allow text to wrap
        self.setStyleSheet(BUTTON_GRID_STYLE)  # set the style sheet
        self.setSpacing(2)  # set spacing between items

        self.viewer = viewer
        self.function_manager = function_manager
        # Initialize the list of functions
        self.update_functions(functions)
        # List to keep track of docked functions
        self.docked_functions = {}

    def update_functions(self, functions: dict[str, WidgetFunction | list] | None):
        """
        Update the list of functions in the button grid.

        Parameters
        ----------
        functions : dict[str, WidgetFunction] | None
            A dictionary of function names and their corresponding WidgetFunction objects.
        """

        # Add the functions to the grid, including the tooltip if it exists.
        self.functions = functions or {}
        for label, function in functions.items():
            if function.tooltip:
                self.add_function_button(label, function.tooltip)
            else:
                self.add_function_button(label)

        # Remove any existing connections to the itemClicked signal to avoid duplicate connections
        with suppress(TypeError):
            self.itemClicked.disconnect()

        # Then add the new connection to the itemClicked signal (there is a single connection for the whole grid
        # which is passed the clicked item and determines which function to execute based on that item).
        self.itemClicked.connect(self.on_function_click)

    def on_function_click(self, item: QListWidgetItem):
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
        function = self.functions.get(item.text())
        if function is None:
            show_error_dialog(f"No function found for {item.text()}", raise_exception=True)
            return
        self.function_manager.add_function_as_widget(item.text(), function)

    def add_function_button(self, label: str | QListWidgetItem, tool_tip: str | None = None):
        """
        Add a button to the grid with the specified label and tooltip.

        Parameters
        ----------
        label : str | QListWidgetItem
            The label for the button. If a QListWidgetItem is provided, it will be used directly.
        tool_tip : str | None
            The tooltip for the button. If None, no tooltip will be set.
        """

        # If the label is already a QListWidgetItem, add it directly to the grid.
        if isinstance(label, QListWidgetItem):
            super().addItem(label)
            return

        # Otherwise, create a new QListWidgetItem with the specified label and get an icon where available
        item = QListWidgetItem(QIcon(_get_icon(label)), label)
        item.setBackground(_get_background_brush())

        if tool_tip is not None:
            item.setToolTip(tool_tip)

        # Add the item to the grid
        super().addItem(item)

    def remove_all_items(self):
        """
        Remove all items from the QListWidget.
        """
        self.clear()

    def add_function(self, widget_function: WidgetFunction, label: str):
        """Add a function button to the button grid"""
        self.functions[label] = widget_function
        self.add_function_button(label, tool_tip=widget_function.tooltip)
