"""Tests for the I/O functionalities of the plugin."""

# pylint: disable=protected-access
# pylint: disable=redefined-outer-name
from pathlib import Path
from unittest.mock import patch

import pytest
from pytestqt.qtbot import QtBot

from napari_topostats import _io as io

from ._helpers import open_load_config_widget


def test_load_config_widget(qtbot: QtBot, napari_viewer, topostats_widget):
    """Test that the load config widget is created properly when it is clicked in the root widget."""

    open_load_config_widget(qtbot, topostats_widget)

    # Check that the load config widget exists in dock

    assert "Load Config" in napari_viewer.window._dock_widgets, "Load Config widget not found in dock widgets."


@pytest.mark.parametrize(
    ("test_config_path", "use_default", "input_path_on_selection", "expected_result"),
    [
        pytest.param(
            Path("src/napari_topostats/_tests/_test_data/test_config.yaml"),
            False,
            False,
            "SUCCESS",
            id="Test valid path as if inputted by user in gui widget",
        ),
        # pytest.param(
        #     Path("src/napari_topostats/_tests/_test_data/test_config.yaml"),
        #     False,
        #     True,
        #     "SUCCESS",
        #     id="Test valid path as if inputted by user in gui on click",
        # ),
        pytest.param(
            Path("This/is/definitely/not/a_real/path"),
            False,
            False,
            "FAILURE",
            id="Test invalid path as if inputted by user in gui widget",
        ),
        # pytest.param(
        #     Path("This/is/definitely/not/a_real/path"),
        #     False,
        #     True,
        #     "FAILURE",
        #     id="Test invalid path as if inputted by user in gui on click",
        # ),
        pytest.param(
            None,
            True,
            False,
            "SUCCESS",
            id="Test valid path as if function run automatically",
        ),
    ],
)
# ns-rse 2025-11-26 : See issue #72
def test_load_config(
    napari_viewer,
    test_config_path: Path,
    use_default: bool,
    input_path_on_selection: bool,
    expected_result: str,
):
    """Test that loading a config file updates the function parameters correctly."""

    def print_error_message(message: str, raise_exception: bool = False):
        print(f"Error: {message}")
        if raise_exception:
            raise ValueError(message)

    with (
        patch(
            "napari_topostats._io.QFileDialog.getOpenFileName",
            return_value=(str(test_config_path), "YAML Files (*.yaml *.yml)"),
        ),
        patch(
            "napari_topostats._io.show_error_dialog",
            side_effect=print_error_message,
        ),
    ):
        if use_default:
            assert io.load_config_impl(napari_viewer, None, use_default=use_default), "Default config load failed"
            full_current_config = io.config_wrapper.unflatten()
            assert full_current_config is not None, "Failed to retrieve current config after loading default."

        else:
            # Simulate selecting a config file (assuming a test config file path)
            if input_path_on_selection:
                result = io.load_config_impl(napari_viewer)
            else:
                result = io.load_config_impl(napari_viewer, test_config_path)
            if result:
                full_current_config = io.config_wrapper.unflatten()

                with open(test_config_path, encoding="utf-8") as f:
                    expected_config = io.yaml.safe_load(f)
                overlap_keys = set(full_current_config.keys()).intersection(set(expected_config.keys()))
                if "run" in overlap_keys:
                    overlap_keys.remove("run")
                for key in overlap_keys:
                    assert (
                        full_current_config[key] == expected_config[key]
                    ), f"Config key '{key}' does not match expected value."
            else:
                assert expected_result == "FAILURE", "Config load was expected to succeed but failed."
