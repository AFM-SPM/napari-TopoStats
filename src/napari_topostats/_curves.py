"""Module for viewing force curves at selected image pixels."""

from collections.abc import Generator
from typing import Any

from napari_topostats._alerts import show_error_dialog
import numpy as np
import pyqtgraph as pg
from AFMReader.data_classes import CurvesDataset
from napari import Viewer
from napari_afmreader._reader import get_loaded_image
from qtpy.QtGui import QHideEvent, QPainterPath, QShowEvent, QTransform
from qtpy.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from napari_topostats._components import CollapsibleBox, SelectionDropdown, get_selected_curves
from napari_topostats._state import (
    add_colour_for_analysis_result,
    add_colour_for_curve_segment,
    get_analysis_result_colours,
    get_curve_segment_colours,
)
from napari_topostats._styles import (
    COLOR_SELECTED_CURVE,
    CURVE_VIEWER_MARGIN,
    CURVE_VIEWER_RIGHT_MARGIN,
    SEGMENT_COLOURS,
    VIBRANT_PALETTE,
)
from napari_topostats._state import get_widget_manager
from napari_topostats.utils import unflatten_dict


def _filled_cross_symbol() -> QPainterPath:
    """
    Create a filled cross symbol for analysis result markers.

    Returns
    -------
    QPainterPath
        The painting path representing a filled cross
    """
    path = QPainterPath()
    path.addRect(-0.5, -0.1, 1.0, 0.2)
    path.addRect(-0.1, -0.5, 0.2, 1.0)
    return QTransform().rotate(45).map(path)


def open_curve_viewer(viewer: Viewer) -> "CurveViewer":
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


class CurveViewer(QWidget):  # pylint: disable=too-many-instance-attributes
    """
    Custom docked widget for displaying force curves

    Parameters
    ----------
    viewer : napari.Viewer
        The napari viewer to attach the curve viewer to.
    """

    # pylint: disable=too-many-statements
    def __init__(self, viewer: Viewer):
        """
        Initialize the curve viewer and attach it to the napari viewer.

        Parameters
        ----------
        viewer : napari.Viewer
            The napari viewer to attach the curve viewer to.
        """
        super().__init__()
        self.viewer = viewer
        self.widget_manager = get_widget_manager()

        # Setup the layout to be arranged vertically
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(
            CURVE_VIEWER_MARGIN, CURVE_VIEWER_MARGIN, CURVE_VIEWER_RIGHT_MARGIN, CURVE_VIEWER_MARGIN
        )
        top_row_widget = QWidget()
        top_row_layout = QHBoxLayout(top_row_widget)
        top_row_layout.setContentsMargins(0, 0, 0, 0)

        # Create and add info label to the layout to provide user instructions for viewing force curves
        self.info_label = QLabel("Hold 'Shift' and click a pixel to view its force curve.")
        top_row_layout.addWidget(self.info_label)

        # Create a volume selector combo box for choosing the volume to display
        self.volume_selector = QComboBox()
        self.volume_selector.currentTextChanged.connect(self.update_volume)
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
        self.plot_widget: pg.PlotItem = self.plot_graphics_widget.addPlot(title="Force Distance curve")
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

        self.segment_selector = SelectionDropdown(
            items=[],
            type_text="segments",
            starting_items=[],
            on_change=self.update_segments,
            item_colors=get_curve_segment_colours(),
        )
        # Add a label for the segment selector and add it to the left layout
        segment_selector_label = QLabel("Select segment")
        self.left_layout.addWidget(segment_selector_label)

        self.right_layout.addWidget(self.segment_selector)

        self.parameter_dialog = None
        self.metadata = {}

        # Create and add the button to open the experimental parameters dialog
        self.open_dialog_button = QPushButton("View experimental parameters")
        self.open_dialog_button.clicked.connect(self.open_experimental_parameters)
        self.left_layout.addWidget(self.open_dialog_button)

        # Create a selection dropdown for analysis results and add it to the right layout
        self.analysis_results_selector = SelectionDropdown(
            items=[],
            type_text="metrics",
            starting_items=[],
            on_change=self.update_analysis_results,
            item_colors=get_analysis_result_colours(),
        )
        self.right_layout.addWidget(self.analysis_results_selector)

        # Add the left and right widgets to a collapsible settings section at the bottom of the viewer
        self.settings_layout.addWidget(self.left_widget)
        self.settings_layout.addWidget(self.right_widget)
        self.settings_box = CollapsibleBox(title="Settings", start_open=True, subtle=True)
        self.settings_box.add_widget(self.settings_widget)
        self.layout().addWidget(self.settings_box)

        # Initialize coordinates, channels and dicts
        self.x_coord = 0
        self.y_coord = 0
        self.x_channel = None
        self.y_channel = None
        self.selected_curve_dict = None
        self.channels_units = None
        self.current_reader_id = None
        self.current_analysis_results = {}
        self.active_analysis_markers = {}

        # Create the plots with empty data for approach and retract segments
        self.segment_lines = {}

    def open_experimental_parameters(self):
        """Open the experimental parameters dialog"""
        if self.parameter_dialog is None:
            self.parameter_dialog = ParameterDialog(self.metadata)

        # If the parameter dialog was previous created but has now been minimised or otherwise made invisible,
        # bring it to the front and make it visible
        if not self.parameter_dialog.isVisible():
            try:
                self.parameter_dialog.show()
                self.parameter_dialog.raise_()
                self.parameter_dialog.activateWindow()
            except RuntimeError:
                self.widget_manager.ensure_valid()
                self.parameter_dialog = None
        
        self.parameter_dialog.populate_parameters(self.metadata)

    def update_curve(self, selected_curve_dict: dict = None):
        """
        Updates the plot with the selected curve dict

        Parameters
        ----------
        selected_curve_dict : dict
            The dictionary representation of the selected curve
        """

        # Update the currently selected curve with new data if a new selection is provided
        if selected_curve_dict:
            self.selected_curve_dict = selected_curve_dict

        if self.selected_curve_dict is None:
            return
        # Ensure some channels are selected before plotting
        self.set_default_channels()

        if self.x_channel not in self.selected_curve_dict or self.y_channel not in self.selected_curve_dict:
            # This could happen if selected channels were present elsewhere in the data but not for the current segment
            self.info_label.setText("Could not find channels to plot for this curve.")
            return
        
        # Plot the data for each selected segment
        for selected_segment in self.segment_selector.get_checked_items():
            self.ensure_segment_line(selected_segment)
            x_data = self.selected_curve_dict[self.x_channel][selected_segment]
            y_data = self.selected_curve_dict[self.y_channel][selected_segment]
            self.segment_lines[selected_segment].setData(x_data, y_data)
        self.info_label.setText(f"Plotting curve for pixel (x={self.x_coord}, y={self.y_coord}).")

    def update_channels(self, x_channel: str | None = None, y_channel: str | None = None):
        """
        Updates the channels of the plot and refreshes curve to match

        Parameters
        ----------
        x_channel : str | None
            The current x-axis channel
        y_channel : str | None
            The current y-axis channel
        """
        # Update the plot with the new channel name and unit
        if x_channel:
            self.x_channel = x_channel
            unit = self.channels_units.get(self.x_channel, "m")
            self.plot_widget.setLabel("bottom", self.x_channel, units=unit)
        if y_channel:
            self.y_channel = y_channel
            unit = self.channels_units.get(self.y_channel, "N")
            self.plot_widget.setLabel("left", self.y_channel, units=unit)
        # Then refresh the curve and analysis results
        self.update_curve()
        self.update_analysis_results()

    def update_volume(self, volume_name: str):
        """
        Updates the volume of the plot and refreshes curve to match

        Parameters
        ----------
        volume_name : str
            The name of the new volume to be set
        """
        if not volume_name:
            return

        # Attempt to retrieve the selected volume from the currently selected layer
        selected_curves = get_selected_curves(self.viewer)
        selected_volume = selected_curves.get_volume(volume_name)
        if selected_volume is None:
            return

        # Segments may have been updated in the new volume, so we need to refresh the segment colours and selector
        self.assign_segment_colours(selected_volume.metadata.segment_names)
        if self.segment_selector.selector_items:
            # If there are already selected segments, keep them if they still exist in the new volume
            starting_segments = [
                name
                for name in self.segment_selector.get_checked_items()
                if name in selected_volume.metadata.segment_names
            ]
        else:
            starting_segments = selected_volume.metadata.segment_names
        if not starting_segments:
            # If no overlap between previously selected segments and the new volume, select all segments
            starting_segments = selected_volume.metadata.segment_names

        self.segment_selector.set_items(
            selected_volume.metadata.segment_names,
            starting_items=starting_segments,
            item_colors=get_curve_segment_colours(),
        )
        # Get the curve from the current volume with the previously selected coordinates
        self.selected_curve_dict = selected_volume[self.y_coord, self.x_coord]

        # Update the segment lines with the new volume data
        self.update_segments(self.segment_selector.get_checked_items())

        self.update_analysis_results(selected_volume.get_analysis_results(self.y_coord, self.x_coord))

    def refresh_volumes(self):
        """Refresh available curve volumes when a new layer is selected."""
        selected_curves: CurvesDataset = get_selected_curves(self.viewer, suppress_errors=True)
        if selected_curves is None:
            return

        previous_volume_name = self.volume_selector.currentText()
        volume_names = list(selected_curves.volumes.keys())
        if not volume_names:
            return

        # Clear and refill the volume selector with the available volumes for the selected layer
        self.volume_selector.clear()
        self.volume_selector.addItems(volume_names)
        if previous_volume_name in selected_curves.volumes:
            # Restore the selected volume from the previous layer if it still exists
            self.volume_selector.setCurrentText(previous_volume_name)
        else:
            # If the previously selected volume is not available, default to the layer's default volume
            self.volume_selector.setCurrentText(selected_curves.default_volume_name)

    def update_segments(self, selected_segments: list[str]):
        """
        Updates the segments of the plot based on user checking boxes

        Parameters
        ----------
        selected_segments : list[str]
            The new segments to be set and displayed
        """
        # Make sure all the selected segments have corresponding lines in the plot (if already there
        # they will be reused and simply have their data updated)
        for segment_name in selected_segments:
            self.ensure_segment_line(segment_name)

        # Remove any segment lines that are no longer selected
        for segment_name in list(self.segment_lines.keys()):
            if segment_name not in selected_segments:
                self.plot_widget.removeItem(self.segment_lines[segment_name])
                del self.segment_lines[segment_name]
                
        # Finally, update the curve to reflect the current selection of segments
        self.update_curve()

    def update_analysis_results(self, analysis_results: dict[str, int] | None = None):
        """
        Update visible analysis result markers for the current curve.

        Parameters
        ----------
        analysis_results : dict[str, int] | None
            The analysis results to be displayed on the plot
        """
        # If analysis_results is a dictionary (and not None), update the internal state and UI accordingly
        if isinstance(analysis_results, dict):
            previous_result_names = set(self.current_analysis_results.keys())
            current_result_names = set(analysis_results.keys())
            self.current_analysis_results = analysis_results

            # If the set of result names has changed, assign colours to the new results
            if previous_result_names != current_result_names:
                self.assign_colours(analysis_results)

                # And update the analysis results selector with the new items and their colors
                self.analysis_results_selector.set_items(
                    items=list(analysis_results.keys()),
                    starting_items=[name for name in self.active_analysis_markers if name in analysis_results],
                    item_colors=get_analysis_result_colours(),
                )

        # Get the selected analysis result names from the analysis results selector (guarded against stale entries)
        selected_analysis_names = self.analysis_results_selector.get_checked_items()
        selected_analysis_results = {
            name: self.current_analysis_results[name]
            for name in selected_analysis_names
            if name in self.current_analysis_results
        }

        # If no curve is selected or the required channels are missing, clear the active analysis markers and return as
        # valid data cannot be plotted
        if (
            self.selected_curve_dict is None
            or self.x_channel not in self.selected_curve_dict
            or self.y_channel not in self.selected_curve_dict
        ):
            for active_analysis_marker in self.active_analysis_markers.values():
                self.plot_widget.removeItem(active_analysis_marker)
            self.active_analysis_markers.clear()
            return

        # TODO: Currently markers can only be associated with the first segment of the selected curve
        marker_segment = next(iter(self.selected_curve_dict[self.x_channel]))

        # Update the positions of the active analysis markers based on the selected analysis results
        for result_name in list(self.active_analysis_markers.keys()):
            active_analysis_marker = self.active_analysis_markers[result_name]
            if result_name in selected_analysis_results:
                # Analysis results are stored as indices into the curve data
                result_value = selected_analysis_results[result_name]
                # Extract the x and y values corresponding to the result index so we know where to place the marker
                result_value_x = self.selected_curve_dict[self.x_channel][marker_segment][result_value]
                result_value_y = self.selected_curve_dict[self.y_channel][marker_segment][result_value]
                # Update the marker position with the extracted coordinates
                active_analysis_marker.setData(
                    x=[result_value_x],
                    y=[result_value_y],
                    data=[{"index": result_value}],
                )
            else:
                # If a marker is no longer selected, remove it from the plot and the active markers dictionary
                self.plot_widget.removeItem(active_analysis_marker)
                self.active_analysis_markers.pop(result_name)

        analysis_result_colours = get_analysis_result_colours()

        # If new analysis results have been selected, create and add markers for them
        for result_name, result_value in selected_analysis_results.items():
            if result_name not in self.active_analysis_markers:
                result_colour = analysis_result_colours[result_name]

                # Extract the x and y coordinates for the new analysis result marker (the result value should be an
                # index into the curve data)
                result_value_x = self.selected_curve_dict[self.x_channel][marker_segment][result_value]
                result_value_y = self.selected_curve_dict[self.y_channel][marker_segment][result_value]

                # pylint: disable=unused-argument
                def result_tip(
                    x: float,
                    y: float,
                    data: dict[str, Any] | None = None,
                    result_name: str = result_name,
                ) -> str:
                    """
                    Build the hover text for an analysis-result marker.

                    Scatter plot item takes a function rather than a constant string so it can update automatically 
                    based on the marker's data such as if it moves.

                    Parameters
                    ----------
                    x : float
                        Marker x-coordinate supplied by pyqtgraph.
                    y : float
                        Marker y-coordinate supplied by pyqtgraph.
                    data : dict[str, Any] | None
                        Marker metadata containing the result index to display.
                    result_name : str
                        Analysis-result name used as the tooltip label.

                    Returns
                    -------
                    str
                        Tooltip containing the formatted result name and index.
                    """
                    idx = data.get("index", "") if data is not None else ""
                    return f"{result_name.title().replace('_', ' ')}: {idx}"

                # Create the cross shaped scatter plot marker for the analysis result
                marker = pg.ScatterPlotItem(
                    x=[result_value_x],
                    y=[result_value_y],
                    size=15,
                    symbol=_filled_cross_symbol(),
                    pen=pg.mkPen(result_colour, width=0),
                    brush=pg.mkBrush(result_colour),
                    hoverable=True,
                    hoverPen=pg.mkPen("y", width=3),
                    data=[{"index": result_value}],
                    tip=result_tip,
                )
                self.active_analysis_markers[result_name] = marker
                self.plot_widget.addItem(marker)

    def showEvent(self, event: QShowEvent):
        """
        Register the mouse callback when the widget is shown (created or made visible).

        Parameters
        ----------
        event : QShowEvent
            Qt event raised when the curve viewer is shown.
        """
        if self.extract_curve not in self.viewer.mouse_drag_callbacks:
            self.viewer.mouse_drag_callbacks.append(self.extract_curve)
        super().showEvent(event)

    def hideEvent(self, event: QHideEvent):
        """
        Clean up the mouse callback and selection cross layer when hidden/closed.

        Parameters
        ----------
        event : QHideEvent
            Qt event raised when the curve viewer is hidden.
        """
        if self.extract_curve in self.viewer.mouse_drag_callbacks:
            self.viewer.mouse_drag_callbacks.remove(self.extract_curve)
        if "Selected Curve" in self.viewer.layers:
            self.viewer.layers.remove("Selected Curve")
        super().hideEvent(event)

    def extract_curve(self, viewer: Viewer, event: Any) -> Generator[None, None, None]:
        """
        Generator that runs when the user clicks and drags the mouse in the viewer.

        Parameters
        ----------
        viewer : Viewer
            Viewer in which the mouse interaction occurred.
        event : Any
            Napari mouse event containing the position, type, and active modifiers.

        Yields
        ------
        Generator[None, None, None]
            Control yielded to napari between mouse-drag updates.
        """
        if "Shift" not in event.modifiers:
            return

        # Trigger the initial plot on click
        self._process_event_coords(viewer, event)

        # Yield control back to napari to wait for drag events
        yield  

        while event.type == "mouse_move":
            # Optional: stop tracking if the user lets go of Shift while dragging
            if "Shift" not in event.modifiers:
                break

            # Trigger the plot update for the new coordinates
            self._process_event_coords(viewer, event)
            yield

    def assign_colours(self, analysis_results: dict):
        """
        Assign colours for the channel selector and plot widget

        Parameters
        ----------
        analysis_results : dict
            Available analysis results whose names require plot colours.
        """
        colours = get_analysis_result_colours()
        for result in analysis_results:
            if result not in colours:
                add_colour_for_analysis_result(result, list(analysis_results.keys()), VIBRANT_PALETTE)

    def assign_segment_colours(self, segments: list[str]):
        """
        Assign colours for curve segments.

        Parameters
        ----------
        segments : list[str]
            Curve segment names whose plot colours should be assigned.
        """
        colours = get_curve_segment_colours()
        for segment in segments:
            if segment not in colours:
                add_colour_for_curve_segment(segment, list(segments), SEGMENT_COLOURS)

    def ensure_segment_line(self, segment_name: str):
        """
        Create the plot line for a curve segment if it does not exist yet.

        Parameters
        ----------
        segment_name : str
            Curve segment for which a plot line should exist.
        """
        if segment_name in self.segment_lines:
            return
        self.segment_lines[segment_name] = self.plot_widget.plot(
            [],
            [],
            pen=get_curve_segment_colours()[segment_name],
        )

    def _process_event_coords(self, viewer: Viewer, event: Any):
        """
        The core logic to extract and plot the curve at the current mouse position.

        Parameters
        ----------
        viewer : Viewer
            Viewer containing the selected force-curve layer.
        event : Any
            Mouse event whose position identifies the curve to extract.
        """
        # Extract data references from selected layer
        layer = viewer.layers.selection.active
        reader_id = layer.metadata.get("afmreader_id") if layer and layer.metadata else None
        loaded_image = get_loaded_image(reader_id) if reader_id is not None else None
        # If no loaded image or curves data is available, display an info message and return early
        if loaded_image is None or loaded_image.curves_data is None:
            self.info_label.setText("No force curves found in active layer.")
            return
        if reader_id != self.current_reader_id:
            self.refresh_volumes()
            self.current_reader_id = reader_id

        # Get click coordinates and convert to integers
        coords = np.round(layer.world_to_data(event.position)).astype(int)

        # Prevent redundant updates if the mouse moves but stays within the same integer pixel
        if coords[-2] == self.y_coord and coords[-1] == self.x_coord:
            return

        # Update the stored coordinates for the current mouse position
        self.y_coord = coords[-2]
        self.x_coord = coords[-1]

        # Compute the linear index of the curve based on the x and y coordinates
        shape_x = layer.data.shape[-1]
        curve_num = shape_x * self.y_coord + self.x_coord

        curves_data: CurvesDataset = loaded_image.curves_data
        global_metadata = curves_data.metadata
        if self.volume_selector.currentText() not in curves_data.volumes:
            # If the currently selected volume is not in the available volumes, refresh the volume selector
            self.volume_selector.clear()
            self.volume_selector.addItems(curves_data.volumes.keys())
            # And use the default volume as the current selection so a curve can still be displayed
            self.volume_selector.setCurrentText(curves_data.get_default_volume().name)

        current_volume = (
            curves_data.get_volume(self.volume_selector.currentText())
            if self.volume_selector.currentText()
            else curves_data.get_default_volume()
        )

        self.channels_units = current_volume.metadata.channel_units
        # Attempt to retrieve and display data for the selected curve
        try:
            analysis_results = current_volume.get_analysis_results(self.y_coord, self.x_coord)
            # Update the metadata for the selected curve
            self.metadata = {
                "global": global_metadata,
                f"curve_{curve_num}": current_volume.metadata[self.y_coord, self.x_coord],
            }
            self.metadata.update(
                {
                    f"curve_{curve_num}_{segment_name}": current_volume.metadata[
                        self.y_coord, self.x_coord, segment_name
                    ]
                    for segment_name in current_volume.metadata.segment_names
                }
            )
            # Update the gui for the new metadata
            # TODO: Updates for the metadata in the GUI doesn't work perfectly
            if self.parameter_dialog is not None:
                self.parameter_dialog.populate_parameters(self.metadata)

            # Retrieve the curve data for the selected coordinates
            curve_dict = current_volume[self.y_coord, self.x_coord]

            self.set_available_channels(curve_dict.keys())
            self.update_curve(curve_dict)
            self.update_analysis_results(analysis_results)

            # Update the cross on the viewer at the selected pixel position
            selected_position = layer.data_to_world(coords)
            
            centre_y, centre_x = selected_position[-2:]

            # The cross should extend 3 pixels from the centre in each direction
            y_scale, x_scale = np.abs(layer.scale[-2:])
            half_size = max(y_scale, x_scale) * 3

            # X and Y coordinates are the centre of the cross use the half_size to determine the end points
            # of the cross lines
            cross_data = np.array(
                [
                    [[centre_y - half_size, centre_x - half_size], [centre_y + half_size, centre_x + half_size]],
                    [[centre_y - half_size, centre_x + half_size], [centre_y + half_size, centre_x - half_size]],
                ]
            )
            if "Selected Curve" in viewer.layers and not hasattr(viewer.layers["Selected Curve"], "edge_width"):
                viewer.layers.remove("Selected Curve")

            if "Selected Curve" not in viewer.layers:
                active_layer = viewer.layers.selection.active
                # Add the cross layer to the viewer to indicate the selected curve if not already present
                selected_curve_layer = viewer.add_shapes(
                    data=cross_data,
                    name="Selected Curve",
                    shape_type="line",
                    edge_color=COLOR_SELECTED_CURVE,
                    # Line width for the cross should be half a pixel
                    edge_width=max(y_scale, x_scale) * 0.5,
                )
                # Need to keep the layer with the actual data selected (adding a layer, including the shapes layer,
                # automatically selects the new layer)
                if active_layer is not None:
                    viewer.layers.selection.active = active_layer
            else:
                selected_curve_layer = viewer.layers["Selected Curve"]
                # Edge colour can get messed up so set it here before updating the data (can cause errors otherwise)
                selected_curve_layer.edge_color = COLOR_SELECTED_CURVE
                # Update the location of the cross to match the newly selected curve
                selected_curve_layer.data = cross_data
                selected_curve_layer.edge_width = max(y_scale, x_scale) * 0.5

            # Bring the selected curve layer to the top of the layer stack so its visible
            current_index = viewer.layers.index(selected_curve_layer)
            if current_index < len(viewer.layers) - 1:
                viewer.layers.move(current_index, len(viewer.layers))

        # Only catch IndexError separately to provide a specific message for clicks outside the image bounds
        except IndexError:
            self.info_label.setText("Clicked outside the image bounds.")

        except Exception as e:  # noqa: BLE001 -- keep plotting failures within the GUI callback
            self.info_label.setText(f"Error plotting curve: {str(e)}")
            show_error_dialog(raise_exception=True, exception=e)

    def set_available_channels(self, available_channels: list):
        """
        Set the available channels for the curve plotter which updates the selector.

        Parameters
        ----------
        available_channels : list
            The list of available channels.
        """
        available_channels = list(available_channels)
        # If the available channels haven't changed, ensure a channel is set, defaulting if necessary
        if self.available_channels == available_channels:
            self.set_default_channels()
            return
        self.available_channels = available_channels
        # Temporarily store the current x and y channels so they potentially can be restored
        temp_x_channel = self.x_channel
        temp_y_channel = self.y_channel

        # Replace the items in the channel selectors with the updated list of available channels
        self.x_channel_selector.clear()
        self.y_channel_selector.clear()
        self.x_channel_selector.addItems(self.available_channels)
        self.y_channel_selector.addItems(self.available_channels)

        # Restore the previously selected channels if they are still available
        if temp_x_channel in available_channels:
            self.x_channel = temp_x_channel
        else:
            self.x_channel = None
        if temp_y_channel in available_channels:
            self.y_channel = temp_y_channel
        else:
            self.y_channel = None

        # Ensure that there are default channels set if the previous ones were not available
        self.set_default_channels()

        # Update the plot widget labels to reflect the current x and y channels
        if self.x_channel is not None:
            unit = (self.channels_units or {}).get(self.x_channel, "m")
            self.plot_widget.setLabel("bottom", self.x_channel, units=unit)
        if self.y_channel is not None:
            unit = (self.channels_units or {}).get(self.y_channel, "N")
            self.plot_widget.setLabel("left", self.y_channel, units=unit)

    def set_default_channels(self):
        """Select usable default x and y channels when the current selection is unavailable."""
        # Return if both x and y channels are already set or if there are no available channels to default within
        if None not in (self.x_channel, self.y_channel) or not self.available_channels:
            return
        # Try and set the default channels to show a standard Force-Distance curve 
        if self.x_channel is None and self.available_channels and "Height (Measured)" in self.available_channels:
            self.x_channel = "Height (Measured)"
        if self.y_channel is None and self.available_channels and "Vertical Deflection" in self.available_channels:
            self.y_channel = "Vertical Deflection"
        # If the preferred default channels are not available, fall back to the first available channels
        if self.x_channel is None:
            self.x_channel = self.available_channels[0]
        if self.y_channel is None:
            self.y_channel = self.available_channels[0]
        # Update the channel selectors to reflect new channels
        self.y_channel_selector.setCurrentText(self.y_channel)
        self.x_channel_selector.setCurrentText(self.x_channel)


class ParameterDialog(QDialog):
    """
    Custom parameters dialog to show values for selected curves

    Parameters
    ----------
    metadata : dict[str, Any] | None, optional
        Experimental parameters to display.
    parent : QWidget | None, optional
        Parent widget for the dialog.
    """

    def __init__(self, metadata: dict[str, Any] | None = None, parent: QWidget | None = None):
        """
        Initialises ParameterDialog.

        Parameters
        ----------
        metadata : dict[str, Any] | None, optional
            Experimental parameters to display.
        parent : QWidget | None, optional
            Parent widget for the dialog.
        """
        super().__init__(parent)
        # Create the main layout and scroll area for displaying the experimental parameters
        self.setWindowTitle("Experimental Parameters")
        self.resize(500, 600)
        self.setLayout(QVBoxLayout())
        self.info_widget = CollapsibleBox(title="Experimental parameters", start_open=True)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.info_widget)
        if metadata is None:
            metadata = {}
        # Set the metadata to its starting state and populate the parameters dialog with it
        self.metadata = metadata
        self.populate_parameters(self.metadata)
        self.layout().addWidget(self.scroll_area)

    def populate_parameters(self, metadata: dict[str, Any]):
        """
        Populate the parameters viewing dialog with the metadata

        Parameters
        ----------
        metadata : dict[str, Any]
            Flattened experimental metadata to display in the dialog.
        """
        self.metadata = metadata
        parameters_dict = unflatten_dict(self.metadata)
        self.info_widget.update(parameters_dict)


def _get_parameters_widget(dict_data: dict[str, Any], title: str = "Parameters") -> CollapsibleBox:
    """
    Build a collapsible widget from nested experimental parameters/ metadata.

    Parameters
    ----------
    dict_data : dict[str, Any]
        Parameter names and values, which may contain nested dictionaries.
    title : str
        Heading displayed on the collapsible section.

    Returns
    -------
    CollapsibleBox
        Collapsible hierarchy displaying the supplied parameter values.
    """
    collapsible_box = CollapsibleBox(title=title)
    for key, value in dict_data.items():
        if isinstance(value, dict):
            # Recursively build a collapsible widget for the nested dictionary
            w = _get_parameters_widget(value, title=key)
        else:
            w = QLabel(f"{key.title().replace('_', ' ')} : {value}")
        collapsible_box.add_widget(w)
    return collapsible_box
