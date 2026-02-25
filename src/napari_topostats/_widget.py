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

import os
from pathlib import Path

from napari import current_viewer  # pylint: disable=no-name-in-module
from qtpy.QtWidgets import (
    QApplication,
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

from napari_topostats.utils import (
    afm2stack,
    grainstats,
)

if os.environ.get("QT_QPA_PLATFORM") != "offscreen" and QApplication.instance() is not None:
    loading_spinner.stop()

from ._alerts import show_error_dialog
from ._batch_process import batch_process
from ._button_grid import ButtonGrid
from ._io import (
    load_config,
    load_config_impl,
    write_new_default_config,
)
from ._state import MIN_TOPOSTATS_VERSION, get_running_function
from ._widget_function import WidgetFunction

if parse_version(parse_version(topostats_version).base_version) < parse_version(MIN_TOPOSTATS_VERSION):
    show_error_dialog(
        f"TopoStats version {topostats_version} is outdated and does not work with this plugin."
        f"Please install at least TopoStats version {MIN_TOPOSTATS_VERSION}.\n"
        f"This can be done with `pip install topostats=={MIN_TOPOSTATS_VERSION}`",
        raise_exception=False,
    )

# List of available functions to be displayed in the button grid.
# Each function is represented as an instance of the WidgetFunction class defined in _widget_function.py,
# which contains all the necessary information for rendering the function as a button and executing it when clicked.
# Function to run shows the function that will be executed when the button is clicked and path_to_data shows where the
# data that will be rendered is located. (path_to_data is designed for when functions will be dynamically converted).
# Attributes from the config can be dynamically inserted into path_to_data or metadata_paths using the syntax
# <config_category.attribute> (this will reference config["config_category"]["attribute"]).

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
        path_to_data='obj.mask_images["<DIRECTION>"]["merged_classes"][:, :, 1]',
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

    def get_running_function_widget(self) -> str | None:
        """
        Get the name of the currently running function, if any.

        Returns
        -------
        str | None
            The name of the currently running function, or None if no function is running.
        """

        return get_running_function()
