"""Repeated fixtures for napari_topostats tests."""

# pylint: disable=redefined-outer-name
import napari
import pytest
from pytestqt.qtbot import QtBot

from napari_topostats._widget import TopoStatsRootWidget


@pytest.fixture
def napari_viewer(qtbot: QtBot):
    """Create a Napari viewer with Qtbot cleanup."""
    # pylint: disable=not-callable
    viewer = napari.Viewer(show=False)
    qtbot.addWidget(viewer.window._qt_window)
    yield viewer
    viewer.close()


@pytest.fixture
def topostats_widget(napari_viewer, qtbot: QtBot):
    """Create the TopoStatsRootWidget and return its function grid."""
    widget = TopoStatsRootWidget(napari_viewer)
    qtbot.addWidget(widget)
    qtbot.wait(50)  # Allow Qt event loop to process
    return widget
