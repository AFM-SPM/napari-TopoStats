"""Repeated fixtures for napari_topostats tests."""

import os

import napari
import pytest
from pytestqt.qtbot import QtBot

from napari_topostats._widget import TopoStatsRootWidget

os.environ["QT_QPA_PLATFORM"] = "offscreen"


@pytest.fixture(name="napari_viewer")
def napari_viewer_fixture(qtbot: QtBot):
    """Create a Napari viewer with QtBot cleanup."""
    viewer = napari.Viewer(show=False)  # pylint: disable=not-callable
    qtbot.addWidget(viewer.window._qt_window)  # pylint: disable=protected-access

    return viewer


@pytest.fixture
def topostats_widget(napari_viewer, qtbot: QtBot):
    """Create the TopoStatsRootWidget and return its function grid."""
    widget = TopoStatsRootWidget(napari_viewer)
    qtbot.addWidget(widget)
    qtbot.wait(50)  # Allow Qt event loop to process

    yield widget

    # Cleanup: Clear docked functions to avoid stale references
    try:
        if hasattr(widget, "function_grid") and hasattr(widget.function_grid, "docked_functions"):
            # Remove references to potentially deleted widgets
            widget.function_grid.docked_functions.clear()
    except RuntimeError:
        # Widget already deleted
        pass

    qtbot.wait(50)  # Allow cleanup to complete
