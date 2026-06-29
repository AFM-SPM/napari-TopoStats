# pylint: disable=no-else-return,too-many-lines,too-many-locals,function-redefined
"""
Module for dynamic widget generation from topostats functions including creating a window of options
for those functions, running them and rendering the result.
"""

import functools
import inspect
import re
from collections.abc import Callable
from typing import Any, get_origin, get_type_hints

import numpy as np
import pandas as pd
from magicgui import magicgui
from magicgui.widgets import Container, FunctionGui, PushButton
from napari import current_viewer  # pylint: disable=no-name-in-module
from napari.layers import Image, Labels, Layer
from napari.layers.labels._labels_constants import Mode
from napari.viewer import Viewer
from napari_afmreader._reader import get_loaded_image
from qtpy.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from scipy.ndimage import label
from topostats.classes import TopoStats

from . import _io as io
from ._alerts import LoadingWidget, attach_status_label, construct_error_args, show_error_dialog
from ._components import (
    SelectionDialog,
    get_selected_curves,
    get_selected_image,
    get_selected_loaded_image,
    show_parameter_dialog,
)
from ._io import add_values_to_dict_from_config, fetch_saved_scripts, get_current_config, save_scripts, unsave_scripts
from ._parallel_processing import ProcessWorker
from ._state import WidgetManager, get_running_function, set_running_function
from .utils import _eval, all_curves, calculate_contrast_limits, is_binary_image, remove_all_but_last

CURVES_VOLUME_PARAM = "curves_volume_to_operate_on"


def enforce_defaults(args: dict[str, Any], params: list[Any]) -> dict[str, Any]:
    """
    Ensure that all required parameters have default values.

    Parameters
    ----------
    args : dict[str, Any]
        The current dictionary of arguments to which the default values will be checked for and added.
    params : list[Any]
        The list of parameters for the function.

    Returns
    -------
    args : dict[str, Any]
        The updated dictionary of arguments with default values added for any missing parameters.
    """
    param_names = [p.name for p in params]
    if "direction" in param_names:
        args.setdefault("direction", "above")

    if "threshold_std_dev" in param_names:
        args.setdefault("threshold_std_dev", {})
        if args.get("threshold_std_dev") is None:
            args["threshold_std_dev"] = {}
        args["threshold_std_dev"].setdefault("above", 1.0)
        args["threshold_std_dev"].setdefault("below", 10.0)

    if "threshold_absolute" in param_names:
        args.setdefault("threshold_absolute", {})
        if args.get("threshold_absolute") is None:
            args["threshold_absolute"] = {}
        args["threshold_absolute"].setdefault("above", 1.0)
        args["threshold_absolute"].setdefault("below", -1.0)
    if "remove_scars" in param_names:
        args.setdefault("remove_scars", {})
        if args.get("remove_scars") is None:
            args["remove_scars"] = {}
        args["remove_scars"].setdefault("run", False)

    for key, value in args.items():
        if isinstance(value, (Image)):
            args[key] = np.asarray(value.data)
    return args


class CallableWithSignature:
    """
    A callable that wraps a function and its signature.

    This allows the signature of the function to be updated for its parameters
    and their defaults so that it can be used correctly with magicgui.

    Parameters
    ----------
    real_func : callable
        The function to wrap.
    sig : inspect.Signature
        The signature to use for the wrapped function.
    """

    def __init__(self, real_func, sig):
        """
        Initialises CallableWithSignature

        Parameters
        ----------
        real_func : callable
            The function to wrap.
        sig : inspect.Signature
            The signature to use for the wrapped function.
        """
        functools.update_wrapper(self, real_func)  # Sets __name__, __doc__, etc.
        self.real_func = real_func
        self.__signature__ = sig

    def __call__(self, *args, **kwargs):
        bound = self.__signature__.bind(*args, **kwargs)
        bound.apply_defaults()
        return self.real_func(**bound.arguments)


def evaluate_path_to_data(path_to_data, return_value, instance=None, type_class=None):
    """
    Evaluate a path expression to extract data from return values or object instances.

    Parameters
    ----------
    path_to_data : str
        Path expression starting with 'return' or 'obj'
    return_value : any
        The return value to evaluate against
    instance : any, optional
        The object instance to evaluate against (required for 'obj' paths)
    type_class : any, optional
        Type class indicator (required for 'obj' paths)

    Returns
    -------
    any
        The evaluated result, or None if there's an error
    """
    if "<DIRECTION>" in path_to_data:
        raised_error = None
        for direction in ["above", "below"]:
            new_path = path_to_data.replace("<DIRECTION>", direction)
            try:
                return evaluate_path_to_data(new_path, return_value, instance, type_class)
            except KeyError as e:
                raised_error = e
        if raised_error:
            raise ValueError("Couldn't find data for either direction") from raised_error
    if path_to_data.startswith("return"):
        return _eval(return_value, path_to_data[6:]) if len(path_to_data) > 6 else return_value

    if path_to_data.startswith("obj"):
        if type_class:
            return _eval(instance, path_to_data[3:]) if len(path_to_data) > 3 else instance
        else:
            raise ValueError(f"Invalid path_to_data: {path_to_data} - 'obj' requires type_class")

    raise ValueError(f"Invalid path_to_data: {path_to_data}")


# Class representation of each function in the button grid.
class WidgetFunction:
    """
    A class that represents each topostats function with its parameters and metadata and allows it to be used as a
    magicgui widget in the napari viewer.

    Parameters
    ----------
    name : str
        The name of the function, used for display and identification. These should be in snake_case. They are used to
        show the title of the widget (would become Snake Case) as well as get the icon for the widget for use in the
        button grid. Therefore, their should be a name.png file in the icons directory with the same name.
    function_key : str | None, optional
        The key for the function in the configuration dictionary.
    function_to_run : Callable | None, optional
        The function to run when the widget is triggered. This can be a FunctionGui or a regular function. This
        function can be directly from the topostats module or a custom function that is defined in the napari-TopoStats
        plugin.
    type_class : Any | None, optional
        The class type that the function belongs to, if applicable. This is used to instantiate the class and call the
        method. This may not be required for all functions, so it can be None. It is used if an instance of the
        enclosing class is required to run the function.
    path_to_data : str | None, optional
        The path to the data that the function returns. This is used to determine how to extract the data from the
        return value of the function. It can be "return" to return the data directly (from the function), "obj" to
        return the object itself, or a specific path to access a nested attribute or subscript in the return value
        or the object instance.
    uses_config : bool, optional
        Whether the function uses a configuration file to set its parameters. If True, the function will
        load the configuration file and use it to set the parameters. If False, the function will
        use only the parameters set in the widget. Note that certain parameters can also be taken from the napari
        viewer, such as the selected image or from the image metadata, such as the pixel to nm scaling factor.
    ndims : int, optional
        The number of dimensions of the data to be rendered. Can be left as default 2, but can be set to 3 if the
        function returns 3D data.
    of_type : list, optional
        A list of layer types that the function can be applied to, used for determining which image to select from the
        napari viewer. Optional as just used as protection layer to ensure correct layer type is selected
    metadata_paths : dict, optional
        A dictionary of additional metadata to extract from the return value or object instance, where the key is the
        name of the metadata and the value is the path to extract it. These are then passed over to the layer rendering
        function.
    tooltip : str | None, optional
        A tooltip for the widget, providing additional information about the function. This is displayed when the
        user hovers over the button for the function in the button grid.
    overide_get_widget : bool, optional
        This should be set to true if you want the function itself to handle adding a docked widget rather than that
        being handled automatically in the WidgetFunctionManager.
    function_manager : WidgetManager, optional
        The WidgetManager instance that manages the widget functions. This is used to add functions to groups when the
        function is part of a group of functions.
    """

    # pylint: disable=too-many-arguments, too-many-positional-arguments, too-many-instance-attributes, too-many-statements, protected-access
    def __init__(
        self,
        name: str,
        function_key: str | None = None,
        function_to_run: Callable | list[Callable] | None = None,
        type_class: Any | None = None,
        path_to_data: str | None = None,
        uses_config: bool = False,
        ndims: int = 2,
        of_type: list = None,
        metadata_paths: dict = None,
        tooltip: str | None = None,
        overide_get_widget: bool = False,
        run_immediately: bool = True,
        function_manager=None,
    ):
        self.name = name
        self.path_to_data = path_to_data
        self.function_manager = function_manager
        if path_to_data is not None:
            self.function_key = function_key
            self.type_class = type_class
            self.uses_config = uses_config
            self.ndims = ndims
            self.of_type = of_type
            self.metadata_paths = metadata_paths
        self.function_to_run = function_to_run
        self.run_immediately = run_immediately
        if function_to_run is not None and isinstance(function_to_run, list):
            self.is_group = True
            self.group_functions = {f.name: f for f in function_to_run}

            def get_choices(_widget=None):
                return list(self.group_functions.keys())

            def make_group_func(widget_function_self):
                def func(function_name: str):
                    wf = widget_function_self.group_functions.get(function_name)
                    widget_function_self.function_manager.add_function_as_widget(function_name, wf)

                return func

            save_scripts_btn = PushButton(
                label="Save Scripts", tooltip="Save the currently loaded scripts for use in future sessions"
            )

            @save_scripts_btn.clicked.connect
            def save_scripts_btn_clicked():
                selection_dialog = SelectionDialog(
                    get_choices(), "Select scripts to save", parent=current_viewer().window._qt_window
                )
                if selection_dialog.exec_():
                    selected_scripts = selection_dialog.get_selected_items()
                    if not selected_scripts:
                        self.function_to_run.set_status_message("No scripts selected to save.")
                        return
                    saved_files = save_scripts(selected_scripts)

                    if saved_files:
                        if len(saved_files) > 3:
                            self.function_to_run.set_status_message(
                                f"✅ Saved: {', '.join(saved_files[:3])} and {len(saved_files) - 3} more"
                            )
                        else:
                            self.function_to_run.set_status_message(f"✅ Saved: {', '.join(saved_files)}")
                    else:
                        self.function_to_run.set_status_message("No scripts saved.")

            delete_scripts_btn = PushButton(
                label="Delete Saved Scripts", tooltip="Delete saved scripts from future sessions"
            )

            @delete_scripts_btn.clicked.connect
            def delete_scripts_btn_clicked():
                scripts_metadata = fetch_saved_scripts()
                if not scripts_metadata:
                    self.function_to_run.set_status_message("No saved scripts to delete.")
                    return
                saved_functions = [
                    func_name for scripts_file in scripts_metadata.values() for func_name in scripts_file
                ]
                selection_dialog = SelectionDialog(
                    saved_functions, "Select scripts to delete", parent=current_viewer().window._qt_window
                )
                if selection_dialog.exec_():
                    selected_scripts = selection_dialog.get_selected_items()
                    if not selected_scripts:
                        self.function_to_run.set_status_message("No scripts selected to delete.")
                        return
                    unsaved_files = unsave_scripts(selected_scripts)

                    if unsaved_files:
                        if len(unsaved_files) > 3:
                            self.function_to_run.set_status_message(
                                f"❌ Deleted: {', '.join(unsaved_files[:3])} and {len(unsaved_files) - 3} more"
                            )
                        else:
                            self.function_to_run.set_status_message(f"❌ Deleted: {', '.join(unsaved_files)}")

                        # Dynamically remove deleted scripts from choices and refresh dropdown
                        for name in selected_scripts:
                            if name in self.group_functions:
                                del self.group_functions[name]
                        self.function_to_run.function_name.reset_choices()
                    else:
                        self.function_to_run.set_status_message("No scripts deleted.")

            button_row = Container(layout="horizontal", widgets=[save_scripts_btn, delete_scripts_btn], labels=False)

            self.function_to_run = magicgui(make_group_func(self), function_name={"choices": get_choices})
            self.function_to_run.append(button_row)
            attach_status_label(self.function_to_run)
        else:
            self.is_group = False

        self.tooltip = tooltip
        self.overide_get_widget = overide_get_widget
        self.overide_viewer = None
        self.function_gui = self.function_to_run if isinstance(self.function_to_run, FunctionGui) else None

    def add_to_group(self, widget_function):
        """Add a widget function to the group of functions if this WidgetFunction is a group."""
        if not self.is_group:
            return
        self.group_functions[widget_function.name] = widget_function

        if hasattr(self.function_to_run, "function_name"):
            self.function_to_run.function_name.reset_choices()

        docked_function = self.function_manager.get_docked_function(self.name)
        if docked_function is not None and hasattr(docked_function, "function_name"):
            docked_function.function_name.reset_choices()

        if self.function_gui is not None and hasattr(self.function_gui, "function_name"):
            self.function_gui.function_name.reset_choices()

    def add_overide_viewer(self, viewer: Viewer):
        """Adds an overide viewer, this is sometimes required for abstract use of the plugin such as tests"""
        self.overide_viewer = viewer

    def get_function_gui(self) -> FunctionGui:
        """
        Get the magicgui widget for the function.
        If the widget has not been created yet, it will be created.

        Returns
        -------
        FunctionGui
            The magicgui widget that can be used in the napari viewer as a representation of the function.
        """
        if self.path_to_data is None:
            if isinstance(self.function_to_run, FunctionGui):
                widget = self.function_to_run
            elif callable(self.function_to_run):
                widget = magicgui(self.function_to_run)
            else:
                widget = None
            if widget is not None and not hasattr(widget, "set_status_message"):
                attach_status_label(widget)
            self.function_gui = widget
            return self.function_gui
        self.function_gui = self.get_widget()
        return self.function_gui

    # pylint: disable=too-many-branches, too-many-statements
    def get_widget(
        self,
    ) -> FunctionGui:
        """Create a magicgui widget for the function.
        This widget will have the function's parameters as inputs and will
        call the function when the user interacts with it.

        Returns
        -------
        FunctionGui
            A magicgui widget that can be used in the napari viewer.
        """
        # Check if a config is needed
        if self.uses_config and (io.config_wrapper is None or io.full_config_container is None):
            io.load_config_impl(current_viewer(), use_default=True)

            # Replace any dynamic components of the paths with actual values from the config if needed
            flat_config = get_current_config(flat=True)

            def lookup(match):
                key = match.group(1)
                if key in flat_config:
                    return str(flat_config[key])
                return match.group(0)

            for attr in ["path_to_data", "metadata_paths"]:
                value = getattr(self, attr)
                if isinstance(value, str):
                    setattr(self, attr, re.sub(r"<([^>]+)>", lookup, value))
        # pylint: disable=too-many-nested-blocks
        try:
            # If path_to_data is not set, default to "return" or "obj" if type_class is provided
            if self.path_to_data is None:
                if self.type_class is not None:
                    self.path_to_data = "obj"
                else:
                    self.path_to_data = "return"
            # Get all the parameters from the function (excluding 'self')
            parameters_from_function = [
                p for p in inspect.signature(self.function_to_run).parameters.values() if p.name != "self"
            ]
            # Get all the parameters from the type_class (if provided)
            if self.type_class is not None:
                sig = inspect.signature(self.type_class.__init__)
                parameters_from_class = [p for name, p in sig.parameters.items() if name != "self"]
                all_parameters = parameters_from_class + parameters_from_function
            else:
                sig = inspect.signature(self.function_to_run)
                all_parameters = parameters_from_function

            # Create a copy of the parameters to include config parameters
            including_config_params_from_function = parameters_from_function.copy()
            including_config_params_from_class = parameters_from_class.copy() if self.type_class is not None else []
            # Then remove parameters that are already in the config (so they are set from config file rather than GUI)
            if self.uses_config:
                full_current_config = io.config_wrapper.unflatten()
                config = full_current_config.get(self.function_key, {})
                for param_name in [p.name for p in all_parameters]:
                    if param_name in config:
                        parameters_from_function = [p for p in parameters_from_function if p.name != param_name]
                        if self.type_class is not None:
                            parameters_from_class = [p for p in parameters_from_class if p.name != param_name]
                    else:
                        for flat_key in io.config_wrapper.flat:
                            if (
                                flat_key.startswith(f"{self.function_key}.")
                                and flat_key[len(f"{self.function_key}.") :] == param_name
                            ):
                                parameters_from_function = [p for p in parameters_from_function if p.name != param_name]
                                if self.type_class is not None:
                                    parameters_from_class = [p for p in parameters_from_class if p.name != param_name]
                                break
                    if param_name in config and isinstance(config[param_name], dict):
                        parameters_from_function = [p for p in parameters_from_function if p.name != param_name]
                        if self.type_class is not None:
                            parameters_from_class = [p for p in parameters_from_class if p.name != param_name]

            # pylint: disable=too-many-branches, too-many-statements, broad-exception-caught, attribute-defined-outside-init
            def func(**kwargs):
                selected_curves_volume_name = kwargs.pop(CURVES_VOLUME_PARAM, None)
                local_params_function = including_config_params_from_function.copy()
                local_params_from_class = (
                    including_config_params_from_class.copy() if self.type_class is not None else []
                )
                func_to_execute = self.function_to_run
                viewer = self.overide_viewer or kwargs.get("viewer") or current_viewer()
                loading_widget = LoadingWidget(viewer)
                loading_widget.start(
                    self.name.replace("_", " ").replace("run", "running").replace("make", "making").title()
                )

                method_args = {}
                class_args = {}
                # Determine all relevant parameters
                all_params = local_params_function + (local_params_from_class if self.type_class else [])

                uses_topostats_object = "topostats_object" in [p.name for p in all_params]

                # Handle image selection if required
                selected_image = get_selected_image(
                    kwargs.get("viewer", current_viewer()),
                    of_type=self.of_type,
                )
                if selected_image is None:
                    loading_widget.stop()
                    return
                if "image" in [p.name for p in all_params]:
                    kwargs["image"] = selected_image

                # Handle pixel_to_nm_scaling if required
                if (
                    "pixel_to_nm_scaling" in [p.name for p in all_params] and "pixel_to_nm_scaling" not in kwargs
                ) or uses_topostats_object:
                    px2nm = selected_image.metadata.get("px2nm", 1.0)
                if "pixel_to_nm_scaling" in [p.name for p in all_params] and "pixel_to_nm_scaling" not in kwargs:
                    kwargs["pixel_to_nm_scaling"] = px2nm

                # Get the filename from the image layer if required
                if ("filename" in [p.name for p in all_params] and "filename" not in kwargs) or uses_topostats_object:
                    filename = "image"
                if "filename" in [p.name for p in all_params] and "filename" not in kwargs:
                    kwargs["filename"] = filename

                if "curve" in [p.name for p in all_params] and "curve" not in kwargs:
                    # Add the type class to kwargs so the function can be wrapped in all_curves if needed
                    if self.type_class:
                        kwargs["type_class"] = self.type_class
                        self.type_class = (
                            None  # Set to None as wrapping in all_curves will remove requirement for type_class
                        )

                    return_type = get_type_hints(self.function_to_run).get("return")
                    if return_type is dict or get_origin(return_type) is dict:
                        loaded_image = get_selected_loaded_image(viewer)
                        current_afm_load = loaded_image.get_current_load()
                        if loaded_image.curves_data is None or current_afm_load is None:
                            loading_widget.stop()
                            show_error_dialog(
                                "No curves found in the selected layer.",
                                raise_exception=True,
                            )
                            return
                        curves_data = loaded_image.curves_data
                        default_volume = curves_data.get_default_volume()
                        curves_name = default_volume.name if default_volume else "curves"
                        volume_options = list(curves_data.volumes.keys())

                        params_config = {
                            "volume_name_to_operate_on": {
                                "type": volume_options,
                                "default": curves_name,
                                "label": "Curves volume to operate on:",
                            },
                            "new_volume_name": {
                                "type": str,
                                "default": f"{curves_name}_{self.function_to_run.__name__}",
                                "label": "New curves volume name:",
                            },
                        }

                        is_afmreader = current_afm_load.metadata.get("created_by") == "AFMReader"
                        if is_afmreader:
                            params_config["add_to_current_file"] = {
                                "type": bool,
                                "default": True,
                                "label": "Add processed curves to current file",
                            }
                            warning_msg = None
                        else:
                            warning_msg = (
                                "This file was not created by AFMReader. "
                                "A new file will be created. Click Cancel to abort."
                            )

                        user_params = show_parameter_dialog(
                            parameters=params_config, title="Process Curves Options", warning_message=warning_msg
                        )
                        if user_params is None:
                            loading_widget.stop()
                            return

                        add_to_current_file = user_params.get("add_to_current_file", False)

                        selected_vol_name = user_params["volume_name_to_operate_on"]
                        kwargs["curves"] = curves_data.volumes[selected_vol_name]
                        # TODO could be more efficient with these two functions by adding a channel image that hasn't
                        # been added yet.
                        if not add_to_current_file:

                            def func_to_execute(**kwargs):
                                current_channel = loaded_image.get_current_channel()
                                loaded_image.loader.save_to_h5()
                                loaded_image.init_from_loader(headless=True)
                                if current_channel not in loaded_image.get_available_channels():
                                    current_channel = (
                                        current_channel.lower()
                                        if current_channel.lower() in loaded_image.get_available_channels()
                                        else loaded_image.get_available_channels()[0]
                                    )
                                loaded_image.add_channel_image(channel=current_channel, headless=True)
                                curves_data = loaded_image.curves_data
                                kwargs["curves"] = curves_data.volumes[selected_vol_name]
                                kwargs["h5file"] = curves_data.h5file
                                kwargs["new_volume_name"] = user_params["new_volume_name"]
                                result = all_curves(func=self.function_to_run, **kwargs)
                                loaded_image.add_channel_image(channel=current_channel, headless=True)
                                return result

                        else:

                            def func_to_execute(**kwargs):
                                kwargs["h5file"] = curves_data.h5file
                                kwargs["new_volume_name"] = user_params["new_volume_name"]
                                result = all_curves(func=self.function_to_run, **kwargs)
                                current_channel = loaded_image.get_current_channel()
                                if current_channel not in loaded_image.get_available_channels():
                                    current_channel = (
                                        current_channel.lower()
                                        if current_channel.lower() in loaded_image.get_available_channels()
                                        else loaded_image.get_available_channels()[0]
                                    )
                                loaded_image.add_channel_image(channel=current_channel, headless=True)
                                return result

                    else:
                        # If the function is designed to take a single curve, wrap it in all_curves to apply
                        # to all curves in the selected layer
                        # pylint: disable=function-redefined
                        def func_to_execute(**kwargs):
                            return all_curves(func=self.function_to_run, **kwargs)

                    new_param = inspect.Parameter(
                        name="curves",
                        kind=inspect.Parameter.KEYWORD_ONLY,
                        default=None,
                        annotation=Any,
                    )
                    all_params = [p if p.name != "curve" else new_param for p in all_params]
                    local_params_function = [p if p.name != "curve" else new_param for p in local_params_function]
                    local_params_from_class = [p if p.name != "curve" else new_param for p in local_params_from_class]

                if "curves" in [p.name for p in all_params] and "curves" not in kwargs:

                    curves_data = get_selected_curves(
                        kwargs.get("viewer", current_viewer()),
                    )
                    selected_volume = (
                        curves_data.get_volume(selected_curves_volume_name)
                        if selected_curves_volume_name in curves_data.volumes
                        else curves_data.get_default_volume()
                    )
                    kwargs["curves"] = selected_volume
                    if "channel_units" in [p.name for p in all_params] and "channel_units" not in kwargs:
                        kwargs["channel_units"] = selected_volume.channel_units
                    if "curves_meta" in [p.name for p in all_params] and "curves_meta" not in kwargs:
                        kwargs["curves_meta"] = curves_data.metadata
                else:
                    if "channel_units" in [p.name for p in all_params] and "channel_units" not in kwargs:
                        kwargs["channel_units"] = {}
                    if "curves_meta" in [p.name for p in all_params] and "curves_meta" not in kwargs:
                        kwargs["curves_meta"] = {}

                if uses_topostats_object:
                    # Create TopoStats object and add to kwargs
                    if selected_image.metadata.get("topostats_object") is not None:
                        topostats_object = selected_image.metadata["topostats_object"]
                    else:
                        topostats_object = TopoStats(
                            image_original=selected_image.data,
                            image=selected_image.data,
                            pixel_to_nm_scaling=px2nm,
                            filename=filename,
                            config=get_current_config(),
                        )
                    kwargs["topostats_object"] = topostats_object
                # Distribute arguments between method_args and class_args
                # TODO do we need to forget about the check for in local_params because if handling curves
                # it might be cleaner to add some kwargs which weren't there before
                for key, value in kwargs.items():
                    if key in [p.name for p in local_params_function]:
                        method_args[key] = value
                    elif self.type_class and key in [p.name for p in local_params_from_class]:
                        class_args[key] = value

                # Add config values if needed
                if self.uses_config:
                    method_args = add_values_to_dict_from_config(
                        config,
                        io.config_wrapper,
                        self.function_key,
                        method_args,
                        local_params_function,
                    )
                    if self.type_class:
                        class_args = add_values_to_dict_from_config(
                            config,
                            io.config_wrapper,
                            self.function_key,
                            class_args,
                            local_params_from_class,
                        )

                # Enforce defaults
                method_args = enforce_defaults(method_args, local_params_function)
                if self.type_class:
                    class_args = enforce_defaults(class_args, local_params_from_class)

                # Execute function or method
                # pylint: disable=too-many-return-statements
                def _func():
                    # ruff: noqa: BLE001
                    try:
                        if self.type_class:
                            instance = self.type_class(**class_args)
                            method = getattr(instance, self.function_to_run.__name__, None)
                            if method:
                                return_value = method(**method_args)
                            else:
                                return construct_error_args(
                                    message=f"Method {self.function_to_run.__name__} not found on instance."
                                )
                        else:
                            return_value = func_to_execute(**method_args)
                        # Evaluate path_to_data
                        metadata = {}
                        if self.metadata_paths is not None:
                            for key in self.metadata_paths:
                                if self.metadata_paths[key] == "config":
                                    metadata[key] = full_current_config
                                else:
                                    metadata[key] = evaluate_path_to_data(
                                        self.metadata_paths[key],
                                        return_value,
                                        instance if self.type_class else None,
                                        self.type_class,
                                    )
                        if self.type_class and hasattr(instance, "topostats_object"):
                            metadata["topostats_object"] = instance.topostats_object

                        if self.type_class:
                            result = evaluate_path_to_data(
                                self.path_to_data,
                                return_value,
                                instance,
                                self.type_class,
                            )
                        else:
                            result = evaluate_path_to_data(self.path_to_data, return_value)
                    except Exception as e:
                        return construct_error_args(
                            exception=e, raise_exception=True, topostats_error=True, type_class=self.type_class
                        )
                    return (result, metadata)

                def _handle_result(result):
                    if isinstance(result, dict) and "message" in result:
                        loading_widget.stop()
                        show_error_dialog(**result)
                        return
                    try:
                        viewer = self.overide_viewer or kwargs.get("viewer") or current_viewer()
                        return_value, metadata = result
                        if (
                            isinstance(return_value, tuple)
                            and len(return_value) == 2
                            and isinstance(return_value[1], str)
                        ):
                            return_value, z_units = return_value
                        else:
                            z_units = None
                        if return_value is not None:
                            self.render_return_value(
                                return_value,
                                viewer,
                                selected_image,
                                metadata=metadata,
                                z_units=z_units,
                            )
                        else:
                            show_error_dialog(f"Function {self.function_to_run.__name__} returned None.")
                    finally:
                        loading_widget.stop()
                        if self.name == get_running_function():
                            set_running_function(None)

                set_running_function(self.name)
                self.worker = ProcessWorker(_func)
                self.worker.start()
                self.worker.result_ready.connect(_handle_result)

            # Collect the parameters for the function and ensure defaults are set (these defaults are shown in the GUI)

            new_parameters = []
            for p in (
                (parameters_from_function + parameters_from_class)
                if self.type_class is not None
                else parameters_from_function
            ):
                if p.name == "image":
                    # Sets the default image to the currently selected image in the viewer
                    # Done at the time of opening the widget
                    new_p = p.replace(annotation=Image)
                elif p.name == "pixel_to_nm_scaling":
                    new_p = p.replace(default=1.0)
                elif p.name == "filename":
                    new_p = p.replace(default="image")
                else:
                    new_p = p
                if new_p.name not in [
                    "pixel_to_nm_scaling",
                    "image",
                    "filename",
                    "topostats_object",
                    "curve",
                    "curves",
                    "channel_units",
                    "curves_meta",
                ]:
                    new_parameters.append(new_p)

            has_curves_parameter = "curves" in [p.name for p in all_parameters] or "curve" in [
                p.name for p in all_parameters
            ]

            if len(new_parameters) == 0 and not has_curves_parameter:
                self.run_immediately = True
            # Create a magicgui function with the wrapped function and the new parameters
            wrapped_func = CallableWithSignature(func, inspect.Signature(parameters=new_parameters))
            param_options = {}
            if has_curves_parameter:

                def get_available_curves_volumes(_event=None):
                    curves_data = get_selected_curves(
                        self.overide_viewer or current_viewer(),
                        suppress_errors=True,
                    )
                    if curves_data is None:
                        return []
                    volume_names = list(curves_data.volumes.keys())
                    return volume_names or []

                def get_default_curves_volume_name():
                    curves_data = get_selected_curves(
                        self.overide_viewer or current_viewer(),
                        suppress_errors=True,
                    )
                    if curves_data is None:
                        return ""
                    return curves_data.default_volume_name

                curves_volume_param = inspect.Parameter(
                    name=CURVES_VOLUME_PARAM,
                    kind=inspect.Parameter.KEYWORD_ONLY,
                    default=get_default_curves_volume_name(),
                    annotation=str,
                )
                new_parameters.append(curves_volume_param)
                wrapped_func = CallableWithSignature(func, inspect.Signature(parameters=new_parameters))
                param_options[CURVES_VOLUME_PARAM] = {
                    "widget_type": "ComboBox",
                    "choices": get_available_curves_volumes,
                    "label": "curves volume to operate on:",
                }

                def refresh_curves_volume_widget(_event=None):
                    if not has_curves_parameter:
                        return
                    volume_widget = magicgui_function[CURVES_VOLUME_PARAM]
                    previous_value = volume_widget.value
                    curves_data = get_selected_curves(
                        self.overide_viewer or current_viewer(),
                        suppress_errors=True,
                    )
                    available_volumes = curves_data.get_volume_names() if curves_data else []
                    volume_widget.reset_choices()
                    volume_widget.enabled = bool(available_volumes)
                    if previous_value in available_volumes:
                        volume_widget.value = previous_value
                        return
                    default_volume_name = curves_data.default_volume_name if curves_data else None
                    if default_volume_name in available_volumes:
                        volume_widget.value = default_volume_name

            magicgui_function = magicgui(**param_options)(wrapped_func)

            if has_curves_parameter:
                refresh_curves_volume_widget()
                viewer = self.overide_viewer or current_viewer()
                viewer.layers.selection.events.changed.connect(refresh_curves_volume_widget)
            attach_status_label(magicgui_function)
            return magicgui_function

        except Exception as e:
            show_error_dialog(f"❌ Exception in get_widget: {e}")
            raise

    # pylint: disable=too-many-statements, too-many-locals
    def render_return_value(
        self,
        return_value: Any,
        viewer: Viewer,
        original: Layer,
        metadata: dict,
        z_units: str | None = None,
    ):
        """
        Render the return value of a function in the napari viewer.

        This function handles the rendering of the return value based on its type.
        If the return value is a numpy array, it will be added as an image layer.
        If it is a binary image, it will be added as a labels layer.

        Parameters
        ----------
        return_value : Any
            The return value of the function which will be rendered.
        function_key : str
            The key of the function that was executed, used for naming the layer.
        viewer : Viewer
            The napari viewer instance where the layer will be added. If not provided, the current viewer will be used.
        original : Layer
            The original image layer, used for metadata and naming. If not provided, it will be set to None.
        metadata : dict
            Additional metadata to add to the layer.
        z_units : str, optional
            The units for the z-axis. Default is None (though will be programmaticaly defaulted to nm).
        """

        # Check if the return value is a numpy array
        if isinstance(return_value, bool) and return_value:
            display_name = self.name.replace("_", " ").title()
            message = f"✅ {display_name} successful."
            if hasattr(self, "function_gui") and self.function_gui and hasattr(self.function_gui, "set_status_message"):
                self.function_gui.set_status_message(message)
            return
        elif isinstance(return_value, np.ndarray):
            # Get the scale from the original layer; default to (1, 1) if not found
            current_scale = original.scale if original else (1, 1)
            # If the return value has a different number of dimensions to the original, use only existing dimensions
            if len(current_scale) != self.ndims:
                current_scale = current_scale[-self.ndims :]

            reader_id = original.metadata.get("afmreader_id", None) if original and original.metadata else None
            if reader_id is not None:
                loaded_image = get_loaded_image(reader_id)
                if loaded_image is not None:
                    channel_name = self.function_key.replace("find_", "")
                    original_channel = original.metadata.get("channel")
                    if z_units is None:
                        _, _, z_units = loaded_image.get_map(original_channel)

                    loaded_image.add_custom_channel(channel_name, return_value, z_units=z_units)
                    # loaded_image.set_channel(channel_name)

            # Common metadata logic
            duplicated_metadata = original.metadata.copy() if original and original.metadata else {}
            combined_metadata = duplicated_metadata | metadata

            # If the return value is a binary image, add it as a labels layer
            if is_binary_image(return_value):
                labels, num_labels = label(return_value.astype(bool))
                label_ids = list(range(1, num_labels + 1))
                properties = {"label_id": label_ids}

                viewer.add_labels(
                    labels.astype(np.uint16),
                    name=f"{original.name} {self.function_key.replace('_', ' ').title()} Mask",
                    properties=properties,
                    metadata=combined_metadata,
                    scale=current_scale,
                )
            # If the return value is a greyscale image array, add it as an image layer
            else:
                name = f"{original.name} {self.function_key.replace('_', ' ').title()} Image"
                name = remove_all_but_last("Image", name)

                viewer.add_image(
                    return_value,
                    name=name,
                    contrast_limits=calculate_contrast_limits(return_value, percentage=0.5),
                    metadata=combined_metadata,
                    scale=current_scale,
                )
                viewer.dims.ndisplay = self.ndims
        elif isinstance(return_value, pd.DataFrame):
            df = return_value
            container = QWidget()
            layout = QVBoxLayout(container)
            nm_checkbox = QCheckBox("Convert to nm")
            nm_checkbox.setChecked(False)

            # Create table widget
            table = QTableWidget()
            table.setRowCount(len(df))
            table.setColumnCount(len(df.columns))
            table.setHorizontalHeaderLabels(df.columns.tolist())

            if isinstance(original, Labels):
                # Create a copy of the dataframe with an extra row for the background for proper alignmemt of labels
                # This will not affect the original dataframe used for the table
                features_df = df.copy()
                features_df.index = features_df.index + 1
                if 0 not in features_df.index:
                    # Get the first row to copy the columns and dtypes
                    bg_row = features_df.iloc[[0]].copy()
                    bg_row.index = [0]
                    # Fill the row with NaN
                    bg_row.loc[0] = np.nan
                    if "grain_number" in bg_row.columns:
                        # Set grain_number to -1 for the background row so it is different from real grains (0-indexed)
                        bg_row["grain_number"] = -1
                    features_df = pd.concat([bg_row, features_df])
                features_df["label_id"] = features_df.index
                original.features = features_df
            original.mode = Mode.PICK
            is_updating = False

            def convert_to_nm(df_m: pd.DataFrame) -> pd.DataFrame:
                """Convert the pd.DataFrame from m to nm."""
                df_nm = df_m.copy()
                m_to_nm = 1e9
                for col in df_nm.select_dtypes(include=[np.number]).columns:
                    if df_nm[col].max() == 0:
                        continue
                    if df_nm[col].max() < 1e-23:  # Volume in m^3
                        df_nm[col] = df_nm[col] * (m_to_nm**3)
                    elif df_nm[col].max() < 1e-14:  # Area in m^2
                        df_nm[col] = df_nm[col] * (m_to_nm**2)
                    elif df_nm[col].max() < 1e-5:  # Length in m
                        df_nm[col] = df_nm[col] * m_to_nm
                return df_nm

            def on_checkbox_changed(checked):
                # Convert table from m to nm
                if checked:
                    df_nm = convert_to_nm(df)

                    # Update table
                    for i in range(len(df_nm)):
                        for j in range(df_nm.shape[1]):
                            item = QTableWidgetItem(str(df_nm.iat[i, j]))
                            table.setItem(i, j, item)
                else:
                    df_m = df.copy()
                    # Update table
                    for i in range(len(df_m)):
                        for j in range(df_m.shape[1]):
                            item = QTableWidgetItem(str(df_m.iat[i, j]))
                            table.setItem(i, j, item)

            # pylint: disable=unused-argument
            def on_row_clicked(row, column):
                """Triggered when a table row is clicked."""
                nonlocal is_updating
                # Get the grain number (or label id) from the dataframe
                grain_id = df.iloc[row]["grain_number"]

                # Find coordinates of that label in the image
                mask = original.data == int(grain_id) + 1
                if mask.any() and isinstance(original, Labels):
                    coords = np.argwhere(mask)
                    if coords.size > 0:
                        centroid = coords.mean(axis=0)
                        # Ensure we're only using (y, x) order for 2D
                        y, x = centroid[-2], centroid[-1]
                        # Set the camera center in world coordinates
                        viewer.camera.center = (y, x)
                    original.show_selected_label = True
                    original.selected_label = int(grain_id) + 1
                    original.mode = Mode.PICK
                    viewer.layers.selection.active = original
                    is_updating = True

            # pylint: disable=unused-argument
            def on_label_selected(event):
                nonlocal is_updating
                if is_updating:
                    is_updating = False
                    return
                selected = original.selected_label
                if selected == 0:  # 0 means background
                    original.show_selected_label = False
                    return

                # Find matching row
                match = df.index[df["grain_number"] + 1 == selected]
                if len(match):
                    row = int(match[0])
                    table.selectRow(row)
                    table.scrollToItem(table.item(row, 0), QTableWidget.PositionAtCenter)
                    original.show_selected_label = True

            nm_checkbox.toggled.connect(on_checkbox_changed)
            nm_checkbox.setObjectName("nm_checkbox")
            layout.addWidget(nm_checkbox)
            original.events.selected_label.connect(on_label_selected)

            # Populate table
            for i in range(len(df)):
                for j in range(df.shape[1]):
                    item = QTableWidgetItem(str(df.iat[i, j]))
                    table.setItem(i, j, item)

            layout.addWidget(table)

            save_button = QPushButton("Save to CSV")
            layout.addWidget(save_button)

            def save_to_csv():
                # Open a file dialog to choose where to save
                file_path, _ = QFileDialog.getSaveFileName(
                    table,
                    "Save Table as CSV",
                    f"{original.name.lower().replace(' ', '_')}_stats.csv",
                    "CSV Files (*.csv)",
                )
                if file_path:
                    df_to_save = convert_to_nm(df) if nm_checkbox.isChecked() else df
                    df_to_save.to_csv(file_path, index=False)
                    print(f"Saved CSV to: {file_path}")

            save_button.clicked.connect(save_to_csv)
            table.cellClicked.connect(on_row_clicked)

            # Add to viewer
            viewer.window.add_dock_widget(container, area="right", name=self.function_key.title())
        else:
            show_error_dialog(
                f"Function {self.function_key} returned an unsupported type: {type(return_value)}.",
                topostats_error=True,
            )


class WidgetFunctionManager:
    """Class to manage the widget functions and their corresponding widgets in the napari viewer."""

    def __init__(self, functions: dict, viewer: Viewer, widget_manager: WidgetManager):
        self.docked_functions: dict[str, QWidget] = {}
        self.functions: dict = functions
        self.viewer = viewer
        self.widget_manager = widget_manager

    # pylint: disable=too-many-branches
    def add_function_as_widget(self, func_name: str, function: WidgetFunction = None):
        """
        Add the widget for a given function to the viewer and run the function

        Parameters
        ----------
        func_name : str
            The name of the function that was clicked.
        """

        widget = None
        self.widget_manager.ensure_valid(func_name)

        function = function or self.functions.get(func_name)
        # Check if the widget is already docked and add it if not
        if func_name not in self.widget_manager.get_docked_widgets():
            if function.overide_get_widget:
                func = function.function_to_run
                sig = inspect.signature(func)
                params = list(sig.parameters.values())
                if len(params) == 1 and params[0].name == "viewer":
                    widget = func(self.viewer)
                elif len(params) == 0:
                    widget = func()
                else:
                    show_error_dialog(
                        f"Function {func_name} expected input when none was given.",
                        raise_exception=True,
                        topostats_error=True,
                    )
                # pylint: disable=used-before-assignment
                self.add_docked_function(widget, func_name)
                return
            widget = function.get_function_gui()
            for param in widget:
                if param.name != "call_button":
                    self.add_docked_function(widget, func_name)
                    break
        widget = self.docked_functions.get(func_name) or widget
        if function.overide_get_widget:
            return

        if not function.is_group and function.run_immediately:
            # If the function is not in the , run it with the appropriate parameters,
            # using the selected image layer as the image parameter
            if hasattr(widget, "image") and widget.image.value is None:
                selected_image = get_selected_image(self.viewer)
                if selected_image is not None:
                    widget.image.value = selected_image
            if hasattr(widget, "viewer"):
                widget.viewer.value = self.viewer
            widget()

    def get_widget_from_function(self, function: WidgetFunction) -> FunctionGui | None:
        """
        Get the widget representation of the passed function by selecting between generating it or returning the
        passed function if it is already a widget

        Parameters
        ----------
        function : WidgetFunction
            The WidgetFunction object to retrieve the widget for.

        Returns
        -------
        FunctionGui or None
            The widget for the function, or None if the function is not valid.
        """
        if isinstance(function, WidgetFunction):
            # If the function is a WidgetFunction, get its GUI representation.
            widget = function.get_function_gui()
        else:
            show_error_dialog(
                f"Function {function.name} is not a valid WidgetFunction or FunctionGui.",
                raise_exception=True,
            )
            return None
        return widget

    def add_docked_function(self, widget, name: str, area: str = "right"):
        """
        Add a widget to the viewer as a docked widget and keep track of it in the state.

        Parameters
        ----------
        widget : QWidget
            The widget to add to the viewer.
        name : str
            The name of the widget, used for tracking in the state.
        area : str, optional
            The area of the viewer to dock the widget in (default is "right").
        """
        self.docked_functions[name] = widget
        self.widget_manager.add_docked_widget(widget, area=area, name=name)

    def get_docked_function(self, name):
        """
        Get the docked widget for a given function name.

        Parameters
        ----------
        name : str
            The name of the function.

        Returns
        -------
        QWidget or None
            The docked widget for the function, or None if it does not exist.
        """
        return self.docked_functions.get(name)
