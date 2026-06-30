"""Module for containing custom and reusable gui components"""

import dask.array as da
import numpy as np
import pyqtgraph as pg
from AFMReader.data_classes import CurvesDataset
from magicgui.widgets import Container, create_widget
from napari import Viewer
from napari.layers import Image, Labels
from napari_afmreader._reader import LoadedImage, get_loaded_image
from qtpy.QtCore import Qt
from qtpy.QtGui import QColor, QStandardItem, QStandardItemModel
from qtpy.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ._alerts import show_error_dialog
from ._state import get_channel_colours
from ._styles import PROFILE_VIEWER_MARGIN


class CollapsibleBox(QWidget):
    """
    A widget to contain over widgets in a collapsible area
    """

    def __init__(
        self, title: str = "", parent: QWidget | None = None, start_open: bool = False, cut_off_title: int = 0
    ):
        """
        Initializes the CollapsibleBox.

        Parameters
        ----------
        title : str, optional
            The title of the box, by default ""
        parent : QWidget, optional
            The parent widget, by default None
        start_open : bool, optional
            Whether the box should start open, by default False
        """
        super().__init__(parent)

        # Main layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Toggle Button (The Header)
        self.toggle_button = QPushButton(f"   {title}")
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(start_open)
        self.toggle_button.setStyleSheet(
            "QPushButton { text-align: left; font-weight: bold; padding: 0.5em; border: none; }"
            "QPushButton:hover { background-color: #555d68; }"
        )
        self.toggle_button.toggled.connect(self.on_toggle)
        self.layout.addWidget(self.toggle_button)

        # Content Area
        self.content_area = QFrame()
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(10, 10, 10, 10)
        self.layout.addWidget(self.content_area)

        self.widgets_dict = {}
        self.current_dict = {}

        self.cut_off_title = cut_off_title

        # Start at given state
        self.on_toggle(start_open)

    def on_toggle(self, checked: bool):
        """
        Set behaviour for expanding/ collapsing when clicked

        Parameters
        ----------
        checked : bool
            The state toggle has been changed to
        """
        self.content_area.setVisible(checked)
        arrow = "▼" if checked else "▶"
        self.toggle_button.setText(f"{arrow}  {self.toggle_button.text()[3:]}")

    def add_widget(self, widget: QWidget):
        """
        Adds the widget to the collapsable view

        Parameters
        ----------
        widget : QWidget
            The widget to add
        """
        self.content_layout.addWidget(widget)

    def add_parameter(self, name: str, value, editable: bool = False):
        """
        Adds a widget representing a given parameter to the collapsible box layout

        Parameters
        ----------
        name : str
            The name of the parameter
        value : any
            The value of the parameter
        editable : bool, optional
            Whether the parameter is editable, by default False
        """
        w = None
        # Update the current dict with the new value
        self.current_dict[name] = value
        if isinstance(value, dict):
            # If the value is a dict, create a new collapsible box for it
            w = CollapsibleBox(title=name.title().replace("_", " "))
            for k, v in value.items():
                # Use recursion to add parameters for the nested dict to the new collapsible box
                w.add_parameter(k, v)
            self.widgets_dict[name] = w
            # Add the new collapsible box widget to the layout
            self.add_widget(w)

        elif not editable:
            # Create a simple label for the parameter and add it to the layout
            w = QLabel(f"{name.title().replace('_', ' ')} : {value}")
            self.add_widget(w)
        else:
            # TODO a full editable selector based on the type of value
            pass

    def remove_parameter(self, key: str):
        """
        Removes a parameter from both the gui and its instance in this object

        Parameters
        ----------
        key : str
            The key of the parameter to remove
        """
        # Remove the widget from the layout and delete it
        self.layout.removeWidget(self.widgets_dict[key])
        self.widgets_dict[key].deleteLater()
        # Remove the parameter from the dictionaries
        self.widgets_dict.pop(key)
        self.current_dict.pop(key)

    def update(self, new_dict: dict):
        """
        Update the current dict that the collapsible box represents

        Parameters
        ----------
        new_dict : dict
            The new dict to update the collapsible box with
        """
        # If the new dict is the same as the current dict, do nothing
        if self.current_dict == new_dict:
            return
        # Remove any keys that are in the current dict but not in the new dict
        for key in self.current_dict.keys() - new_dict.keys():
            self.remove_parameter(key)
        # Update existing keys and add new keys
        for key, value in new_dict.items():
            # Update the widget if the key already exists
            if key in self.widgets_dict:
                # If the value is the same as the current value, do nothing
                if self.current_dict[key] == value:
                    continue
                # Update the current dict with the new value
                self.current_dict[key] = value
                if isinstance(value, dict):
                    # If the item in the dict to be updated is a dict itself, use recursion to update it
                    self.widgets_dict[key].update(value)
                else:
                    # If the item is not a dict, update the text of the corresponding widget
                    self.widgets_dict[key].setText(f"{key.title().replace('_', ' ')} : {value}")
            # Otherwise, add the new key and value as a new widget
            else:
                self.add_parameter(key, value)


class SelectionDialog(QDialog):
    """Selection dialog to allow so list of items to be given then return selected items"""

    def __init__(self, available_items, text="Select items", parent=None):
        """
        Initializes the selection dialog.

        Parameters
        ----------
        available_items : list
            The list of items to display in the selection dialog.
        text : str, optional
            The title of the selection dialog (default is "Select items").
        parent : QWidget, optional
            The parent widget of the dialog (default is None).
        """
        super().__init__(parent)
        self.setWindowTitle(text)
        self.resize(300, 400)  # Width, Height

        self.layout = QVBoxLayout()

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_widget.addItems(available_items)
        self.layout.addWidget(self.list_widget)

        # Helper buttons for quick selection
        self.helpers_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self.select_all)
        self.clear_btn = QPushButton("Clear Selection")
        self.clear_btn.clicked.connect(self.clear_selection)
        self.helpers_layout.addWidget(self.select_all_btn)
        self.helpers_layout.addWidget(self.clear_btn)
        self.layout.addLayout(self.helpers_layout)

        self.confirm_btn = QPushButton("Confirm")
        self.confirm_btn.clicked.connect(self.accept)
        self.layout.addWidget(self.confirm_btn)

        self.setLayout(self.layout)

    def select_all(self):
        """Select all items in the list widget."""
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setSelected(True)

    def clear_selection(self):
        """Deselect all items in the list widget."""
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setSelected(False)

    def get_selected_items(self):
        """Helper method to return the text of the selected items."""
        return [item.text() for item in self.list_widget.selectedItems()]


class SelectionDropdown(QComboBox):
    """A dropdown with checkable items to allow multiple selection"""

    def __init__(
        self,
        items: list,
        parent: QWidget = None,
        type_text: str = "items",
        starting_items: list = None,
        on_change: callable = None,
        item_colors: dict = None,
    ):
        """
        Initializes the SelectionDropdown.

        Parameters
        ----------
        items : list
            The list of items to display in the dropdown.
        parent : QWidget, optional
            The parent widget of the dropdown (default is None).
        type_text : str, optional
            The type of items being displayed (default is "items").
        starting_items : list, optional
            The list of items that should be initially checked (default is None).
        on_change : callable, optional
            A callback function to be called when the selection changes (default is None).
        item_colors : dict, optional
            A dictionary mapping items to their colors (default is None).
        """

        super().__init__(parent)
        self.selector_items = items
        self.type_text = type_text
        self.on_change = on_change
        starting_items = starting_items or []

        # Make it editable so we can display the selected text in the line edit
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setText(f"Loading {self.type_text}...")

        self.model = QStandardItemModel(self)
        self.setModel(self.model)

        # Add checkable items
        self.set_items(items, starting_items, item_colors)
        # Update the text when a box is checked/unchecked
        self.model.itemChanged.connect(self.on_selection_change)

    def set_items(self, items: list, starting_items: list = None, item_colors: dict = None):
        """
        Set the items in the dropdown and their checked state.

        Parameters
        ----------
        items : list
            The list of items to display in the dropdown.
        starting_items : list, optional
            The list of items that should be initially checked (default is None).
        block_signals : bool, optional
            Whether to block signals while setting items (default is False).
        """
        self.selector_items = items
        self.model.clear()
        starting_items = starting_items or []
        for text in items:
            item = QStandardItem(text)
            item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            item.setData(Qt.Checked if text in starting_items else Qt.Unchecked, Qt.CheckStateRole)
            if item_colors and text in item_colors:
                item.setForeground(QColor(item_colors[text]))
            self.model.appendRow(item)
        self.update_text()

    def on_selection_change(self):
        """
        Handle changes in selection and update the displayed text accordingly.
        """
        self.update_text()
        if self.on_change:
            self.on_change(self.get_checked_items())

    def update_text(self):
        """
        Update the text displayed in the line edit based on the current selection.
        """
        checked = self.get_checked_items()
        if len(self.selector_items) == 0:
            new_text = f"No {self.type_text} available"
        elif len(checked) == 0:
            new_text = f"No {self.type_text} selected"
        elif len(checked) < 4:
            new_text = f"{', '.join(checked)}"
        else:
            new_text = f"{len(checked)} {self.type_text} selected" if checked else f"No {self.type_text} selected"
        self.setCurrentIndex(-1)
        self.lineEdit().setText(new_text)

    def get_checked_items(self):
        """
        Return a list of the currently checked items.

        Returns
        -------
        list
            A list of the currently checked items.
        """
        return [
            self.model.item(i).text()
            for i in range(self.model.rowCount())
            if self.model.item(i).checkState() == Qt.Checked
        ]

    def set_checked_items(self, checked_items: list):
        """
        Manually set which items in the dropdown are checked.

        Parameters
        ----------
        checked_items : list
            The list of items that should be checked.
        """

        # Temporarily disable the on_change callback to avoid triggering it during updates
        temp_on_change = self.on_change
        self.on_change = None

        # Update the check state of each item based on the provided list
        for i in range(self.model.rowCount()):
            item = self.model.item(i)
            state = Qt.Checked if item.text() in checked_items else Qt.Unchecked
            item.setData(state, Qt.CheckStateRole)

        # Restore the on_change callback
        self.on_change = temp_on_change

        # Update the displayed text to reflect the new selection
        self.update_text()


class MultiPlotWidget(QWidget):
    """A widget to display multiple plots in a grid layout"""

    def __init__(self, title: str, parent=None):
        """Initializes the MultiPlotWidget."""
        super().__init__(parent=parent)
        self.setLayout(QHBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)

        # Set size policy to expanding to prevent the widget from collapsing in layouts
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Set a minimum height to ensure the plots are readable and don't flatten
        self.setMinimumHeight(200)

        # Create the main plot widget container
        self.graphics_widget = pg.GraphicsLayoutWidget()
        self.graphics_widget.setBackground(None)
        self.graphics_widget.ci.layout.setContentsMargins(
            PROFILE_VIEWER_MARGIN, PROFILE_VIEWER_MARGIN, PROFILE_VIEWER_MARGIN, PROFILE_VIEWER_MARGIN
        )
        self.layout().addWidget(self.graphics_widget)

        # Add the first plot
        self.p1: pg.PlotItem = self.graphics_widget.addPlot(title=title)

        # Create the secondary plot
        self.p2_view = pg.ViewBox()
        self.p2: pg.PlotItem = pg.PlotItem(viewBox=self.p2_view)

        # Add the secondary plot to the graph and link their axes
        self.p1.scene().addItem(self.p2_view)
        self.p1.showAxis("right")
        self.p1.getAxis("right").linkToView(self.p2_view)
        self.p2_view.setXLink(self.p1)
        self.p1.vb.sigResized.connect(self.update_views)

        # Initialize data structures to keep track of plotted lines and their data
        self.profile_lines: dict[str, dict[str, pg.PlotDataItem]] = {}
        self.current_unit = None
        self.previous_unit = None
        self.line_data: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = {}

    def update_views(self):
        """Forces the secondary ViewBox to match the primary's geometry."""
        self.p2_view.setGeometry(self.p1.vb.sceneBoundingRect())
        self.p2_view.linkedViewChanged(self.p1.vb, self.p2_view.XAxis)

    def reset_view(self):
        """Reset the primary and secondary profile plot axes to automatic scaling."""
        self.update_views()
        self.p1.vb.enableAutoRange(axis=self.p1.vb.XYAxes)
        self.p2_view.enableAutoRange(axis=self.p2_view.YAxis)

    def plot(self, channel: str, xdata: np.ndarray, ydata: np.ndarray, unit: str = "m"):
        """
        Plots the given data on the appropriate axis based on the unit.

        Parameters
        ----------
        xdata : np.ndarray
            The x-axis data.
        ydata : np.ndarray
            The y-axis data.
        channel : str
            The name of the channel.
        unit : str, optional
            The unit of the data, by default "m".
        """
        if unit not in self.profile_lines:
            self.profile_lines[unit] = {}

        line_key = (unit, channel)
        cached_data = self.line_data.get(line_key)

        # If the channel has not been plotted yet, create a new line for it
        if unit not in self.profile_lines or (channel not in self.profile_lines[unit]):
            self.profile_lines[unit][channel] = self.p1.plot(
                xdata, ydata, pen=get_channel_colours()[channel], name=channel, unit=unit
            )
            self.line_data[line_key] = (xdata, ydata)

            # Update the axis labels to reflect the current unit and channel
            self.p1.setLabel("left", channel, units=unit)

        # If the channel already exists, check if the data has changed before updating
        elif cached_data is None or not (
            np.array_equal(xdata, cached_data[0]) and np.array_equal(ydata, cached_data[1])
        ):
            self.profile_lines[unit][channel].setData(xdata, ydata)
            self.line_data[line_key] = (xdata, ydata)

        # If the data is the same, do nothing
        else:
            return

        # TODO does this need to be split into unit so it matches structure of profile_lines?
        if unit != self.current_unit:
            self.previous_unit = self.current_unit
            self.current_unit = unit
            if self.previous_unit and self.previous_unit in self.profile_lines:

                for line_channel in self.profile_lines[self.previous_unit]:
                    line_item = self.profile_lines[self.previous_unit][line_channel]
                    if line_item in self.p1.items:
                        self.p1.removeItem(line_item)
                    if line_item not in self.p2.items:
                        self.p2.addItem(line_item)
                    line_data = self.line_data[(self.previous_unit, line_channel)]
                    line_item.setData(line_data[0], line_data[1])
                self.p1.setLabel("right", "", units=self.previous_unit)

                for line_channel in self.profile_lines[self.current_unit]:
                    line_item = self.profile_lines[self.current_unit][line_channel]
                    if line_item in self.p2.items:
                        self.p2.removeItem(line_item)
                    if line_item not in self.p1.items:
                        self.p1.addItem(line_item)
                    line_data = self.line_data[(self.current_unit, line_channel)]
                    line_item.setData(line_data[0], line_data[1])

    def remove_unshown_lines(self):
        """Remove plotted profile lines that are not shown on either axis."""
        removed = []
        for profile_unit, lines in list(self.profile_lines.items()):
            if profile_unit not in [self.current_unit, self.previous_unit]:
                for line_channel, line_item in list(lines.items()):
                    if line_item in self.p1.items:
                        self.p1.removeItem(line_item)
                    if line_item in self.p2.items:
                        self.p2.removeItem(line_item)
                    lines.pop(line_channel, None)
                    self.line_data.pop((profile_unit, line_channel), None)
                    removed.append(line_channel)
                if not lines:
                    self.profile_lines.pop(profile_unit, None)
        return removed

    def get_profile_lines(self):
        """Returns the current profile lines."""
        return self.profile_lines

    def remove_profile_line(self, channel: str, unit: str):
        """Removes the profile line for the given channel."""
        if unit in self.profile_lines and channel in self.profile_lines[unit]:
            line_item = self.profile_lines[unit].pop(channel)
            if line_item in self.p2.items:
                self.p2.removeItem(line_item)
            if line_item in self.p1.items:
                self.p1.removeItem(line_item)
            self.line_data.pop((unit, channel), None)
            if not self.profile_lines[unit]:
                self.profile_lines.pop(unit, None)


# TODO: This function really gets currently selected layer not image
def get_selected_image(viewer, of_type: list = None) -> Image | None:
    """
    Get the currently selected image layer from the viewer.

    Parameters
    ----------
    viewer : Viewer
        The napari viewer instance from which to get the selected image layer.

    Returns
    -------
    Image | None
        The selected image layer, or None if no layer is selected.
    """
    selected = list(viewer.layers.selection)

    if not selected:
        show_error_dialog("No layer selected. Select a layer ")
        return None
    layer = selected[0]
    if of_type is not None and layer.__class__ not in of_type:
        pretty_types = [t.__name__ for t in of_type]
        show_error_dialog(
            f"Selected layer is not of a required type: {', '.join(pretty_types)}.",
            raise_exception=False,
        )
        return None
    if isinstance(layer, Image):
        data = layer.data
        if isinstance(data, (np.ndarray, da.Array)):  # conforms to ImageData
            return layer
        show_error_dialog("Layer data is not valid ImageData.", raise_exception=True)
    elif isinstance(layer, Labels):
        return layer
    return None


def get_selected_curves(viewer, suppress_errors=False) -> CurvesDataset | None:
    """
    Get the currently selected curves from the viewer.
    This retrieves the curves from the LoadedImage object associated with the selected layer.

    Parameters
    ----------
    viewer : Viewer
        The napari viewer instance from which to get the selected curves.

    Returns
    -------
    CurvesDataset | None
        The selected curves, or None if no layer is selected or if the selected layer does not have curves.
    """
    selected = list(viewer.layers.selection)

    if not selected:
        if not suppress_errors:
            show_error_dialog("No layer selected. Select a layer ")
        return None
    layer = selected[0]

    reader_id = layer.metadata.get("afmreader_id") if layer.metadata else None
    loaded_image = get_loaded_image(reader_id) if reader_id is not None else None
    if loaded_image is None or loaded_image.curves_data is None:
        if not suppress_errors:
            show_error_dialog("Selected layer does not contain curves", raise_exception=True)
        return None

    return loaded_image.curves_data


def get_current_layer(viewer, requires_force_curves=False):
    """Utility function to get the current active layer, excluding helper shapes layers"""

    def has_force_curves(layer):
        if not layer or not layer.metadata:
            return False
        reader_id = layer.metadata.get("afmreader_id")
        if reader_id is None:
            return False
        loaded_image = get_loaded_image(reader_id)
        return loaded_image is not None and loaded_image.curves_data is not None

    active = viewer.layers.selection.active
    if (
        active
        and active.name not in ("Profile Line", "Selected Curve")
        and (not requires_force_curves or has_force_curves(active))
    ):
        return active

    for layer in reversed(viewer.layers):
        if (
            layer.visible
            and layer.name not in ("Profile Line", "Selected Curve")
            and (not requires_force_curves or has_force_curves(layer))
        ):
            return layer
    return None


def get_selected_loaded_image(viewer: Viewer) -> LoadedImage:
    """
    Get the currently selected loaded image from the viewer.

    Returns
    -------
    LoadedImage | None
        The selected loaded image, or None if no layer is selected or if the selected layer is not a LoadedImage.
    """
    selected_layer = get_current_layer(viewer)
    loaded_image = get_loaded_image(selected_layer.metadata["afmreader_id"])
    if loaded_image is not None:
        return loaded_image
    show_error_dialog("Selected layer was not loaded throught napari-AFMReader", raise_exception=True)
    return None


class DynamicParameterDialog(QDialog):
    """A dialog that dynamically generates inputs based on parameters configuration using magicgui."""

    def __init__(self, parameters: dict, title: str = "Parameters", warning_message: str = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.layout = QVBoxLayout(self)

        if warning_message:
            warning_label = QLabel(warning_message)
            warning_label.setWordWrap(True)
            warning_label.setStyleSheet("font-weight: bold; color: #ffaa00; margin-bottom: 10px;")
            self.layout.addWidget(warning_label)

        self.container = Container()
        self.widgets = {}

        for param_name, config in parameters.items():
            param_type = config.get("type")
            default = config.get("default")
            label_text = config.get("label", param_name)

            if param_type is bool:
                w = create_widget(value=default, annotation=bool, label=label_text, name=param_name)
            elif isinstance(param_type, list):
                w = create_widget(value=default, options={"choices": param_type}, label=label_text, name=param_name)
            elif param_type is str:
                w = create_widget(value=default, annotation=str, label=label_text, name=param_name)
            else:
                continue

            self.container.append(w)
            self.widgets[param_name] = w

        self.layout.addWidget(self.container.native)

        # OK / Cancel Buttons
        button_layout = QHBoxLayout()
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(ok_button)
        self.layout.addLayout(button_layout)

    def get_values(self) -> dict:
        """
        Get the current values of all parameters.

        Returns
        -------
        dict
            Dictionary mapping parameter names to their current widget values.
        """
        return {name: w.value for name, w in self.widgets.items()}


def show_parameter_dialog(
    parameters: dict, title: str = "Parameters", warning_message: str = None, parent=None
) -> dict | None:
    """Helper function to show a DynamicParameterDialog and return values or None."""
    dialog = DynamicParameterDialog(parameters, title, warning_message, parent)
    if dialog.exec_() == QDialog.Accepted:
        return dialog.get_values()
    return None
