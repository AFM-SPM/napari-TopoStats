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
    viewer = napari.Viewer(show=False)
    qtbot.addWidget(
        viewer.window._qt_window
    )  # pylint: disable=protected-access
    yield viewer
    viewer.close()


@pytest.fixture
def topostats_widget(napari_viewer, qtbot: QtBot):
    """Create the TopoStatsRootWidget and return its function grid."""
    widget = TopoStatsRootWidget(napari_viewer)
    qtbot.addWidget(widget)
    qtbot.wait(50)  # Allow Qt event loop to process
    return widget
