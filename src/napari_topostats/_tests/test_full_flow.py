from pathlib import Path

import napari
import pytest
from napari_afmreader._reader import reader_function
from pytestqt.qtbot import QtBot
from qtpy.QtCore import Qt

from napari_topostats._widget import AVAILABLE_FUNCTIONS, TopoStatsRootWidget

# --- Fixtures ---


@pytest.fixture
def viewer(qtbot: QtBot):
    """Create a Napari viewer with Qtbot cleanup."""
    viewer = napari.Viewer(show=False)
    qtbot.addWidget(viewer.window._qt_window)
    yield viewer
    viewer.close()


@pytest.fixture
def topostats_widget(viewer, qtbot: QtBot):
    """Create the TopoStatsRootWidget and return its function grid."""
    widget = TopoStatsRootWidget(viewer)
    qtbot.addWidget(widget)
    qtbot.wait(50)  # Allow Qt event loop to process
    return widget.function_grid


# --- Helper Functions ---


def load_test_image(viewer, image_path):
    """Load a test AFM image using the napari_afmreader."""
    layers = reader_function(image_path, channel="Height")
    for data, metadata, layer_type in layers:
        if layer_type == "image":
            test_image_layer = viewer.add_image(
                data, name="test image", metadata=metadata
            )
    return test_image_layer


# --- Tests ---


@pytest.mark.parametrize(
    ("run_function_on", "expected_layers"),
    [
        (
            [
                "test image",
                "test image",
                "test image Filter Image",
                "test image Filter Image",
            ],
            [
                "test image",
                "test image Filter Image",
                "test image Filter Image Grains Mask",
                "test image Filter 3D Image",
            ],
        )
    ],
)
def test_functions_in_grid(
    qtbot: QtBot, topostats_widget, viewer, run_function_on, expected_layers
):
    """Simulate clicking functions and verify new layers are created."""
    function_names = [f.name for f in AVAILABLE_FUNCTIONS]
    button_grid = topostats_widget.function_grid
    for i, func_name in enumerate(function_names):
        pretty_name = func_name.replace("_", " ").title()
        viewer.layers.selection = [viewer.layers[run_function_on[i]]]
        item = button_grid.findItems(pretty_name, Qt.MatchExactly)[0]
        qtbot.mouseClick(
            button_grid.viewport(), Qt.LeftButton, pos=item.rect().center()
        )
        button_grid.add_function_as_widget(item)
        qtbot.wait(100)

    for expected_name in expected_layers:
        assert (
            expected_name in viewer.layers
        ), f"Layer '{expected_name}' not found"


def test_button_grid_exists(qtbot: QtBot, button_grid):
    """Ensure the function grid loads correctly."""
    assert (
        button_grid.functions is not None
    ), "Function grid did not initialize"


@pytest.mark.parametrize(
    "image_path",
    [str(Path("src/napari_topostats/_tests/_test_data/4.spm"))],
)
def test_load_image(viewer, image_path):
    """Verify that a test AFM image loads properly."""
    layer = load_test_image(viewer, image_path)
    assert layer is not None, "Failed to load test image"


@pytest.mark.parametrize(
    ("image_path", "run_function_on", "expected_layers"),
    [
        (
            str(Path("src/napari_topostats/_tests/_test_data/4.spm")),
            [
                "test image",
                "test image",
                "test image Filter Image",
                "test image Filter Image",
            ],
            [
                "test image",
                "test image Filter Image",
                "test image Filter Image Grains Mask",
                "test image Filter 3D Image",
            ],
        )
    ],
)
def test_end_to_end(
    qtbot: QtBot,
    viewer,
    topostats_widget,
    image_path,
    run_function_on,
    expected_layers,
):
    """End-to-end test: load image, run functions, and verify layers."""
    load_test_image(viewer, image_path)
    test_functions_in_grid(
        qtbot,
        topostats_widget.function_grid,
        viewer,
        run_function_on,
        expected_layers,
    )
