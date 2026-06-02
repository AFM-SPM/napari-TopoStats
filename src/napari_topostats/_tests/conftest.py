"""Repeated fixtures for napari_topostats tests."""

import os

import matplotlib
import napari
import pytest
from pytestqt.qtbot import QtBot

from napari_topostats._state import WidgetManager
from napari_topostats._widget import TopoStatsRootWidget

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session", autouse=True)
def configure_matplotlib():
    """
    Force matplotlib to use the non-interactive 'Agg' backend
    to prevent Tcl/Tk threading errors during tests.
    """
    matplotlib.use("Agg")


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


@pytest.fixture
def widget_manager(napari_viewer):
    """Create a WidgetManager bound to the current test's viewer, updating the global singleton."""
    return WidgetManager(napari_viewer)
