# pylint: disable=wrong-import-order, wrong-import-position, ungrouped-imports
# ruff: noqa: E402

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

import inspect
import os
from pathlib import Path

from napari import current_viewer  # pylint: disable=no-name-in-module
from qtpy.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
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

from forcestats.analysis import find_trigger_point
from forcestats.contact import create_3d_approach_map, find_contact_point
from forcestats.curve_correction import correct_curve
from napari.layers import Image, Labels
from napari.viewer import Viewer
from packaging.version import parse as parse_version
from platformdirs import user_config_dir
from topostats import __version__ as topostats_version
from topostats.filters import Filters
from topostats.grains import Grains

if os.environ.get("QT_QPA_PLATFORM") != "offscreen" and QApplication.instance() is not None:
    loading_spinner.stop()


from napari_topostats._alerts import show_error_dialog
from napari_topostats._batch_process import batch_process
from napari_topostats._button_grid import ButtonGrid
from napari_topostats._curves import open_curve_viewer
from napari_topostats._grainstats import grainstats
from napari_topostats._guide import check_guide, show_guide
from napari_topostats._io import (
    load_config,
    load_config_impl,
    open_config_editor,
    write_new_default_config,
)
from napari_topostats._profile_viewer import start_drawing
from napari_topostats._script_handler import get_loaded_functions
from napari_topostats._state import MIN_TOPOSTATS_VERSION, WidgetManager, get_running_function, set_topostats_widget
from napari_topostats._widget_function import WidgetFunction, WidgetFunctionManager
from napari_topostats.utils import (
    afm2stack,
)

check_guide(current_viewer())

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

MAIN_FUNCTIONS = [
    WidgetFunction(
        name="load_config",
        tooltip="Load a configuration file to use with TopoStats functions.",
        function_to_run=load_config,
        run_immediately=False,
    ),
    WidgetFunction(
        name="run_filters",
        function_key="filter",
        function_to_run=Filters.filter_image,
        type_class=Filters,
        path_to_data='obj.images["gaussian_filtered"]',
        config_type="topostats",
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
        config_type="topostats",
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
    WidgetFunction(
        name="view_curves",
        function_to_run=open_curve_viewer,
        tooltip="Open curve window for viewing AFM curves for each point of the image",
        overide_get_widget=True,
    ),
]

EXTRA_FUNCTIONS = [
    WidgetFunction(
        name="find_trigger_point",
        function_key="find_trigger_point",
        path_to_data="return",
        function_to_run=find_trigger_point,
        tooltip=inspect.getdoc(find_trigger_point),
        config_type="forcestats",
        run_immediately=False,
    ),
    WidgetFunction(
        name="find_contact_point",
        function_key="find_contact_point",
        path_to_data="return",
        function_to_run=find_contact_point,
        tooltip=inspect.getdoc(find_contact_point),
        run_immediately=False,
        config_type="forcestats",
    ),
    WidgetFunction(
        name="create_3d_approach_map",
        function_key="create_3d_approach_map",
        path_to_data="return",
        function_to_run=create_3d_approach_map,
        tooltip=inspect.getdoc(create_3d_approach_map),
        run_immediately=False,
        config_type="forcestats",
    ),
    WidgetFunction(
        name="correct_curve",
        function_key="correct_curve",
        path_to_data="return",
        function_to_run=correct_curve,
        tooltip=inspect.getdoc(correct_curve),
        run_immediately=False,
        config_type="forcestats",
    ),
]


MAX_LOADED_FUNCTIONS = 3  # Maximum number of functions that can be loaded from external scripts to prevent overload


class RootWidget(QWidget):
    """
    A root widget where all force stats functions can be accessed.

    This widget serves as a container for the button grid and provides
    a layout for the various controls.

    Parameters
    ----------
    viewer : Viewer
        The napari viewer.
    functions : dict[str, WidgetFunction]
        The available functions to be displayed in the button grid.
    parent : QWidget, optional
        The parent widget, by default None.
    """

    def __init__(self, viewer: Viewer, functions: dict[str, WidgetFunction], parent=None):
        """
        Initialises RootWidget

        Parameters
        ----------
        viewer : Viewer
            The napari viewer.
        functions : dict[str, WidgetFunction]
            The available functions to be displayed in the button grid.
        parent : QWidget, optional
            The parent widget, by default None.
        """
        # Initialize the widget with a viewer
        if parent:
            super().__init__(parent)
        else:
            super().__init__()
        self._viewer = viewer
        # Setup the key binding for the line tool to allow users to draw a line and view the profile
        self._viewer.bind_key("a", start_drawing, overwrite=True)
        # Make layout so children are arranged vertically
        self.vlayout = QVBoxLayout(self)
        # Add the function grid to the layout with the available functions
        self._functions = self.get_functions(functions)
        self.widget_manager = WidgetManager(viewer)
        self.function_manager = WidgetFunctionManager(self._functions, self._viewer, self.widget_manager)
        self.function_grid = ButtonGrid(
            self, functions=self._functions, viewer=self._viewer, function_manager=self.function_manager
        )
        # Set the size policy to allow the widget to expand
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.function_grid.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Set the layout margins and add the function grid
        self.vlayout.setContentsMargins(5, 5, 5, 5)
        self.vlayout.addWidget(self.function_grid)

        # Bottom-right button row
        self.bottom_row = QHBoxLayout()

        # Create a container for the status label that doesn't expand
        status_container = QWidget()
        status_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        status_layout = QHBoxLayout(status_container)
        status_layout.setContentsMargins(0, 0, 0, 0)
        self.vlayout.addWidget(status_container)
        self.bottom_row.addStretch()  # Push button to the right

        self.bottom_widget = QWidget()
        self.bottom_widget.setLayout(self.bottom_row)
        self.bottom_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Attach status label to the status container instead of bottom_widget
        attach_status_label(status_container)

        # Store reference to status_container for the button callback
        self.bottom_widget.set_status_message = status_container.set_status_message

        self.vlayout.addWidget(self.bottom_widget)

        # Set the layout for the widget
        self.setLayout(self.vlayout)

    def get_functions(self, _functions: dict[str, WidgetFunction | tuple[str, list[WidgetFunction]]]):
        """
        Get the available functions for the button grid.

        Returns
        -------
        functions : dict[str, WidgetFunction | FunctionGui]
            A dictionary of function names and their corresponding WidgetFunction or FunctionGui objects.
        """
        functions = {}
        for function in _functions:
            function_name = function.name
            display_name = function_name.replace("_", " ").title()
            functions[display_name] = function
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

    def add_function(self, function_to_add: WidgetFunction, to_group: bool = False):
        """Add a function to the button grid (designed for retrospective use, after loading widget)"""
        function_to_add.function_manager = self.function_manager
        function_name = function_to_add.name
        display_name = function_name.replace("_", " ").title()
        self._functions[display_name] = function_to_add
        if to_group:
            params = inspect.signature(function_to_add.function_to_run).parameters
            if "curve" in params or "curves" in params:
                group_to_add_to = "Loaded Curve Functions"
            else:
                group_to_add_to = "Loaded Image Functions"
            group_function = self._functions.get(group_to_add_to)
            if not group_function:
                type_of_function = "curves" if "curve" in params or "curves" in params else "images"
                group_function = WidgetFunction(
                    name=group_to_add_to.lower().replace(" ", "_"),
                    function_to_run=[function_to_add],
                    tooltip=f"Functions loaded from external scripts that operate on {type_of_function}.",
                    function_manager=self.function_manager,
                )
                self._functions[group_to_add_to] = group_function
                self.function_grid.add_function(group_function, label=group_to_add_to)
            if group_function and group_function.is_group:
                group_function.add_to_group(function_to_add)
                return

        self.function_grid.add_function(function_to_add, label=display_name)


class TopoStatsRootWidget(RootWidget):
    """
    A root widget where all topostats functions can be accessed.

    This widget serves as a container for the button grid and provides
    a layout for the various controls.

    Parameters
    ----------
    viewer : Viewer
        The napari viewer.
    parent : QWidget, optional
        The parent widget, by default None.
    """

    def __init__(self, viewer: Viewer, parent=None):  # pylint: disable=too-many-statements
        """
        Initialises TopoStatsRootWidget

        Parameters
        ----------
        viewer : Viewer
            The napari viewer.
        parent : QWidget, optional
            The parent widget, by default None.
        """
        # Initialize the widget with a viewer
        available_functions = MAIN_FUNCTIONS.copy()
        if parent:
            super().__init__(viewer=viewer, parent=parent, functions=available_functions)
        else:
            super().__init__(viewer=viewer, functions=available_functions)
        loaded_functions = get_loaded_functions()
        extra_topostats_functions = []
        extra_forcestats_functions = []
        for func in loaded_functions + EXTRA_FUNCTIONS:
            params = inspect.signature(func.function_to_run).parameters
            if func.name not in [f.name for f in available_functions]:
                if "curve" in params or "curves" in params:
                    extra_forcestats_functions.append(func)
                else:
                    extra_topostats_functions.append(func)
        if extra_topostats_functions:
            self.add_function(
                WidgetFunction(
                    name="loaded_image_functions",
                    function_to_run=extra_topostats_functions,
                    tooltip="Functions loaded from external scripts that operate on images.",
                    function_manager=self.function_manager,
                    run_immediately=False,  # Prevent immediate execution for loaded image functions
                )
            )
        if extra_forcestats_functions:
            self.add_function(
                WidgetFunction(
                    name="loaded_curve_functions",
                    function_to_run=extra_forcestats_functions,
                    tooltip="Functions loaded from external scripts that operate on curves.",
                    function_manager=self.function_manager,
                    run_immediately=False,  # Prevent immediate execution for loaded curve functions
                )
            )
        config_type_selector = QComboBox()
        config_type_selector.addItems(["TopoStats", "ForceStats"])
        config_type_selector.setToolTip("Select the configuration type to edit or reset.")

        reset_button = QPushButton("Reset Default")
        reset_button.setToolTip("Restore the selected factory configuration as the active and user default.")

        def on_reset_clicked():
            config_type = config_type_selector.currentText().lower()
            config_dir = Path(user_config_dir("TopoStats", "Napari"))
            default_config_path = config_dir / f"{config_type}_config.yaml"
            config_dir.mkdir(parents=True, exist_ok=True)
            write_new_default_config(default_config_path, config_type=config_type)
            if load_config_impl(self._viewer, config_path=None, config_type=config_type, use_default=True):
                self.bottom_widget.set_status_message("✅ Default configuration reset successfully.")

        reset_button.clicked.connect(on_reset_clicked)

        guide_button = QPushButton("Show Guide")
        guide_button.setToolTip("Open the TopoStats guide.")
        guide_button.clicked.connect(lambda: show_guide(viewer))
        # Add a text label to tell the user they can press 'a' to open the curve viewer and use the line tool
        line_tool_label = QLabel("Hold 'a' to draw a line and view the profile plot")
        line_tool_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        line_tool_label.setWordWrap(True)
        self.bottom_row.addWidget(line_tool_label)
        self.bottom_row.addWidget(guide_button)

        config_row = QHBoxLayout()
        edit_button = QPushButton("Edit")
        edit_button.clicked.connect(
            lambda: open_config_editor(self._viewer, self, config_type_selector.currentText().lower())
        )
        config_row.addWidget(config_type_selector)
        config_row.addWidget(edit_button)
        config_row.addWidget(reset_button)
        self.vlayout.addLayout(config_row)

        set_topostats_widget(widget=self)

        failed_configs = []
        for config_type in ("topostats", "forcestats"):
            if not load_config_impl(self._viewer, config_type=config_type, use_default=True, report_errors=False):
                failed_configs.append(config_type.title())
        if failed_configs:
            self.bottom_widget.set_status_message(
                f"Could not load the stored default for {', '.join(failed_configs)}. Reset Default can repair it."
            )
