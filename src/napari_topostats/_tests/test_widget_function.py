import pytest
import napari
import napari_topostats._widget_function as widget_function
from napari_topostats._widget import AVAILABLE_FUNCTIONS
from napari_topostats._tests.test_full_flow import setup_tests


def test_get_widget():
    viewer = setup_tests()
