"""Module to add plotting functionality for viewing force curves"""

# pylint: disable=too-many-instance-attributes, unused-argument, too-many-nested-blocks
# pylint: disable=too-many-branches, global-variable-not-assigned


import numpy as np
import pyqtgraph as pg
from napari import Viewer
from napari.layers import Shapes
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

from napari_topostats._components import (
    CollapsibleBox,
    MultiPlotWidget,
    SelectionDropdown,
    get_current_layer,
    get_selected_curves,
)
from napari_topostats._state import (
    WidgetManager,
    add_colour_for_channel,
    get_channel_colours,
    get_widget_manager,
)
from napari_topostats._styles import (
    COLOR_APPROACH,
    COLOR_PROFILE_LINE,
    COLOR_RETRACT,
    COLOR_SELECTED_CURVE,
    CURVE_VIEWER_MARGIN,
    CURVE_VIEWER_RIGHT_MARGIN,
    PROFILE_VIEWER_MARGIN,
    VIBRANT_PALETTE,
)
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
        self.layout().setContentsMargins(
            CURVE_VIEWER_MARGIN, CURVE_VIEWER_MARGIN, CURVE_VIEWER_RIGHT_MARGIN, CURVE_VIEWER_MARGIN
        )
        top_row_widget = QWidget()
        top_row_layout = QHBoxLayout(top_row_widget)
        top_row_layout.setContentsMargins(0, 0, 0, 0)

        # Create and add info label to the layout
        self.info_label = QLabel("Hold 'Shift' and click a pixel to view its force curve.")
        self.volume_selector = QComboBox()
        self.volume_selector.currentTextChanged.connect(self.update_volume)
        top_row_layout.addWidget(self.info_label)
        top_row_layout.addWidget(self.volume_selector)
        self.layout().addWidget(top_row_widget)

        # Create the graph area: a pg.GraphicsLayoutWidget() embedded in a horizontal layout
        plot_layout = QHBoxLayout()
        plot_layout.setContentsMargins(0, 0, 0, 0)
        self.plot_graphics_widget = pg.GraphicsLayoutWidget()
        self.plot_graphics_widget.setBackground(None)
        self.plot_graphics_widget.ci.layout.setContentsMargins(
            CURVE_VIEWER_MARGIN, CURVE_VIEWER_MARGIN, CURVE_VIEWER_RIGHT_MARGIN, CURVE_VIEWER_MARGIN
        )
        self.plot_widget = self.plot_graphics_widget.addPlot(title="Force Distance curve")
        plot_layout.addWidget(self.plot_graphics_widget)
        self.layout().addLayout(plot_layout)

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
        self.approach_checkbox.setStyleSheet(f"color: {COLOR_APPROACH};")
        self.retract_checkbox.setStyleSheet(f"color: {COLOR_RETRACT};")
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
            [], [], pen=COLOR_APPROACH, name="approach", available_channels=self.available_channels
        )
        self.retract_line = self.plot_widget.plot(
            [], [], pen=COLOR_RETRACT, name="retract", available_channels=self.available_channels
        )

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

    def update_curve(self, selected_curve_dict: dict = None):
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

    def update_volume(self, volume_name: str):
        """Updates the volume of the plot and refreshes curve to match"""
        selected_curves = get_selected_curves(self.viewer)
        self.update_curve(selected_curves.get_volume(volume_name)[self.y_coord, self.x_coord])

    def update_segments(self, approach: bool | None = None, retract: bool | None = None):
        """Updates the segments of the plot based on user checking boxes"""
        if approach is not None:
            self.show_approach = approach
        if retract is not None:
            self.show_retract = retract
        self.update_curve()

    def showEvent(self, event):
        """Register the mouse callback when the widget is shown."""
        if self.extract_curve not in self.viewer.mouse_drag_callbacks:
            self.viewer.mouse_drag_callbacks.append(self.extract_curve)
        super().showEvent(event)

    def hideEvent(self, event):
        """Clean up the mouse callback and selection cross layer when hidden/closed."""
        if self.extract_curve in self.viewer.mouse_drag_callbacks:
            self.viewer.mouse_drag_callbacks.remove(self.extract_curve)
        if "Selected Curve" in self.viewer.layers:
            self.viewer.layers.remove("Selected Curve")
        super().hideEvent(event)

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
        reader_id = layer.metadata.get("afmreader_id") if layer and layer.metadata else None
        loaded_image = get_loaded_image(reader_id) if reader_id is not None else None
        if loaded_image is None or loaded_image.curves_data is None:
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

        curves_data = loaded_image.curves_data
        raw_metadata = curves_data.metadata
        if self.volume_selector.currentText() not in curves_data.volumes:
            self.volume_selector.clear()
            self.volume_selector.addItems(curves_data.volumes.keys())
            self.volume_selector.setCurrentText(curves_data.get_default_volume().name)
        current_volume = (
            curves_data.get_volume(self.volume_selector.currentText())
            if self.volume_selector.currentText()
            else curves_data.get_default_volume()
        )
        self.channels_units = current_volume.channel_units
        try:
            self.metadata = {
                "global": raw_metadata.toplevel,
                f"curve_{curve_num}": raw_metadata[self.y_coord, self.x_coord],
                f"curve_{curve_num}_approach": raw_metadata[self.y_coord, self.x_coord, 0],
                f"curve_{curve_num}_retract": raw_metadata[self.y_coord, self.x_coord, 1],
            }
            if self.parameter_dialog is not None:
                self.parameter_dialog.populate_parameters(self.metadata)
            curve_dict = current_volume[self.y_coord, self.x_coord]
            self.set_available_channels(curve_dict.keys())
            self.update_curve(curve_dict)

            # Update the cross on the viewer at the selected pixel position
            selected_position = layer.data_to_world(coords)
            y_pos, x_pos = selected_position[-2:]
            y_scale, x_scale = np.abs(layer.scale[-2:])
            half_size = max(y_scale, x_scale) * 3
            cross_data = np.array(
                [
                    [[y_pos - half_size, x_pos - half_size], [y_pos + half_size, x_pos + half_size]],
                    [[y_pos - half_size, x_pos + half_size], [y_pos + half_size, x_pos - half_size]],
                ]
            )
            if "Selected Curve" in viewer.layers and not hasattr(viewer.layers["Selected Curve"], "edge_width"):
                viewer.layers.remove("Selected Curve")

            if "Selected Curve" not in viewer.layers:
                active_layer = viewer.layers.selection.active
                viewer.add_shapes(
                    data=cross_data,
                    name="Selected Curve",
                    shape_type="line",
                    edge_color=COLOR_SELECTED_CURVE,
                    edge_width=max(y_scale, x_scale) * 0.5,
                )
                if active_layer is not None:
                    viewer.layers.selection.active = active_layer
            else:
                selected_curve_layer = viewer.layers["Selected Curve"]
                selected_curve_layer.data = cross_data
                selected_curve_layer.edge_width = max(y_scale, x_scale) * 0.5
                selected_curve_layer.edge_color = COLOR_SELECTED_CURVE
        except IndexError:
            self.info_label.setText("Clicked outside the image bounds.")
        # pylint: disable=broad-exception-caught
        except Exception as e:  # noqa: BLE001
            self.info_label.setText(f"Error plotting curve: {str(e)}")

    def set_available_channels(self, available_channels: list):
        """
        Set the available channels for the curve plotter which updates the selector.

        Parameters
        ----------
        available_channels : list
            The list of available channels.
        """
        if self.available_channels == available_channels:
            return
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

    def __init__(self, viewer: Viewer, shapes_layer: Shapes = None, widget_manager: WidgetManager = None):
        super().__init__()
        self.viewer = viewer
        self.shapes_layer = shapes_layer
        self.widget_manager = widget_manager or get_widget_manager()

        # Get the currently active layer in the viewer to determine which image is being analyzed
        self.active_layer = get_current_layer(self.viewer)
        reader_id = (
            self.active_layer.metadata.get("afmreader_id") if self.active_layer and self.active_layer.metadata else None
        )
        self.loaded_image = get_loaded_image(reader_id) if reader_id is not None else None
        self.available_channels = self.loaded_image.get_available_channels() if self.loaded_image else []

        # Start and end points of the line profile (start as None to indicate no line drawn yet)
        self.start_point = None
        self.end_point = None

        # Flag to track if profile line events are connected to the shapes layer
        self.profile_line_events_connected = False

        # Setup the layout
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(
            PROFILE_VIEWER_MARGIN, PROFILE_VIEWER_MARGIN, PROFILE_VIEWER_MARGIN, PROFILE_VIEWER_MARGIN
        )

        # Attach info label above plot
        self.info_label = QLabel("Hold 'A' to draw a line profile.")
        self.layout().addWidget(self.info_label)

        # Plot widget for the profile
        self.plot_widget = MultiPlotWidget(title="Line Profile")
        self.layout().addWidget(self.plot_widget)

        # Create a settings widget to hold channel selector and label
        self.settings_widget = QWidget()
        self.settings_layout = QHBoxLayout(self.settings_widget)
        self.channel_displayed_label = QLabel("Selected channels: ")

        # Assign colours for the available channels (colours are defined in _styles.py and maintained in _state.py)
        self.assign_colours()

        # Create a channel selector dropdown to allow users to select which channels to display in the profile plot
        self.channel_selector = SelectionDropdown(
            items=self.available_channels,
            type_text="channels",
            on_change=self.update_profile_from_channels,
            starting_items=[self.loaded_image.get_current_channel()] if self.loaded_image else [],
            item_colors=get_channel_colours(),
        )

        # Add the settings widget to the main layout
        self.settings_layout.addWidget(self.channel_displayed_label)
        self.settings_layout.addWidget(self.channel_selector)
        self.layout().addWidget(self.settings_widget)

        # Whenever a new channel is selected, the profile widget should be updated
        viewer.layers.selection.events.changed.connect(self.on_selection_change)

    def assign_colours(self):
        """Assign colours to the channel selector and plot widget"""
        colours = get_channel_colours()
        for channel in self.available_channels:
            if channel not in colours:
                add_colour_for_channel(channel, self.available_channels, VIBRANT_PALETTE)

    def on_selection_change(self, event=None):
        """Called when the user changes the active layer to update the available channels"""
        temp_active = get_current_layer(self.viewer)

        # If the active layer hasn't actually changed, do nothing
        if temp_active == self.active_layer:
            return

        # Ignore selection changes to the drawing layer itself to prevent clearing loaded image context
        if temp_active is not None and temp_active.name == "Profile Line":
            return

        self.active_layer = temp_active
        if self.active_layer is not None:
            # Get the channel and image data associated with the newly selected layer
            reader_id = self.active_layer.metadata.get("afmreader_id") if self.active_layer.metadata else None
            self.loaded_image = get_loaded_image(reader_id) if reader_id is not None else None
            self.available_channels = self.loaded_image.get_available_channels() if self.loaded_image else []

            # Colours need to be updated for any new channels that have been added since the last selection change
            self.assign_colours()

            # Update the channel selector with the new available channels, starting with the current channel if possible
            self.channel_selector.set_items(
                self.available_channels,
                starting_items=[self.loaded_image.get_current_channel()] if self.loaded_image else [],
                item_colors=get_channel_colours(),
            )
        else:
            # If there is no active layer, clear the available channels and the channel selector
            self.available_channels = []
            self.channel_selector.set_items(self.available_channels)

    def connect_profile_line_events(self, shapes_layer: Shapes):
        """
        Connect profile line updates to a shapes layer once.

        Parameters
        ----------
        shapes_layer : Shapes
            The shapes layer to connect profile line updates to.
        """
        if self.profile_line_events_connected and self.shapes_layer is shapes_layer:
            return
        self.disconnect_profile_line_events()
        self.shapes_layer = shapes_layer
        self.profile_line_events_connected = True

        # Set data is triggered continously while the user is drawing
        shapes_layer.events.set_data.connect(self.on_line_changed)

        # Data is triggered when the user finishes drawing the line
        shapes_layer.events.data.connect(self.on_line_changed)

    def disconnect_profile_line_events(self):
        """Disconnect profile line events from the current shapes layer."""
        if not self.profile_line_events_connected:
            return
        self.shapes_layer.events.set_data.disconnect(self.on_line_changed)
        self.shapes_layer.events.data.disconnect(self.on_line_changed)
        self.profile_line_events_connected = False

    def on_line_changed(self, event=None):
        """
        Called when the shapes in the Profile Line layer change

        Parameters
        ----------
        event : Event
            The event that triggered the update; not used but required for the callback signature.
        """

        # If there is no shapes layer or if it has no data, reset the start and end points and return
        if self.shapes_layer is None or len(self.shapes_layer.data) == 0:
            self.start_point = None
            self.end_point = None
            return

        # Get the last line drawn
        line_coords = self.shapes_layer.data[-1]
        if len(line_coords) < 2:
            return

        self.start_point, self.end_point = line_coords[0], line_coords[1]
        self.update_profile_from_line()

    def update_profile_from_channels(self, selected_channels=None):
        """
        Update the profile plot based on the currently active layer and the line drawn in the shapes layer

        Parameters
        ----------
        selected_channels : list, optional
            The list of channels to plot. Not used but required for the callback signature of the channel selector.
        """

        # Get the pixel coordinates covered by the line drawn in the shapes layer
        self.update_profile_from_line()

        # Synchronize the channel selection dropdown with the lines currently plotted in the profile plot
        self.sync_channel_selection_to_visible_lines()

    def sync_channel_selection_to_visible_lines(self):
        """Keep dropdown channel selection consistent with the plotted lines."""
        channels_to_deselect = set(self.plot_widget.remove_unshown_lines())
        if channels_to_deselect:
            selected_channels = [
                channel for channel in self.channel_selector.get_checked_items() if channel not in channels_to_deselect
            ]
            self.channel_selector.set_checked_items(selected_channels)

        selected_channels = set(self.channel_selector.get_checked_items())
        for profile_unit, lines in list(self.plot_widget.get_profile_lines().items()):
            for channel in list(lines):
                if channel not in selected_channels:
                    self.plot_widget.remove_profile_line(channel, unit=profile_unit)

    def update_profile_from_line(self):
        """Update the profile plot based on the coordinates of the drawn line"""

        # If there is no active layer, no shapes layer, or the shapes layer has no data,
        # close the profile viewer and return.
        if self.active_layer is None or self.shapes_layer is None or len(self.shapes_layer.data) == 0:
            close_profile_viewer(self.viewer, self.shapes_layer, self.widget_manager)
            return
        if self.start_point is None or self.end_point is None:
            return

        # Get the pixel coordinates along the line drawn in the shapes layer
        row_coords, column_coords = self.get_pixel_coordinates()

        if self.loaded_image is not None:
            for channel in self.channel_selector.get_checked_items():
                # For each selected channel, retrieve the profile data
                values, px2nm, z_units = self.get_profile_data(channel, row_coords, column_coords)

                # Create the plot or update it if it already exists
                if values is not None:
                    self.plot_widget.plot(
                        channel,
                        np.array(np.arange(len(values))) * float(px2nm),
                        values,
                        unit=z_units,
                    )
            # Info label is updated to show the number of points in the profile
            self.info_label.setText(f"Profile: {len(row_coords)} points.")

        else:
            self.info_label.setText("Selected layer wasn't loaded with AFMReader, cannot extract profile.")

    def get_profile_data(
        self, channel: str, row_coords: np.ndarray, column_coords: np.ndarray
    ) -> tuple[np.ndarray | None, float, str]:
        """
        Retrieve the profile data for a given channel along the specified pixel coordinates

        Parameters
        ----------
        channel : str
            The name of the channel to retrieve the profile data for.
        row_coords : np.ndarray
            The row coordinates of the pixels along the line.
        column_coords : np.ndarray
            The column coordinates of the pixels along the line.

        Returns
        -------
        tuple[np.ndarray | None, float, str]
            A tuple containing the profile values (or None if empty), the pixel-to-nanometer
            conversion factor, and the z-axis units.
        """

        # Retrieve the loaded data, pixel-to-nanometer conversion factor, and z-axis units for the specified channel
        data, px2nm, z_units = self.loaded_image.get_map(channel)

        # Handle multi-dimensional data (take the last 2D slice if needed)
        if data.ndim > 2:
            slice_idx = tuple(self.viewer.dims.current_step[:-2])
            data_slice = data[slice_idx]
        else:
            data_slice = data

        height, width = data_slice.shape
        values = []

        # For each pixel coordinate along the line, retrieve the corresponding value from the data slice
        for r, c in zip(row_coords, column_coords, strict=False):
            if 0 <= r < height and 0 <= c < width:
                values.append(data_slice[r, c])

        if values:
            # Correct length units to be strictly in m
            if z_units == "nm":
                z_units = "m"
                values = np.array(values) * 1e-9
            elif z_units == "um":
                z_units = "m"
                values = np.array(values) * 1e-6
            elif z_units == "mm":
                z_units = "m"
                values = np.array(values) * 1e-3
            return values, px2nm, z_units

        # Values returned as None if empty
        return None, px2nm, z_units

    def get_pixel_coordinates(self) -> tuple[np.ndarray, np.ndarray]:
        """
        Return the pixel coordinates of the drawn line

        Returns
        -------
        tuple[np.ndarray, np.ndarray]
            A tuple containing the row and column coordinates of the pixels along the line.
        """

        # Convert the start and end points from data coordinates in the shapes layer to world coordinates
        start_point = self.shapes_layer.data_to_world(self.start_point)
        end_point = self.shapes_layer.data_to_world(self.end_point)

        # Then convert the world coordinates to data coordinates in the active layer
        start_point = self.active_layer.world_to_data(start_point)
        end_point = self.active_layer.world_to_data(end_point)

        # Start/end_point are (y, x) or (z, y, x) - take last two for 2D
        r0, c0 = np.round(start_point[-2:]).astype(int)
        r1, c1 = np.round(end_point[-2:]).astype(int)

        # Get all integer pixel coordinates along the line
        return line(r0, c0, r1, c1)


def close_profile_viewer(viewer: Viewer, shapes_layer: Shapes, widget_manager: WidgetManager):
    """Utility function to close the profile viewer and remove the shapes layer"""
    global profile_viewer  # pylint: disable=global-statement
    if profile_viewer is not None:
        profile_viewer.disconnect_profile_line_events()
    widget_manager.remove_docked_widget("Profile Viewer")
    profile_viewer = None
    if shapes_layer and "Profile Line" in viewer.layers:
        viewer.layers.remove(shapes_layer)


def start_drawing(viewer: Viewer):
    """
    Start the process of drawing a line on the viewer and updating the profile viewer with the line profile.
    This is a generator function that yields control back to napari to allow for interactive drawing.

    Parameters
    ----------
    viewer : napari.Viewer
        The napari viewer to attach the profile viewer to.
    """

    global profile_viewer  # pylint: disable=global-statement

    active_layer = get_current_layer(viewer)
    if active_layer is None:
        return

    # Keep a track of the previously active layer and its mode to restore later
    previous_active_layer = viewer.layers.selection.active
    previous_mode = previous_active_layer.mode if previous_active_layer else None

    # Use a size that is always one pixel on the active layer regardless of its scale
    y_scale, x_scale = np.abs(active_layer.scale[-2:])
    edge_width = max(y_scale, x_scale) * 1.0

    # Reuse or create the shapes layer for drawing the profile line to prevent OpenGL state corruption
    if "Profile Line" in viewer.layers:
        shapes_layer = viewer.layers["Profile Line"]
        shapes_layer.data = []
        shapes_layer.edge_width = edge_width
        shapes_layer.edge_color = COLOR_PROFILE_LINE
        current_index = viewer.layers.index(shapes_layer)
        if current_index < len(viewer.layers) - 1:
            viewer.layers.move(current_index, len(viewer.layers))
    else:
        shapes_layer = viewer.add_shapes(
            name="Profile Line",
            shape_type="line",
            edge_color=COLOR_PROFILE_LINE,
            edge_width=edge_width,
        )

    widget_manager = get_widget_manager()
    widget_manager.ensure_valid("Profile Viewer")

    if profile_viewer is None or "Profile Viewer" not in widget_manager.get_docked_widgets():
        profile_viewer = ProfileViewer(viewer, shapes_layer=shapes_layer, widget_manager=widget_manager)
        widget_manager.add_docked_widget(profile_viewer, area="right", name="Profile Viewer")
    profile_viewer.active_layer = active_layer
    profile_viewer.connect_profile_line_events(shapes_layer)

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
