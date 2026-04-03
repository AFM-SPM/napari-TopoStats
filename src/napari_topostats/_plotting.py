"""Module to add plotting functionality for viewing force curves"""

# pylint: disable=too-many-instance-attributes, unused-argument, too-many-nested-blocks
# pylint: disable=too-many-branches, global-variable-not-assigned


import numpy as np
import pyqtgraph as pg
from napari import Viewer
from napari_afmreader._reader import get_loaded_image
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
from skimage.draw import line  # pylint: disable=no-name-in-module

from napari_topostats._components import CollapsibleBox, MultiPlotWidget, SelectionDropdown, get_current_layer
from napari_topostats._state import WidgetManager, get_widget_manager
from napari_topostats.utils import unflatten_dict

profile_viewer = None


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
        self.approach_line = self.plot_widget.plot(
            [], [], pen="y", name="approach", available_channels=self.available_channels
        )
        self.retract_line = self.plot_widget.plot(
            [], [], pen="r", name="retract", available_channels=self.available_channels
        )

        # Setup the onclick event for so the curve viewer updates when the user clicks on a pixel
        self.viewer.mouse_drag_callbacks.append(self.extract_curve)

    def open_experimental_parameters(self):
        """Open the experimental parameters dialog"""
        if self.parameter_dialog is None:
            self.parameter_dialog = ParameterDialog(self.metadata)

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
        """Generator that runs when the user clicks and drags the mouse in the viewer."""
        if "Shift" not in event.modifiers:
            return

        # Trigger the initial plot on click
        self._process_event_coords(viewer, event)

        yield  # Yield control back to napari to wait for drag events

        while event.type == "mouse_move":
            # Optional: stop tracking if the user lets go of Shift while dragging
            if "Shift" not in event.modifiers:
                break

            # Trigger the plot update for the new coordinates
            self._process_event_coords(viewer, event)
            yield

    def _process_event_coords(self, viewer, event):
        """The core logic to extract and plot the curve at the current mouse position."""
        layer = viewer.layers.selection.active
        if layer is None or "force_curves" not in layer.metadata:
            self.info_label.setText("No force curves found in active layer.")
            return

        # Get click coordinates and convert to integers
        coords = np.round(layer.world_to_data(event.position)).astype(int)

        # Prevent redundant updates if the mouse moves but stays within the same integer pixel
        if coords[-2] == self.y_coord and coords[-1] == self.x_coord:
            return

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
                f"curve_{curve_num}": raw_metadata["curves"][self.y_coord][self.x_coord],
                f"curve_{curve_num}_approach": raw_metadata["segments"][self.y_coord][self.x_coord][0],
                f"curve_{curve_num}_retract": raw_metadata["segments"][self.y_coord][self.x_coord][1],
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


class ProfileViewer(QWidget):
    """Custom docked widget for displaying profiles along a line"""

    def __init__(self, viewer, shapes_layer=None, widget_manager=None):
        super().__init__()
        self.viewer = viewer
        self.shapes_layer = shapes_layer
        self.widget_manager = widget_manager or get_widget_manager()
        self.active = True

        # Setup the layout
        self.setLayout(QVBoxLayout())
        self.info_label = QLabel("Hold 'A' to draw a line profile.")
        self.layout().addWidget(self.info_label)

        self.settings_widget = QWidget()
        self.settings_layout = QHBoxLayout(self.settings_widget)
        self.channel_displayed_label = QLabel("Selected channels: ")
        self.active_layer = get_current_layer(self.viewer)
        self.loaded_image = get_loaded_image(self.active_layer.metadata.get("afmreader_id"))
        print(f"Loaded image: {self.loaded_image}")
        self.available_channels = self.loaded_image.get_available_channels() if self.loaded_image else []
        print(f"Available channels: {self.available_channels}")
        self.channel_selector = SelectionDropdown(
            items=self.available_channels,
            type_text="channels",
            on_change=self.update_profile_from_channels,
            starting_items=[self.loaded_image.get_current_channel()] if self.loaded_image else [],
        )
        self.settings_layout.addWidget(self.channel_displayed_label)
        self.settings_layout.addWidget(self.channel_selector)
        viewer.layers.selection.events.changed.connect(self.on_selection_change)

        # Plot widget for the profile
        self.plot_widget = MultiPlotWidget(title="Line Profile")

        self.layout().addWidget(self.plot_widget)
        self.layout().addWidget(self.settings_widget)

    def on_selection_change(self, event=None):
        """Called when the user changes the active layer to update the available channels"""
        temp_active = get_current_layer(self.viewer)
        print(f"Active layer changed: {temp_active}")
        if temp_active == self.active_layer:
            return
        self.active_layer = temp_active
        if self.active_layer is not None:
            self.loaded_image = get_loaded_image(self.active_layer.metadata.get("afmreader_id"))
            self.available_channels = self.loaded_image.get_available_channels() if self.loaded_image else []
            self.channel_selector.set_items(
                self.available_channels,
                starting_items=[self.loaded_image.get_current_channel()] if self.loaded_image else [],
            )
        else:
            self.available_channels = []
            self.channel_selector.set_items(self.available_channels)

    def on_line_changed(self, shapes_layer, event=None):
        """Called when the shapes in the Profile Line layer change"""
        print("Current channel: ", self.loaded_image.get_current_channel() if self.loaded_image else "None")

        self.shapes_layer = shapes_layer
        if shapes_layer is None or len(shapes_layer.data) == 0:
            return

        # Get the last line drawn
        line_coords = shapes_layer.data[-1]
        if len(line_coords) < 2:
            return

        start_point, end_point = line_coords[0], line_coords[1]
        self._update_profile_from_line(shapes_layer, start_point, end_point)

    def update_profile_from_channels(self, selected_channels=None):
        """Update the profile plot based on the currently active layer and the line drawn in the shapes layer"""
        shapes_layer = (
            self.shapes_layer
            if self.shapes_layer is not None
            else self.viewer.layers["Profile Line"] if "Profile Line" in self.viewer.layers else None  # noqa: SIM401
        )
        if shapes_layer is None:
            return

        self.on_line_changed(shapes_layer)

    def _update_profile_from_line(self, shapes_layer, start_point, end_point):
        """Update the profile plot based on the coordinates of the drawn line"""
        global colour_idx

        self.shapes_layer = shapes_layer
        # Get the top-most visible data layer
        self.active_layer = get_current_layer(self.viewer)

        if self.active_layer is None:
            close_profile_viewer(self.viewer, self.shapes_layer, self.widget_manager)
            return

        # Convert the start and end points from data coordinates in the shapes layer to world coordinates
        start_point = shapes_layer.data_to_world(start_point)
        end_point = shapes_layer.data_to_world(end_point)

        # Then convert the world coordinates to data coordinates in the active layer
        start_point = self.active_layer.world_to_data(start_point)
        end_point = self.active_layer.world_to_data(end_point)

        # Start/end_point are (y, x) or (z, y, x) - take last two for 2D
        r0, c0 = np.round(start_point[-2:]).astype(int)
        r1, c1 = np.round(end_point[-2:]).astype(int)

        # Get all integer pixel coordinates along the line
        rr, cc = line(r0, c0, r1, c1)

        if self.active_layer is not None:

            for channel in self.channel_selector.get_checked_items():

                data, _ = self.loaded_image.get_map(channel)
                # Handle multi-dimensional data (take the last 2D slice if needed)
                if data.ndim > 2:
                    slice_idx = tuple(self.viewer.dims.current_step[:-2])
                    data_slice = data[slice_idx]
                else:
                    data_slice = data

                h, w = data_slice.shape
                values = []
                for r, c in zip(rr, cc, strict=False):
                    if 0 <= r < h and 0 <= c < w:
                        values.append(data_slice[r, c])

                if values:
                    unit = "nm" if "height" in channel.lower() or "point" in channel.lower() else "N"
                    self.plot_widget.plot(
                        np.arange(len(values)), values, channel, available_channels=self.available_channels, unit=unit
                    )
                    self.info_label.setText(f"Profile: {len(values)} points.")

            for _, lines in self.plot_widget.get_profile_lines().items():
                for channel in lines:
                    if channel not in self.channel_selector.get_checked_items():
                        self.plot_widget.remove_profile_line(channel)


def close_profile_viewer(viewer: Viewer, shapes_layer, widget_manager: WidgetManager):
    """Utility function to close the profile viewer and remove the shapes layer"""
    global profile_viewer  # pylint: disable=global-statement
    widget_manager.remove_docked_widget("Profile Viewer")
    profile_viewer = None
    if shapes_layer and "Profile Line" in viewer.layers:
        viewer.layers.remove(shapes_layer)


def start_drawing(viewer):
    """
    Start the process of drawing a line on the viewer and updating the profile viewer with the line profile.
    This is a generator function that yields control back to napari to allow for interactive drawing.
    """

    global profile_viewer  # pylint: disable=global-statement

    active_layer = get_current_layer(viewer)
    if active_layer is None:
        return

    # Keep a track of the previously active layer and its mode to restore later
    previous_active_layer = viewer.layers.selection.active
    previous_mode = previous_active_layer.mode if previous_active_layer else None

    # Remove existing "Profile Line" layer if it exists to reset the tool
    if "Profile Line" in viewer.layers:
        viewer.layers.remove("Profile Line")

    # Add a new shapes layer for drawing the profile line
    shapes_layer = viewer.add_shapes(name="Profile Line", shape_type="line", edge_color="cyan", edge_width=1)
    widget_manager = get_widget_manager()
    widget_manager.ensure_valid("Profile Viewer")

    if profile_viewer is None or "Profile Viewer" not in widget_manager.get_docked_widgets():
        profile_viewer = ProfileViewer(viewer, shapes_layer=shapes_layer, widget_manager=widget_manager)
        widget_manager.add_docked_widget(profile_viewer, area="right", name="Profile Viewer")

    shapes_layer.events.set_data.connect(lambda event=None: profile_viewer.on_line_changed(shapes_layer, event))
    shapes_layer.events.data.connect(lambda event=None: profile_viewer.on_line_changed(shapes_layer, event))

    viewer.layers.selection.active = shapes_layer
    shapes_layer.mode = "add_line"

    # Wait for key release
    yield

    # Restore previous active layer and mode once key released
    viewer.layers.selection.active = previous_active_layer
    if previous_mode:
        shapes_layer.mode = previous_mode

    # Remove the shapes layer and profile viewer if no line is drawn
    if len(shapes_layer.data) == 0:
        close_profile_viewer(viewer, shapes_layer, widget_manager)


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
