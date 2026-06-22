"""
Utilities for testing napari-TopoStats widget behaviour, including loading
test images, simulating button clicks, and opening configuration dialogs.
"""

from pathlib import Path
from unittest.mock import patch

from napari import Viewer
from napari.layers import Image
from napari_afmreader._reader import reader_function
from pytestqt.qtbot import QtBot
from qtpy.QtCore import Qt

from napari_topostats._widget import MAIN_FUNCTIONS, TopoStatsRootWidget


def load_test_image(napari_viewer: Viewer, image_path: str | Path) -> Image | None:
    """
    Load a test AFM image into the napari viewer.

    Parameters
    ----------
    napari_viewer : napari.Viewer
        The viewer to add the image layer to.
    image_path : str or Path
        The path to the AFM image file.

    Returns
    -------
    Image or None
        The loaded napari image layer, or None if no image layer was found.
    """
    layers = reader_function(image_path, channel="Height")
    test_image_layer = None
    for data, metadata, layer_type in layers:
        if layer_type == "image":
            test_image_layer = napari_viewer.add_image(data, name="test image", metadata=metadata)
    return test_image_layer


def run_functions_in_grid(
    qtbot: QtBot,
    topostats_widget: TopoStatsRootWidget,
    napari_viewer: Viewer,
    run_function_on: list[str],
    functions_to_run: list[str],
):
    """
    Simulate clicking functions in the function grid and verify layers appear.

    Parameters
    ----------
    qtbot : QtBot
        The pytest-qt bot for simulating GUI interactions.
    topostats_widget : TopoStatsRootWidget
        The main napari-TopoStats widget containing the function grid.
    napari_viewer : napari.Viewer
        The active napari viewer instance.
    run_function_on : list[str]
        Names of layers to select before running each function.
    functions_to_run : list[str]
        Names of functions to run in the function grid.
    """
    if functions_to_run == ["all"]:
        functions_to_run = [f.name for f in MAIN_FUNCTIONS]
        functions_to_run.remove("load_config")
    button_grid = topostats_widget.function_grid

    for i, func_name in enumerate(functions_to_run):
        print(f"{func_name} running on {run_function_on[i]}")
        pretty_name = func_name.replace("_", " ").title()
        napari_viewer.layers.selection = [napari_viewer.layers[run_function_on[i]]]
        item = button_grid.findItems(pretty_name, Qt.MatchExactly)[0]
        rect = button_grid.visualItemRect(item)
        qtbot.mouseClick(button_grid.viewport(), Qt.LeftButton, pos=rect.center())
        qtbot.wait(300)
        running_function = topostats_widget.get_running_function_widget()
        print(f"Running function: {running_function}")
        while running_function is not None:
            qtbot.wait(300)
            running_function = topostats_widget.get_running_function_widget()


def open_load_config_widget(qtbot: QtBot, topostats_widget: TopoStatsRootWidget):
    """
    Simulate clicking the Load Config button in the function grid.

    Parameters
    ----------
    qtbot : QtBot
        The pytest-qt bot for generating clicks.
    topostats_widget : TopoStatsRootWidget
        The napari-TopoStats widget containing the function grid.
    """

    # pylint: disable=unused-argument
    def get_file_path(*args, **kwargs):
        return (None, None)

    with patch(
        "napari_topostats._io.QFileDialog.getOpenFileName",
        side_effect=get_file_path,
    ):
        button_grid = topostats_widget.function_grid
        load_config_button = button_grid.findItems("Load Config", Qt.MatchExactly)[0]
        rect = button_grid.visualItemRect(load_config_button)
        qtbot.mouseClick(button_grid.viewport(), Qt.LeftButton, pos=rect.center())
        qtbot.wait(100)
