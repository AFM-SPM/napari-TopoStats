"""Module for viewing force curves at selected image pixels."""

import numpy as np
import pyqtgraph as pg
from AFMReader.data_classes import CurvesDataset
from napari_afmreader._reader import get_loaded_image
from qtpy.QtGui import QPainterPath, QTransform
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

from napari_topostats._components import CollapsibleBox, SelectionDropdown, get_selected_curves
from napari_topostats._state import (
    add_colour_for_analysis_result,
    get_analysis_result_colours,
)
from napari_topostats._styles import (
    COLOR_APPROACH,
    COLOR_RETRACT,
    COLOR_SELECTED_CURVE,
    CURVE_VIEWER_MARGIN,
    CURVE_VIEWER_RIGHT_MARGIN,
    VIBRANT_PALETTE,
)
from napari_topostats.utils import measured_height_names, unflatten_dict, vertical_deflection_names


def _filled_cross_symbol() -> QPainterPath:
    """Create a filled cross symbol for analysis result markers."""
    path = QPainterPath()
    path.addRect(-0.5, -0.1, 1.0, 0.2)
    path.addRect(-0.1, -0.5, 0.2, 1.0)
    return QTransform().rotate(45).map(path)


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


class CurveViewer(QWidget):  # pylint: disable=too-many-instance-attributes
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
        self.current_analysis_results = {}
        self.active_analysis_markers = {}

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
        self.set_default_channels()
        if self.x_channel not in self.selected_curve_dict or self.y_channel not in self.selected_curve_dict:
            self.info_label.setText("Could not find channels to plot for this curve.")
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
        self.update_analysis_results()

    def update_volume(self, volume_name: str):
        """Updates the volume of the plot and refreshes curve to match"""
        if not volume_name:
            return

        selected_curves = get_selected_curves(self.viewer)
        selected_volume = selected_curves.get_volume(volume_name)
        if selected_volume is None:
            return

        self.update_curve(selected_volume[self.y_coord, self.x_coord])
        self.update_analysis_results(selected_volume.get_analysis_results(self.y_coord, self.x_coord))

    def update_segments(self, approach: bool | None = None, retract: bool | None = None):
        """Updates the segments of the plot based on user checking boxes"""
        if approach is not None:
            self.show_approach = approach
        if retract is not None:
            self.show_retract = retract
        self.update_curve()

    def update_analysis_results(self, analysis_results=None):
        """Update visible analysis result markers for the current curve."""
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

        if self.selected_curve_dict is None:
            for active_analysis_marker in self.active_analysis_markers.values():
                self.plot_widget.removeItem(active_analysis_marker)
            self.active_analysis_markers.clear()
            return

        for result_name in list(self.active_analysis_markers.keys()):
            active_analysis_marker = self.active_analysis_markers[result_name]
            if result_name in selected_analysis_results:
                result_value = selected_analysis_results[result_name]
                result_value_x = self.selected_curve_dict[self.x_channel]["Segment_0"][result_value]
                result_value_y = self.selected_curve_dict[self.y_channel]["Segment_0"][result_value]
                active_analysis_marker.setData(x=[result_value_x], y=[result_value_y])
            else:
                self.plot_widget.removeItem(active_analysis_marker)
                self.active_analysis_markers.pop(result_name)
        analysis_result_colours = get_analysis_result_colours()
        for result_name, result_value in selected_analysis_results.items():
            if result_name not in self.active_analysis_markers:
                result_colour = analysis_result_colours.get(result_name, "r")
                result_value_x = self.selected_curve_dict[self.x_channel]["Segment_0"][result_value]
                result_value_y = self.selected_curve_dict[self.y_channel]["Segment_0"][result_value]

                def result_tip(x, y, _data, result_name=result_name):
                    x_unit = self.channels_units.get(self.x_channel, "")
                    y_unit = self.channels_units.get(self.y_channel, "")
                    return (
                        f"{result_name.title().replace('_', ' ')}\n"
                        f"{self.x_channel}: {x:.3f} {x_unit}\n"
                        f"{self.y_channel}: {y:.3f} {y_unit}"
                    )

                marker = pg.ScatterPlotItem(
                    x=[result_value_x],
                    y=[result_value_y],
                    size=15,
                    symbol=_filled_cross_symbol(),
                    pen=pg.mkPen(result_colour, width=0),
                    brush=pg.mkBrush(result_colour),
                    hoverable=True,
                    hoverPen=pg.mkPen("y", width=3),
                    tip=result_tip,
                )
                self.active_analysis_markers[result_name] = marker
                self.plot_widget.addItem(marker)

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

    def assign_colours(self, analysis_results: dict):
        """Assign colours to the channel selector and plot widget"""
        colours = get_analysis_result_colours()
        for result in analysis_results:
            if result not in colours:
                add_colour_for_analysis_result(result, list(analysis_results.keys()), VIBRANT_PALETTE)

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

        curves_data: CurvesDataset = loaded_image.curves_data
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
        analysis_results = current_volume.get_analysis_results(self.y_coord, self.x_coord)

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
        if self.x_channel is None and self.available_channels:
            for default_x in measured_height_names:
                if default_x in self.available_channels:
                    self.x_channel = default_x
                    break
        if self.y_channel is None and self.available_channels:
            for default_y in vertical_deflection_names:
                if default_y in self.available_channels:
                    self.y_channel = default_y
                    break
        if self.x_channel is None:
            self.x_channel = self.available_channels[0]
        if self.y_channel is None:
            self.y_channel = self.available_channels[0]
        self.y_channel_selector.setCurrentText(self.y_channel)
        self.x_channel_selector.setCurrentText(self.x_channel)


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
