"""Module to add plotting functionality for viewing force curves"""

# pylint: disable=too-many-instance-attributes


import numpy as np
import pyqtgraph as pg
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from napari_topostats.utils import unflatten_dict

from ._components import CollapsibleBox


def open_curve_viewer(viewer):
    """
    Return the curve viewer

    Parameters
    ----------
    viewer : napari.Viewer
        The napari viewer to attach the curve viewer to.

    Returns
    -------
    CurveViewer
        The curve viewer instance.
    """
    curve_viewer = CurveViewer(viewer)
    return curve_viewer


class CurveViewer(QWidget):
    """Custom docked widget for displaying force curves"""

    # pylint: disable=too-many-statements
    def __init__(self, viewer):
        """
        Initialize the curve viewer and attach it to the napari viewer.

        Parameters
        ----------
        viewer : napari.Viewer
            The napari viewer to attach the curve viewer to.
        """
        super().__init__()
        self.viewer = viewer

        # Setup the layout to be arranged vertically
        self.setLayout(QVBoxLayout())

        # Create and add info label to the layout
        self.info_label = QLabel("Hold 'Shift' and click a pixel to view its force curve.")
        self.layout().addWidget(self.info_label)

        # Create and add the plot widget to the layout
        self.plot_widget = pg.PlotWidget(title="F-D curve")
        self.layout().addWidget(self.plot_widget)

        self.available_channels = []

        # Create a new settings widget to hold the channel selectors and segment checkboxes
        self.settings_widget = QWidget()
        self.settings_layout = QHBoxLayout(self.settings_widget)

        # Instantiate left and right widgets (containers) and their layouts for x and y settings
        self.left_widget = QWidget()
        self.right_widget = QWidget()
        self.left_layout = QVBoxLayout(self.left_widget)
        self.right_layout = QVBoxLayout(self.right_widget)

        # Create channel selector labels and combo boxes for x and y channels
        self.x_selector_label = QLabel("Select channel for X")
        self.y_selector_label = QLabel("Select channel for Y")
        self.x_channel_selector = QComboBox()
        self.y_channel_selector = QComboBox()

        # Call update_channels when the user selects a different channel from the dropdown
        self.x_channel_selector.currentTextChanged.connect(lambda text: self.update_channels(x_channel=text))
        self.y_channel_selector.currentTextChanged.connect(lambda text: self.update_channels(y_channel=text))

        # Add the channel selectors to the left and right layouts
        self.left_layout.addWidget(self.x_selector_label)
        self.right_layout.addWidget(self.y_selector_label)
        self.left_layout.addWidget(self.x_channel_selector)
        self.right_layout.addWidget(self.y_channel_selector)

        # Create checkboxes for showing approach and retract segments
        self.show_approach = True
        self.show_retract = False
        self.approach_checkbox = QCheckBox("Show approach")
        self.retract_checkbox = QCheckBox("Show retract")

        # Set different colors for the approach and retract checkboxes to match the curve colors
        self.approach_checkbox.setStyleSheet("color: yellow;")
        self.retract_checkbox.setStyleSheet("color: red;")
        self.approach_checkbox.setChecked(True)
        self.retract_checkbox.setChecked(False)

        # Make the approach and retract checkboxes update the plot when toggled
        self.approach_checkbox.toggled.connect(lambda checked: self.update_segments(approach=checked))
        self.retract_checkbox.toggled.connect(lambda checked: self.update_segments(retract=checked))

        # Add the segment checkboxes to the left and right layouts
        self.left_layout.addWidget(self.approach_checkbox)
        self.right_layout.addWidget(self.retract_checkbox)

        # Add the left and right widgets to the settings layout, then add the settings widget to the main layout
        self.settings_layout.addWidget(self.left_widget)
        self.settings_layout.addWidget(self.right_widget)
        self.layout().addWidget(self.settings_widget)

        self.parameter_dialog = None
        self.metadata = {}

        # Create and add the button to open the experimental parameters dialog
        self.open_dialog_button = QPushButton("View experimental parameters")
        self.open_dialog_button.clicked.connect(self.open_experimental_parameters)
        self.layout().addWidget(self.open_dialog_button)

        # Initialize coordinates, channels and dicts
        self.x_coord = 0
        self.y_coord = 0
        self.x_channel = "measuredHeight"
        self.y_channel = "vDeflection"
        self.selected_curve_dict = None
        self.channels_units = None

        # Create the plots with empty data for approach and retract segments
        self.approach_line = self.plot_widget.plot([], [], pen="y", name="approach")
        self.retract_line = self.plot_widget.plot([], [], pen="r", name="retract")

        # Setup the onclick event for so the curve viewer updates when the user clicks on a pixel
        self.viewer.mouse_drag_callbacks.append(self.extract_curve)

    def open_experimental_parameters(self):
        """Open the experimental parameters dialog"""
        if self.parameter_dialog is None:
            self.parameter_dialog = ParameterDialog(self.metadata)
        else:
            if not self.parameter_dialog.isVisible():
                try:
                    self.parameter_dialog.show()
                    self.parameter_dialog.raise_()
                    self.parameter_dialog.activateWindow()
                except RuntimeError:
                    self.parameter_dialog.deleteLater()
                    self.parameter_dialog = None
            self.parameter_dialog.populate_parameters(self.metadata)

    def update_curve(self, selected_curve_dict=None):
        """Updates the plot with the selected curve dict"""
        if selected_curve_dict:
            self.selected_curve_dict = selected_curve_dict
        if self.selected_curve_dict is None:
            return
        approach_x, approach_y, retract_x, retract_y = [], [], [], []
        if self.show_approach:
            approach_x = self.selected_curve_dict[self.x_channel]["Segment_0"]
            approach_y = self.selected_curve_dict[self.y_channel]["Segment_0"]
        if self.show_retract:
            retract_x = self.selected_curve_dict[self.x_channel]["Segment_1"]
            retract_y = self.selected_curve_dict[self.y_channel]["Segment_1"]
        self.approach_line.setData(approach_x, approach_y)
        self.retract_line.setData(retract_x, retract_y)
        self.info_label.setText(f"Plotting curve for pixel (x={self.x_coord}, y={self.y_coord}).")

    def update_channels(self, x_channel=None, y_channel=None):
        """Updates the channels of the plot and refreshes curve to match"""
        if x_channel:
            self.x_channel = x_channel
            unit = self.channels_units.get(self.x_channel, "m")
            self.plot_widget.setLabel("bottom", self.x_channel, units=unit)
        if y_channel:
            self.y_channel = y_channel
            unit = self.channels_units.get(self.y_channel, "N")
            self.plot_widget.setLabel("left", self.y_channel, units=unit)
        self.update_curve()

    def update_segments(self, approach: bool | None = None, retract: bool | None = None):
        """Updates the segments of the plot based on user checking boxes"""
        if approach is not None:
            self.show_approach = approach
        if retract is not None:
            self.show_retract = retract
        self.update_curve()

    def extract_curve(self, viewer, event):
        """This runs every time the user clicks the mouse in the viewer."""
        if "Shift" not in event.modifiers:
            return

        layer = viewer.layers.selection.active
        if layer is None or "force_curves" not in layer.metadata:
            self.info_label.setText("No force curves found in active layer.")
            return

        # Get click coordinates and convert to integers
        coords = np.round(event.position).astype(int)
        self.y_coord = coords[-2]
        self.x_coord = coords[-1]
        shape_x = layer.data.shape[-1]

        curve_num = shape_x * self.y_coord + self.x_coord

        all_curve_data = layer.metadata["force_curves"]
        self.channels_units = layer.metadata["force_curves_units"]
        raw_metadata = layer.metadata["force_curves_meta"]
        try:
            self.metadata = {
                "global": raw_metadata["top_level"],
                f"curve_{curve_num}": raw_metadata["curves"][curve_num],
                f"curve_{curve_num}_approach": raw_metadata["segments"][curve_num * 2],
                f"curve_{curve_num}_retract": raw_metadata["segments"][curve_num * 2 + 1],
            }
            if self.parameter_dialog is not None:
                self.parameter_dialog.populate_parameters(self.metadata)
            curve_dict = all_curve_data[self.y_coord][self.x_coord]
            self.set_available_channels(curve_dict.keys())
            self.update_curve(curve_dict)
        except IndexError:
            self.info_label.setText("Clicked outside the image bounds.")
        # pylint: disable=broad-exception-caught
        except Exception as e:  # noqa: BLE001
            self.info_label.setText(f"Error plotting curve: {str(e)}")

    def set_available_channels(self, available_channels: list):
        """Set the available channels for the curve plotter which updates the selector"""
        self.available_channels = available_channels
        temp_x_channel = self.x_channel
        temp_y_channel = self.y_channel
        self.x_channel_selector.clear()
        self.y_channel_selector.clear()
        self.x_channel_selector.addItems(self.available_channels)
        self.y_channel_selector.addItems(self.available_channels)
        if temp_x_channel in available_channels:
            self.x_channel_selector.setCurrentText(temp_x_channel)
        if temp_y_channel in available_channels:
            self.y_channel_selector.setCurrentText(temp_y_channel)


class ParameterDialog(QDialog):
    """Custom parameters dialog to show values for selected curves"""

    def __init__(self, metadata: dict = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Experimental Parameters")
        self.resize(500, 600)
        self.setLayout(QVBoxLayout())
        self.info_widget = CollapsibleBox(title="Experimental parameters", start_open=True)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.info_widget)
        if metadata is None:
            metadata = {}
        self.metadata = metadata
        self.populate_parameters(self.metadata)
        self.layout().addWidget(self.scroll_area)

    def populate_parameters(self, metadata):
        """Populate the parameters viewing dialog with the metadata"""
        self.metadata = metadata
        parameters_dict = unflatten_dict(self.metadata)
        self.info_widget.update(parameters_dict)


def _get_parameters_widget(dict_data: dict, title: str = "Parameters"):
    collapsible_box = CollapsibleBox(title=title)
    for key, value in dict_data.items():
        if isinstance(value, dict):
            w = _get_parameters_widget(value, title=key)
        else:
            w = QLabel(f"{key.title().replace('_', ' ')} : {value}")
        collapsible_box.add_widget(w)
    return collapsible_box
