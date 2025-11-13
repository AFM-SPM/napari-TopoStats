"""Tests for the I/O functionalities of the plugin."""

# pylint: disable=redefined-outer-name
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot
from qtpy.QtCore import Qt

from napari_topostats import _io as io

from .conft_test import napari_viewer

# --- Helper Functions ---


def open_load_config_widget(qtbot: QtBot, topostats_widget):
    """Simulate clicking the Load Config button in the function grid."""
    button_grid = topostats_widget.function_grid
    load_config_button = button_grid.findItems("Load Config", Qt.MatchExactly)[
        0
    ]
    rect = button_grid.visualItemRect(load_config_button)
    qtbot.mouseClick(button_grid.viewport(), Qt.LeftButton, pos=rect.center())
    qtbot.wait(100)


# --- Actual Tests ---


def test_load_config_widget(qtbot: QtBot, topostats_widget):
    """Test that the load config widget is created properly when it is clicked in the root widget."""

    open_load_config_widget(qtbot, topostats_widget)

    # Check that the load config widget exists in dock
    assert (
        "Load Config" in napari_viewer.window._dock_widgets
    ), "Load Config widget not found in dock widgets."


@pytest.mark.parametrize(
    ("test_config_path", "use_default", "expected_result"),
    [
        (
            Path("src/napari_topostats/_tests/_test_data/test_config.yaml"),
            False,
            "SUCCESS",
        ),
        (Path("This/is/definitely/not/a_real/path"), False, "FAILURE"),
        (None, True, "SUCCESS"),
    ],
)
def test_load_config(
    napari_viewer,
    test_config_path,
    use_default,
    expected_result,
):
    """Test that loading a config file updates the function parameters correctly."""

    if use_default:
        assert io._load_config_impl(
            napari_viewer, None
        ), "Default config load failed"
        updated_values = io.collect_values(io.full_config_container)
        io.config_wrapper.flat.update(updated_values)
        full_current_config = io.config_wrapper.unflatten()
        assert (
            full_current_config is not None
        ), "Failed to retrieve current config after loading default."

    else:

        # Simulate selecting a config file (assuming a test config file path)
        result = io._load_config_impl(napari_viewer, test_config_path)
        if result:
            updated_values = io.collect_values(io.full_config_container)
            io.config_wrapper.flat.update(updated_values)
            full_current_config = io.config_wrapper.unflatten()

            with open(test_config_path, encoding="utf-8") as f:
                expected_config = io.yaml.safe_load(f)
            overlap_keys = set(full_current_config.keys()).intersection(
                set(expected_config.keys())
            )
            for key in overlap_keys.remove("run"):
                assert (
                    full_current_config[key] == expected_config[key]
                ), f"Config key '{key}' does not match expected value."
        else:
            assert (
                expected_result == "FAILURE"
            ), "Config load was expected to succeed but failed."
