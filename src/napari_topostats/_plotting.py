"""Module to add plotting functionality for viewing force curves"""

# pylint: disable=too-many-instance-attributes
import numpy as np
import pyqtgraph as pg
from qtpy.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget


def open_curve_viewer(viewer):
    """Return the curve viewer"""
    curve_viewer = CurveViewer(viewer)
    return curve_viewer


class CurveViewer(QWidget):
    """Custom docked widget for displaying force curves"""

    def __init__(self, viewer):
        super().__init__()
        self.viewer = viewer

        self.setLayout(QVBoxLayout())

        self.info_label = QLabel("Hold 'Shift' and click a pixel to view its force curve.")
        self.layout().addWidget(self.info_label)

        self.plot_widget = pg.PlotWidget(title="F-D curve")

        self.layout().addWidget(self.plot_widget)
        self.available_channels = []

        self.settings_widget = QWidget()
        self.settings_layout = QHBoxLayout(self.settings_widget)
        self.left_widget = QWidget()
        self.right_widget = QWidget()
        self.left_layout = QVBoxLayout(self.left_widget)
        self.right_layout = QVBoxLayout(self.right_widget)
        self.x_selector_label = QLabel("Select channel for X")
        self.y_selector_label = QLabel("Select channel for Y")
        self.x_channel_selector = QComboBox()
        self.y_channel_selector = QComboBox()
        self.x_channel_selector.currentTextChanged.connect(lambda text: self.update_channels(x_channel=text))
        self.y_channel_selector.currentTextChanged.connect(lambda text: self.update_channels(y_channel=text))

        self.left_layout.addWidget(self.x_selector_label)
        self.right_layout.addWidget(self.y_selector_label)
        self.left_layout.addWidget(self.x_channel_selector)
        self.right_layout.addWidget(self.y_channel_selector)

        self.show_approach = True
        self.show_retract = False

        self.approach_checkbox = QCheckBox("Show approach")
        self.retract_checkbox = QCheckBox("Show retract")
        self.approach_checkbox.setStyleSheet("color: yellow;")
        self.retract_checkbox.setStyleSheet("color: red;")
        self.approach_checkbox.setChecked(True)
        self.retract_checkbox.setChecked(False)
        self.approach_checkbox.toggled.connect(lambda checked: self.update_segments(approach=checked))
        self.retract_checkbox.toggled.connect(lambda checked: self.update_segments(retract=checked))
        self.left_layout.addWidget(self.approach_checkbox)
        self.right_layout.addWidget(self.retract_checkbox)

        self.settings_layout.addWidget(self.left_widget)
        self.settings_layout.addWidget(self.right_widget)
        self.layout().addWidget(self.settings_widget)

        self.x_coord = 0
        self.y_coord = 0

        self.x_channel = "measuredHeight"
        self.y_channel = "vDeflection"

        self.selected_curve_dict = None
        self.channels_units = None

        self.approach_line = self.plot_widget.plot([], [], pen="y", name="approach")
        self.retract_line = self.plot_widget.plot([], [], pen="r", name="retract")

        self.viewer.mouse_drag_callbacks.append(self.extract_curve)

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

        all_curve_data = layer.metadata["force_curves"]
        self.channels_units = layer.metadata["force_curves_units"]

        try:
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
