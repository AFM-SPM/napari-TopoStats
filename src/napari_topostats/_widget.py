# pylint: disable=wrong-import-order, wrong-import-position, ungrouped-imports

"""
This module contains the root napari widget which is used for accessing the various functions this plugin provides.
The provided functions are listed and can be added to in the array AVAILABLE_FUNCTIONS. For full details about how
these instances of the WidgetFunction class are converted into qt viewable widgets view the _widget_function.py module.

References:
- Widget specification: https://napari.org/stable/plugins/guides.html?#widgets
- magicgui docs: https://pyapp-kit.github.io/magicgui/

Replace code below according to your needs.
"""

# ns-rse 2025-12-08 - We seem to need to allow ungrouped imports so that LoadingWidget() can be used
# pylint: disable=ungrouped-imports

import argparse
import os
import threading
from pathlib import Path

from napari import current_viewer  # pylint: disable=no-name-in-module
from qtpy.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ._alerts import LoadingWidget, attach_status_label

if os.environ.get("QT_QPA_PLATFORM") != "offscreen" and QApplication.instance() is not None:
    loading_spinner = LoadingWidget(current_viewer())
    loading_spinner.start()
    QApplication.processEvents()

from magicgui import magicgui
from magicgui.widgets import FunctionGui
from napari.layers import Image, Labels
from napari.viewer import Viewer
from packaging.version import parse as parse_version
from platformdirs import user_config_dir
from topostats import __version__ as topostats_version
from topostats.filters import Filters
from topostats.grains import Grains
from topostats.run_modules import process

from napari_topostats.utils import (
    afm2stack,
    grainstats,
)

if os.environ.get("QT_QPA_PLATFORM") != "offscreen" and QApplication.instance() is not None:
    loading_spinner.stop()

from ._alerts import show_error_dialog
from ._button_grid import ButtonGrid
from ._io import (
    config_wrapper,
    full_config_container,
    get_current_config_path,
    load_config,
    load_config_impl,
    write_new_default_config,
)
from ._state import MIN_TOPOSTATS_VERSION
from ._widget_function import WidgetFunction

if parse_version(parse_version(topostats_version).base_version) < parse_version(MIN_TOPOSTATS_VERSION):
    show_error_dialog(
        f"TopoStats version {topostats_version} is outdated and does not work with this plugin."
        f"Please install at least TopoStats version {MIN_TOPOSTATS_VERSION}.\n"
        f"This can be done with `pip install topostats=={MIN_TOPOSTATS_VERSION}`",
        raise_exception=False,
    )


# pylint: disable=unused-argument
def batch_process_impl(viewer: Viewer, data_path: str | Path = None, output_path: str | Path = None):
    """
    Batch process multiple AFM images in a selected folder using the current configuration.

    Parameters
    ----------
    viewer : napari.Viewer
        The active napari viewer instance.
    """
    if config_wrapper is None or full_config_container is None:
        load_config_impl(current_viewer(), use_default=True)
        if data_path is None:
            data_path = QFileDialog.getExistingDirectory(
                parent=None,
                caption="Select Input Data Directory",
            )
            if not data_path:
                return
            data_path = Path(data_path)
            widget = batch_process
            widget.viewer.value = viewer
            widget.data_path.value = data_path
        if output_path is None:
            output_path = QFileDialog.getExistingDirectory(
                parent=None,
                caption="Select Output Data Directory",
            )
            if not output_path:
                return
            output_path = Path(output_path)
            widget = batch_process
            widget.viewer.value = viewer
            widget.output_path.value = output_path

    args = argparse.Namespace()
    args.config_file = str(get_current_config_path())
    args.module = "topostats"
    args.summary_config = None
    thread = threading.Thread(target=process, args=(args,), name="ProcessThread-topostats")
    thread.start()


@magicgui(
    data_path={"label": "Input data path"},
    output_path={
        "label": "Output data path",
    },
    call_button="Run Batch Process",
)
def batch_process(viewer: Viewer, data_path: str | Path = None, output_path: str | Path = None):
    """Batch process multiple AFM images in a selected folder using the current configuration.

    Parameters
    ----------
    viewer : napari.Viewer
        The active napari viewer instance.
    data_path : str or Path, optional
        The path to the directory containing AFM image files.
        If None, a dialog will prompt the user to select a directory.
    """
    return batch_process_impl(viewer, data_path=data_path, output_path=output_path)


AVAILABLE_FUNCTIONS = [
    WidgetFunction(
        name="load_config",
        tooltip="Load a configuration file to use with TopoStats functions.",
        function_to_run=load_config,
    ),
    WidgetFunction(
        name="run_filters",
        function_key="filter",
        function_to_run=Filters.filter_image,
        type_class=Filters,
        path_to_data='obj.images["gaussian_filtered"]',
        uses_config=True,
        of_type=[Image],
        tooltip="Run filters on the selected image layer using the current configuration.",
    ),
    WidgetFunction(
        name="run_grains",
        function_key="grains",
        function_to_run=Grains.find_grains,
        type_class=Grains,
        path_to_data='obj.mask_images["above"]["merged_classes"][:, :, 1]',
        of_type=[Image],
        metadata_paths={"config": "config", "grains": "obj"},
        uses_config=True,
        tooltip="Run grain analysis on the selected image layer using the current configuration.",
    ),
    WidgetFunction(
        name="make_3d",
        function_key="3d",
        function_to_run=afm2stack,
        path_to_data="return",
        of_type=[Image],
        ndims=3,
        tooltip="Convert the selected image layer to a 3D stack",
    ),
    WidgetFunction(
        name="run_grainstats",
        function_key="grainstats",
        path_to_data="return",
        of_type=[Labels],
        function_to_run=grainstats,
        tooltip="Creates a table showing the grainstats of the selected grain labels layer.",
    ),
    WidgetFunction(
        name="batch_process",
        function_to_run=batch_process,
        tooltip="Batch process multiple AFM images in a selected folder using the current configuration.",
    ),
]


class TopoStatsRootWidget(QWidget):
    """
    A root widget where all topostats functions can be accessed.
    This widget serves as a container for the button grid and provides
    a layout for the various controls.
    """

    def __init__(self, viewer: Viewer, parent=None):
        # Initialize the widget with a viewer
        if parent:
            super().__init__(parent)
        else:
            super().__init__()
        self._viewer = viewer
        # Make layout so children are arranged vertically
        layout = QVBoxLayout(self)
        # Add the function grid to the layout with the available functions
        self._functions = self.get_functions()
        self.function_grid = ButtonGrid(self, functions=self._functions, viewer=self._viewer)
        # Set the size policy to allow the widget to expand
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.function_grid.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Set the layout margins and add the function grid
        layout.setContentsMargins(5, 5, 5, 5)
        layout.addWidget(self.function_grid)

        # Bottom-right button row
        bottom_row = QHBoxLayout()

        # Create a container for the status label that doesn't expand
        status_container = QWidget()
        status_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        status_layout = QHBoxLayout(status_container)
        status_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(status_container)
        bottom_row.addStretch()  # Push button to the right

        reset_button = QPushButton("Reset Default Config")
        reset_button.setToolTip("Reset the default configuration to the original TopoStats default.")

        def on_reset_clicked():
            config_dir = Path(user_config_dir("TopoStats", "Napari"))
            default_config_path = config_dir / "config.yaml"
            if default_config_path.exists():
                write_new_default_config(default_config_path)
                load_config_impl(self._viewer, config_path=None, use_default=True)
                bottom_widget.set_status_message("✅ Default configuration reset successfully.")
            else:
                bottom_widget.set_status_message("No default configuration file found to reset.")

        reset_button.clicked.connect(on_reset_clicked)
        bottom_row.addWidget(reset_button)

        bottom_widget = QWidget()
        bottom_widget.setLayout(bottom_row)
        bottom_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Attach status label to the status container instead of bottom_widget
        attach_status_label(status_container)

        # Store reference to status_container for the button callback
        bottom_widget.set_status_message = status_container.set_status_message

        layout.addWidget(bottom_widget)

        # Set the layout for the widget
        self.setLayout(layout)

    def get_functions(self):
        """
        Get the available functions for the button grid.

        Returns
        -------
        functions : dict[str, WidgetFunction | FunctionGui]
            A dictionary of function names and their corresponding WidgetFunction or FunctionGui objects.
        """
        functions = {}
        for function in AVAILABLE_FUNCTIONS:
            function_name = function.name
            display_name = function_name.replace("_", " ").title()
            if function.path_to_data is not None:
                # This option is used for functions that will be dynamically converted to a widget
                functions[display_name] = function
            else:
                # This option is used for functions that are hardcoded
                func = function.function_to_run
                if isinstance(func, FunctionGui):
                    functions[display_name] = func
                elif callable(func):
                    functions[display_name] = magicgui(func)
        return functions
