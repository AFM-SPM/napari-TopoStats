from qtpy.QtCore import QSize
from qtpy.QtGui import QIcon, QColor, QBrush
from qtpy.QtWidgets import QListWidget, QListWidgetItem
from pathlib import Path
from magicgui.widgets import FunctionGui
from napari.viewer import Viewer
import inspect
from napari.types import ImageData
from typing import Any, Callable
from napari.layers import Image
from napari.types import ImageData
import numpy as np
import dask.array as da

RUN_IMMEDIATELY_EXEMPTIONS = {
    "Load Config"
}
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
    background_color = QColor()
    background_color.setNamedColor("#414851")
    background = QBrush(1)
    background.setColor(background_color)

    return background

def _get_highlight_brush():
    highlight_color = QColor()
    highlight_color.setNamedColor("#68707a")
    highlight = QBrush(1)
    highlight.setColor(highlight_color)

    return highlight


def _get_icon(name):
    path = ICON_ROOT / f'{name.lower().replace(" ", "_")}.png'
    if not path.exists():
        return ""
    return str(path)

# Class representation of each function in the button grid.
class WidgetFunction:
    def __init__(self, name: str, function_key: str | None = None, function_to_run: Callable | None = None, type_class: Any | None = None, path_to_data: str | None = None, uses_config: bool = False, ndims: int = 2, tooltip: str | None = None):
        
        self.name = name
        self.function_key = function_key
        if function_key is not None:
            self.function_key = function_key
            self.function_to_run = function_to_run
            self.type_class = type_class
            self.path_to_data = path_to_data
            self.uses_config = uses_config
            self.ndims = ndims
        self.tooltip = tooltip

    def set_function_gui(self, function_gui: FunctionGui):
        self.function_gui = function_gui

    def get_function_gui(self) -> FunctionGui:
        if hasattr(self, 'function_gui'):
            return self.function_gui
        else:
            raise AttributeError("Function GUI not set for this WidgetFunction instance.")

class ButtonGrid(QListWidget):
    def __init__(self, parent=None, functions: dict[str, WidgetFunction] | None = None, viewer: Viewer = None):
        super().__init__(parent=parent)
        self.setMovement(self.Static)  # The items cannot be moved by the user.
        self.setViewMode(self.IconMode)  # make items icons
        self.setResizeMode(self.Adjust)  # relayout when view is resized.
        self.setUniformItemSizes(True)  # better performance
        self.setIconSize(QSize(90, 40))
        self.setWordWrap(True)
        self.setStyleSheet(STYLES)
        self.setSpacing(2)
        self.item_mapping = {}
        self.viewer = viewer
        self.update_functions(functions)
        self.docked_functions = []

    def update_functions(self, functions: dict[str, WidgetFunction] | None):
        self.functions = functions or {}
        self.remove_all_items()  # Clear existing items
        for label, function in functions.items():
            if function.tooltip:
                self.addItem(label, function.tooltip)
            else:
                self.addItem(label)
        try:
            self.itemClicked.disconnect()
        except TypeError:
            pass
        self.itemClicked.connect(self.add_function_as_widget)

    def add_function_as_widget(self, item):
        """
        Handle the click event on a list item.
        """
        widget = self.functions.get(item.text()).get_function_gui()
        if item.text() not in self.docked_functions:
            self.viewer.window.add_dock_widget(widget, name=item.text())
            self.docked_functions.append(item.text())
        if item.text() not in RUN_IMMEDIATELY_EXEMPTIONS:
            sig = inspect.signature(widget._function)
            kwargs = {}

            for name, param in sig.parameters.items():
                if param.annotation == ImageData:
                    selected = self.get_selected_image(self.viewer)
                    if selected is None:
                        print(f"No valid image data selected for {name}.")
                    else:
                        kwargs[name] = self.get_selected_image(self.viewer).data
                if param.annotation == Image:
                    selected = self.get_selected_image(self.viewer)
                    if selected is None:
                        print(f"No valid image layer selected for {name}.")
                    else:
                        kwargs[name] = self.get_selected_image(self.viewer)

                if param.annotation == Viewer:
                    kwargs[name] = self.viewer
            print(f"Running {widget._function.__name__} with parameters: {kwargs}")
            widget._function(**kwargs)

    @staticmethod
    def get_selected_image(viewer) -> Image | None:
        selected = list(viewer.layers.selection)

        if not selected:
            print("No layer selected.")
            return None

        layer = selected[0]
        if isinstance(layer, Image):
            data = layer.data
            if isinstance(data, (np.ndarray, da.Array)):  # conforms to ImageData
                return layer
            else:
                print("Layer data is not valid ImageData.")
        else:
            print("Selected layer is not an Image layer.")

        return None


    def addItem(self, label : str, tool_tip: str | None = None):
        if isinstance(label, QListWidgetItem):
            super().addItem(label)

        item = QListWidgetItem(QIcon(_get_icon(label)), label)
        self.item_mapping[label] = item
        item.setBackground(_get_background_brush())
        
        if tool_tip is not None:
            item.setToolTip(tool_tip)
        super().addItem(item)

    def remove_all_items(self):
        """
        Remove all items from the QListWidget and clear the item mapping.
        """
        self.clear()            # Clears all QListWidgetItems from the widget
        self.item_mapping.clear()  # Clear the dictionary tracking the items

