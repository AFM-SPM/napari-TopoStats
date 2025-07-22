from qtpy.QtCore import QSize
from qtpy.QtGui import QIcon, QColor, QBrush
from qtpy.QtWidgets import QListWidget, QListWidgetItem
from pathlib import Path
from magicgui.widgets import FunctionGui
from napari.viewer import Viewer
import inspect
from napari.types import ImageData
import typing
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

class ButtonGrid(QListWidget):
    def __init__(self, parent=None, functions: dict[str, FunctionGui] = None, viewer: Viewer = None):
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

    
    def update_functions(self, functions: dict[str, FunctionGui]):
        self.functions = functions or {}
        self.remove_all_items()  # Clear existing items
        for label in functions or {}:
            self.addItem(label)
        self.itemClicked.connect(self.add_function_as_widget)

    def add_function_as_widget(self, item):
        """
        Handle the click event on a list item.
        """
        widget = self.functions.get(item.text())
        if item.text() not in self.viewer.window._dock_widgets:
            self.viewer.window.add_dock_widget(widget, name=item.text())
        if item.text() not in RUN_IMMEDIATELY_EXEMPTIONS:
            sig = inspect.signature(widget._function)
            kwargs = {}

            for name, param in sig.parameters.items():
                if param.annotation == ImageData:
                    selected = self.get_selected_image_data(self.viewer)
                    if selected is None:
                        print(f"No valid image data selected for {name}.")
                    else:
                        kwargs[name] = self.get_selected_image_data(self.viewer)
                if param.annotation == Viewer:
                    kwargs[name] = self.viewer
            widget._function(**kwargs)

    @staticmethod
    def get_selected_image_data(viewer) -> ImageData | None:
        selected = list(viewer.layers.selection)

        if not selected:
            print("No layer selected.")
            return None

        layer = selected[0]
        if isinstance(layer, Image):
            data = layer.data
            if isinstance(data, (np.ndarray, da.Array)):  # conforms to ImageData
                return data
            else:
                print("Layer data is not valid ImageData.")
        else:
            print("Selected layer is not an Image layer.")

        return None


    def addItem(self, label : str, tool_tip : str = None):
        if isinstance(label, QListWidgetItem):
            super().addItem(label)

        item = QListWidgetItem(QIcon(_get_icon(label)), label)
        self.item_mapping[label] = item
        item.setBackground(_get_background_brush())
        
        if tool_tip is not None:
            item.setToolTip(tool_tip)
        super().addItem(item)

    def addItems(self, labels) -> None:
        for label in labels:
            if hasattr(labels[label], "tool_tip"):
                self.addItem(label, labels[label].tool_tip)
            else:
                self.addItem(label)
    def remove_all_items(self):
        """
        Remove all items from the QListWidget and clear the item mapping.
        """
        self.clear()            # Clears all QListWidgetItems from the widget
        self.item_mapping.clear()  # Clear the dictionary tracking the items

