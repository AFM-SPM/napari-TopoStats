from unittest.mock import patch

from napari_afmreader._reader import reader_function
from pytestqt.qtbot import QtBot
from qtpy.QtCore import Qt

from napari_topostats._widget import AVAILABLE_FUNCTIONS


def load_test_image(napari_viewer, image_path):
    """Load a test AFM image using the napari_afmreader."""
    layers = reader_function(image_path, channel="Height")
    test_image_layer = None
    for data, metadata, layer_type in layers:
        if layer_type == "image":
            test_image_layer = napari_viewer.add_image(
                data, name="test image", metadata=metadata
            )
    return test_image_layer


def run_functions_in_grid(
    qtbot: QtBot,
    topostats_widget,
    napari_viewer,
    run_function_on,
    expected_layers,
):
    """Simulate clicking functions and verify new layers are created."""
    function_names = [f.name for f in AVAILABLE_FUNCTIONS]
    function_names.remove("load_config")
    button_grid = topostats_widget.function_grid
    for i, func_name in enumerate(function_names):
        pretty_name = func_name.replace("_", " ").title()
        napari_viewer.layers.selection = [
            napari_viewer.layers[run_function_on[i]]
        ]
        item = button_grid.findItems(pretty_name, Qt.MatchExactly)[0]
        rect = button_grid.visualItemRect(item)
        qtbot.mouseClick(
            button_grid.viewport(), Qt.LeftButton, pos=rect.center()
        )
        qtbot.wait(100)

    for expected_name in expected_layers:
        assert (
            expected_name in napari_viewer.layers
        ), f"Layer '{expected_name}' not found"


def open_load_config_widget(qtbot: QtBot, topostats_widget):
    """Simulate clicking the Load Config button in the function grid."""

    # pylint: disable=unused-argument
    def get_file_path(*args, **kwargs):
        return (None, None)

    with patch(
        "napari_topostats._io.QFileDialog.getOpenFileName",
        side_effect=get_file_path,
    ):
        button_grid = topostats_widget.function_grid
        load_config_button = button_grid.findItems(
            "Load Config", Qt.MatchExactly
        )[0]
        rect = button_grid.visualItemRect(load_config_button)
        qtbot.mouseClick(
            button_grid.viewport(), Qt.LeftButton, pos=rect.center()
        )
        qtbot.wait(100)
