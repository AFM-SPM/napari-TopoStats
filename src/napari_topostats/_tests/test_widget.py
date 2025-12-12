"""Tests for the widget functionalities of the plugin."""

from pathlib import Path

import pytest
from napari import Viewer
from pytestqt.qtbot import QtBot

from napari_topostats._widget import TopoStatsRootWidget

from ._helpers import load_test_image, run_functions_in_grid


def test_button_grid_exists(topostats_widget: TopoStatsRootWidget):
    """Ensure the function grid loads correctly."""
    assert topostats_widget.function_grid.functions is not None, "Function grid did not initialize"


@pytest.mark.parametrize(
    "image_path",
    [
        pytest.param(
            str(Path("src/napari_topostats/_tests/_test_data/test_spm.spm")),
            id="Testing loading with valid image path",
        )
    ],
)
def test_load_image(napari_viewer: Viewer, image_path: str):
    """Verify that a test AFM image loads properly."""
    layer = load_test_image(napari_viewer, image_path)
    assert layer is not None, "Failed to load test image"


@pytest.mark.parametrize(
    ("image_path", "run_function_on", "expected_layers"),
    [
        pytest.param(
            str(Path("src/napari_topostats/_tests/_test_data/test_spm.spm")),
            [
                "test image",
                "test image Filter Image",
                "test image Filter Image",
                "test image Filter Image Grains Mask",
            ],
            [
                "test image",
                "test image Filter Image",
                "test image Filter Image Grains Mask",
                "test image Filter 3D Image",
            ],
            id="Testing all the functions in standard order",
        )
    ],
)
def test_functions_in_grid(  # pylint: disable=too-many-positional-arguments
    qtbot: QtBot,
    napari_viewer: Viewer,
    topostats_widget: TopoStatsRootWidget,
    image_path: str,
    run_function_on: list[str],
    expected_layers: list[str],
):
    """End-to-end test: load image, run functions, and verify layers."""
    load_test_image(napari_viewer, image_path)
    run_functions_in_grid(
        qtbot,
        topostats_widget,
        napari_viewer,
        run_function_on,
    )
    for expected_name in expected_layers:
        assert expected_name in napari_viewer.layers, f"Layer '{expected_name}' not found"


@pytest.mark.parametrize(
    ("image_path", "run_function_on"),
    [
        pytest.param(
            str(Path("src/napari_topostats/_tests/_test_data/test_spm.spm")),
            [
                "test image",
                "test image Filter Image",
                "test image Filter Image",
                "test image Filter Image Grains Mask",
            ],
            id="Checking grainstats function after running prior functions",
        )
    ],
)
def test_grainstats_function(
    qtbot: QtBot,
    napari_viewer: Viewer,
    topostats_widget: TopoStatsRootWidget,
    image_path: str,
    run_function_on: list[str],
):
    """Test the grainstats function separately."""
    load_test_image(napari_viewer, image_path)
    run_functions_in_grid(
        qtbot,
        topostats_widget,
        napari_viewer,
        run_function_on,
    )

    # pylint: disable=protected-access
    assert "Grainstats" in napari_viewer.window._dock_widgets, "Grainstats widget not found in dock widgets."
