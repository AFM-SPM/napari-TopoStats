"""Module for viewing force curves at selected image pixels."""

from collections.abc import Generator
from typing import Any

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
        """
        Updates the plot with the selected curve dict

        Parameters
        ----------
        selected_curve_dict : dict
            The dictionary representation of the selected curve
        """
        if selected_curve_dict:
            self.selected_curve_dict = selected_curve_dict
        if self.selected_curve_dict is None:
            return
        self.set_default_channels()
        if self.x_channel not in self.selected_curve_dict or self.y_channel not in self.selected_curve_dict:
            self.info_label.setText("Could not find channels to plot for this curve.")
            return
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
        if x_channel:
            self.x_channel = x_channel
            unit = self.channels_units.get(self.x_channel, "m")
            self.plot_widget.setLabel("bottom", self.x_channel, units=unit)
        if y_channel:
            self.y_channel = y_channel
            unit = self.channels_units.get(self.y_channel, "N")
            self.plot_widget.setLabel("left", self.y_channel, units=unit)
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

        selected_curves = get_selected_curves(self.viewer)
        selected_volume = selected_curves.get_volume(volume_name)
        if selected_volume is None:
            return
        self.assign_segment_colours(selected_volume.metadata.segment_names)
        if self.segment_selector.selector_items:
            starting_segments = [
                name
                for name in self.segment_selector.get_checked_items()
                if name in selected_volume.metadata.segment_names
            ]
        else:
            starting_segments = selected_volume.metadata.segment_names
        if not starting_segments:
            starting_segments = selected_volume.metadata.segment_names
        self.segment_selector.set_items(
            selected_volume.metadata.segment_names,
            starting_items=starting_segments,
            item_colors=get_curve_segment_colours(),
        )
        self.selected_curve_dict = selected_volume[self.y_coord, self.x_coord]

        self.update_segments(self.segment_selector.get_checked_items())
        self.update_analysis_results(selected_volume.get_analysis_results(self.y_coord, self.x_coord))

    def refresh_volumes(self):
        """Refresh available curve volumes and update the currently plotted curve."""
        selected_curves = get_selected_curves(self.viewer, suppress_errors=True)
        if selected_curves is None:
            return

        previous_volume_name = self.volume_selector.currentText()
        volume_names = list(selected_curves.volumes.keys())
        if not volume_names:
            return

        self.volume_selector.clear()
        self.volume_selector.addItems(volume_names)
        if previous_volume_name in selected_curves.volumes:
            self.volume_selector.setCurrentText(previous_volume_name)
        else:
            self.volume_selector.setCurrentText(selected_curves.default_volume_name)

    def update_segments(self, selected_segments: list[str]):
        """
        Updates the segments of the plot based on user checking boxes

        Parameters
        ----------
        selected_segments : list[str]
            The new segments to be set and displayed
        """
        for segment_name in selected_segments:
            self.ensure_segment_line(segment_name)

        for segment_name in list(self.segment_lines.keys()):
            if segment_name not in selected_segments:
                self.plot_widget.removeItem(self.segment_lines[segment_name])
                del self.segment_lines[segment_name]
        self.update_curve()

    def update_analysis_results(self, analysis_results: dict[str, int] | None = None):
        """
        Update visible analysis result markers for the current curve.

        Parameters
        ----------
        analysis_results : dict[str, int] | None
            The analysis results to be displayed on the plot
        """
        if isinstance(analysis_results, dict):
            previous_result_names = set(self.current_analysis_results.keys())
            current_result_names = set(analysis_results.keys())
            self.current_analysis_results = analysis_results

            if previous_result_names != current_result_names:
                self.assign_colours(analysis_results)

                self.analysis_results_selector.set_items(
                    items=list(analysis_results.keys()),
                    starting_items=[name for name in self.active_analysis_markers if name in analysis_results],
                    item_colors=get_analysis_result_colours(),
                )
        selected_analysis_names = self.analysis_results_selector.get_checked_items()

        selected_analysis_results = {
            name: self.current_analysis_results[name]
            for name in selected_analysis_names
            if name in self.current_analysis_results
        }

        if (
            self.selected_curve_dict is None
            or self.x_channel not in self.selected_curve_dict
            or self.y_channel not in self.selected_curve_dict
        ):
            for active_analysis_marker in self.active_analysis_markers.values():
                self.plot_widget.removeItem(active_analysis_marker)
            self.active_analysis_markers.clear()
            return

        marker_segment = next(iter(self.selected_curve_dict[self.x_channel]))

        for result_name in list(self.active_analysis_markers.keys()):
            active_analysis_marker = self.active_analysis_markers[result_name]
            if result_name in selected_analysis_results:
                result_value = selected_analysis_results[result_name]
                result_value_x = self.selected_curve_dict[self.x_channel][marker_segment][result_value]
                result_value_y = self.selected_curve_dict[self.y_channel][marker_segment][result_value]
                active_analysis_marker.setData(
                    x=[result_value_x],
                    y=[result_value_y],
                    data=[{"index": result_value}],
                )
            else:
                self.plot_widget.removeItem(active_analysis_marker)
                self.active_analysis_markers.pop(result_name)
        analysis_result_colours = get_analysis_result_colours()
        for result_name, result_value in selected_analysis_results.items():
            if result_name not in self.active_analysis_markers:
                result_colour = analysis_result_colours[result_name]
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
        Register the mouse callback when the widget is shown.

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

        yield  # Yield control back to napari to wait for drag events

        while event.type == "mouse_move":
            # Optional: stop tracking if the user lets go of Shift while dragging
            if "Shift" not in event.modifiers:
                break

            # Trigger the plot update for the new coordinates
            self._process_event_coords(viewer, event)
            yield

    def assign_colours(self, analysis_results: dict):
        """
        Assign colours to the channel selector and plot widget

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
        Assign colours to curve segments.

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
        layer = viewer.layers.selection.active
        reader_id = layer.metadata.get("afmreader_id") if layer and layer.metadata else None
        loaded_image = get_loaded_image(reader_id) if reader_id is not None else None
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

        self.y_coord = coords[-2]
        self.x_coord = coords[-1]
        shape_x = layer.data.shape[-1]

        curve_num = shape_x * self.y_coord + self.x_coord

        curves_data: CurvesDataset = loaded_image.curves_data
        global_metadata = curves_data.metadata
        if self.volume_selector.currentText() not in curves_data.volumes:
            self.volume_selector.clear()
            self.volume_selector.addItems(curves_data.volumes.keys())
            self.volume_selector.setCurrentText(curves_data.get_default_volume().name)
        current_volume = (
            curves_data.get_volume(self.volume_selector.currentText())
            if self.volume_selector.currentText()
            else curves_data.get_default_volume()
        )

        self.channels_units = current_volume.metadata.channel_units
        try:
            analysis_results = current_volume.get_analysis_results(self.y_coord, self.x_coord)
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
            if self.parameter_dialog is not None:
                self.parameter_dialog.populate_parameters(self.metadata)
            curve_dict = current_volume[self.y_coord, self.x_coord]

            self.set_available_channels(curve_dict.keys())
            self.update_curve(curve_dict)
            self.update_analysis_results(analysis_results)

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
                selected_curve_layer = viewer.add_shapes(
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

            current_index = viewer.layers.index(selected_curve_layer)
            if current_index < len(viewer.layers) - 1:
                viewer.layers.move(current_index, len(viewer.layers))
        except IndexError:
            self.info_label.setText("Clicked outside the image bounds.")

        except Exception as e:  # noqa: BLE001 -- keep plotting failures within the GUI callback
            self.info_label.setText(f"Error plotting curve: {str(e)}")

    def set_available_channels(self, available_channels: list):
        """
        Set the available channels for the curve plotter which updates the selector.

        Parameters
        ----------
        available_channels : list
            The list of available channels.
        """
        available_channels = list(available_channels)
        if self.available_channels == available_channels:
            self.set_default_channels()
            return
        self.available_channels = available_channels
        temp_x_channel = self.x_channel
        temp_y_channel = self.y_channel

        self.x_channel_selector.clear()
        self.y_channel_selector.clear()
        self.x_channel_selector.addItems(self.available_channels)
        self.y_channel_selector.addItems(self.available_channels)

        if temp_x_channel in available_channels:
            self.x_channel = temp_x_channel
        else:
            self.x_channel = None
        if temp_y_channel in available_channels:
            self.y_channel = temp_y_channel
        else:
            self.y_channel = None
        self.set_default_channels()
        if self.x_channel is not None:
            unit = (self.channels_units or {}).get(self.x_channel, "m")
            self.plot_widget.setLabel("bottom", self.x_channel, units=unit)
        if self.y_channel is not None:
            unit = (self.channels_units or {}).get(self.y_channel, "N")
            self.plot_widget.setLabel("left", self.y_channel, units=unit)

    def set_default_channels(self):
        """Select usable default x and y channels when the current selection is unavailable."""
        if None not in (self.x_channel, self.y_channel) or not self.available_channels:
            return
        if self.x_channel is None and self.available_channels and "Height (Measured)" in self.available_channels:
            self.x_channel = "Height (Measured)"
        if self.y_channel is None and self.available_channels and "Vertical Deflection" in self.available_channels:
            self.y_channel = "Vertical Deflection"
        if self.x_channel is None:
            self.x_channel = self.available_channels[0]
        if self.y_channel is None:
            self.y_channel = self.available_channels[0]
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
            w = _get_parameters_widget(value, title=key)
        else:
            w = QLabel(f"{key.title().replace('_', ' ')} : {value}")
        collapsible_box.add_widget(w)
    return collapsible_box
