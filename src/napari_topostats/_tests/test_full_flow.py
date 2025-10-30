import os
from pathlib import Path
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest
from qtpy.QtWidgets import QApplication
import napari
from napari_afmreader._reader import reader_function
from napari_topostats._widget import AVAILABLE_FUNCTIONS, TopoStatsRootWidget
from qtpy.QtCore import Qt


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app

@pytest.fixture
def viewer():
    viewer = napari.Viewer(show=False)
    yield viewer
    viewer.close()
    

def load_test_image(viewer, image_path):
    layers = reader_function(image_path, channel="Height")
    for data, metadata, layer_type in layers:
        if layer_type == "image":
            test_image_layer = viewer.add_image(data, name="test image", metadata=metadata)
    return test_image_layer

@pytest.mark.parametrize(("run_function_on", "expected_layers"),
                         [(["test image", "test image", "test image Filter Image", "test image Filter Image"],
                           ["test image", "test image Filter Image", "test image Filter Image Grains Mask", "test image Filter 3D Image"])])
def test_functions_in_grid(button_grid, viewer, run_function_on, expected_layers):
    function_names = [f.name for f in AVAILABLE_FUNCTIONS]
    for i in range(0, len(function_names)):
        name = function_names[i]
        name = name.replace("_", " ").title()
        viewer.layers.selection = [viewer.layers[run_function_on[i]]]
        item = button_grid.findItems(name, Qt.MatchExactly)[0]
        button_grid.add_function_as_widget(item)

    for expected_name in expected_layers:
        assert expected_name in viewer.layers, f"Layer '{expected_name}' not found"

@pytest.fixture
def button_grid(viewer, qapp):
    widget = TopoStatsRootWidget(viewer)
    qapp.processEvents()
    return widget.function_grid

def test_button_grid(viewer, qapp):
    grid = button_grid()
    assert grid.functions is not None, "Button grid cannot render"

@pytest.mark.parametrize(("image_path"), [
    (str(Path("src\\napari_topostats\\_tests\\_test_data\\4.spm")))
])
def test_load_image(viewer, image_path):
    assert load_test_image(viewer, image_path) is not None, "Failed to load test image"

@pytest.mark.parametrize(("image_path", "run_function_on", "expected_layers"), [
    (str(Path("src\\napari_topostats\\_tests\\_test_data\\4.spm")),
      ["test image", "test image", "test image Filter Image", "test image Filter Image"],
      ["test image", "test image Filter Image", "test image Filter Image Grains Mask", "test image Filter 3D Image"])
])
def test_overall(qapp, viewer, image_path, run_function_on, expected_layers):
    load_test_image(viewer, image_path)
    widget = test_button_grid(viewer, qapp)
    test_functions_in_grid(widget.function_grid, viewer, run_function_on)
    
    



