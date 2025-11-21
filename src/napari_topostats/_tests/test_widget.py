"""Tests for the widget functionalities of the plugin."""

# pylint: disable=redefined-outer-name
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from ._helpers import load_test_image, run_functions_in_grid


def test_button_grid_exists(topostats_widget):
    """Ensure the function grid loads correctly."""
    assert (
        topostats_widget.function_grid.functions is not None
    ), "Function grid did not initialize"


@pytest.mark.parametrize(
    "image_path",
    [
        pytest.param(
            str(Path("src/napari_topostats/_tests/_test_data/test_spm.spm")),
            id="Testing loading with valid image path",
        )
    ],
)
def test_load_image(napari_viewer, image_path):
    """Verify that a test AFM image loads properly."""
    layer = load_test_image(napari_viewer, image_path)
    assert layer is not None, "Failed to load test image"


# pylint: disable=too-many-positional-arguments
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
def test_functions_in_grid(
    qtbot: QtBot,
    napari_viewer,
    topostats_widget,
    image_path,
    run_function_on,
    expected_layers,
):
    """End-to-end test: load image, run functions, and verify layers."""
    load_test_image(napari_viewer, image_path)
    run_functions_in_grid(
        qtbot,
        topostats_widget,
        napari_viewer,
        run_function_on,
        expected_layers,
    )
