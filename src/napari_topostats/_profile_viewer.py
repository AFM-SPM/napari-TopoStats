"""Module to add plotting functionality for viewing force curves"""

from typing import Any

# pylint: disable=too-many-instance-attributes, unused-argument, too-many-nested-blocks
# pylint: disable=too-many-branches
import numpy as np
from napari import Viewer
from napari.layers import Shapes
from napari_afmreader._reader import get_loaded_image
from qtpy.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from skimage.draw import line  # pylint: disable=no-name-in-module

from napari_topostats._components import (
    CollapsibleBox,
    MultiPlotWidget,
    SelectionDropdown,
    get_current_layer,
)
from napari_topostats._state import (
    WidgetManager,
    add_colour_for_channel,
    get_channel_colours,
    get_widget_manager,
)
from napari_topostats._styles import (
    COLOR_PROFILE_LINE,
    PROFILE_VIEWER_MARGIN,
    VIBRANT_PALETTE,
)

profile_viewer = None


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
        self.reset_view_button = QPushButton("Reset view")
        self.reset_view_button.setToolTip("Reset profile plot axes")
        self.reset_view_button.setFixedWidth(self.reset_view_button.sizeHint().width())
        self.reset_view_button.clicked.connect(self.plot_widget.reset_view)
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

        # Add the settings widget to a collapsible section at the bottom of the viewer
        self.settings_layout.addWidget(self.reset_view_button)
        self.settings_layout.addWidget(self.channel_displayed_label)
        self.settings_layout.addWidget(self.channel_selector)
        self.settings_box = CollapsibleBox(title="Settings", start_open=True, subtle=True)
        self.settings_box.add_widget(self.settings_widget)
        self.layout().addWidget(self.settings_box)

        # Whenever a new channel is selected, the profile widget should be updated
        viewer.layers.selection.events.changed.connect(self.on_selection_change)

    def assign_colours(self):
        """Assign colours to the channel selector and plot widget"""
        colours = get_channel_colours()
        for channel in self.available_channels:
            if channel not in colours:
                add_colour_for_channel(channel, self.available_channels, VIBRANT_PALETTE)

    def on_selection_change(self, event: Any = None):
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

    def on_line_changed(self, event: Any = None):
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

    def update_profile_from_channels(self, selected_channels: list[str] | None = None):
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
                values, pixel_to_nanometre_scaling, z_units = self.get_profile_data(channel, row_coords, column_coords)

                # Create the plot or update it if it already exists
                if values is not None:
                    self.plot_widget.plot(
                        channel,
                        np.array(np.arange(len(values))) * float(pixel_to_nanometre_scaling),
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
            A tuple containing the profile values (or None if empty), the pixel-to-nanometre
            conversion factor, and the z-axis units.
        """

        # Retrieve the loaded data, pixel-to-nanometre conversion factor, and z-axis units for the specified channel
        data, pixel_to_nanometre_scaling, z_units = self.loaded_image.get_map(channel)

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
            return values, pixel_to_nanometre_scaling, z_units

        # Values returned as None if empty
        return None, pixel_to_nanometre_scaling, z_units

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
    else:
        widget_manager.reveal_docked_widget("Profile Viewer")
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
