from qtpy.QtCore import QSize
from qtpy.QtGui import QIcon, QColor, QBrush
from qtpy.QtWidgets import QListWidget, QListWidgetItem
from pathlib import Path
from magicgui.widgets import FunctionGui, Container
from napari.viewer import Viewer
import inspect
from napari.types import ImageData
from typing import Any, Callable
from napari.layers import Image
from napari.types import ImageData
from napari_topostats._widget_function import WidgetFunction, get_selected_image, ConfigWrapper
import numpy as np


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
        function_from_list = self.functions.get(item.text())
        if isinstance(function_from_list, WidgetFunction):
            widget = function_from_list.get_function_gui()
        elif isinstance(function_from_list, FunctionGui):
            widget = function_from_list
        else:
            print(f"Function {item.text()} is not a valid WidgetFunction or FunctionGui.")
            return
        if item.text() not in self.docked_functions:
            self.viewer.window.add_dock_widget(widget, name=item.text())
            self.docked_functions.append(item.text())
        if item.text() not in RUN_IMMEDIATELY_EXEMPTIONS:
            sig = inspect.signature(widget._function)
            kwargs = {}

            for name, param in sig.parameters.items():
                if param.annotation == ImageData:
                    selected = get_selected_image(self.viewer)
                    if selected is None:
                        print(f"No valid image data selected for {name}.")
                    else:
                        kwargs[name] = get_selected_image(self.viewer).data
                if param.annotation == Image:
                    selected = get_selected_image(self.viewer)
                    if selected is None:
                        print(f"No valid image layer selected for {name}.")
                    else:
                        kwargs[name] = get_selected_image(self.viewer)

                if param.annotation == Viewer:
                    kwargs[name] = self.viewer
            print(f"Running {widget._function.__name__} with parameters: {kwargs}")
            widget._function(**kwargs)

    


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

