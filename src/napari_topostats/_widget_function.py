# pylint: disable=no-else-return
"""
Module for dynamic widget generation from topostats functions including creating a window of options
for those functions, running them and rendering the result.
"""
import functools
import inspect
from collections.abc import Callable
from typing import Any

import dask.array as da
import numpy as np
import pandas as pd
from magicgui import magicgui
from magicgui.widgets import FunctionGui
from napari import current_viewer  # pylint: disable=no-name-in-module
from napari.layers import Image, Labels, Layer
from napari.layers.labels._labels_constants import Mode
from napari.viewer import Viewer
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

from . import _io as io
from ._alerts import LoadingWidget, show_error_dialog
from ._io import ConfigWrapper, collect_values


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


def add_values_to_dict_from_config(
    config: dict[str, Any],
    wrapper: ConfigWrapper,
    function_key: str,
    args: dict[str, Any],
    params: list,
):
    """
    Add values from the config to the args dictionary based on the function key and parameters.
    This function checks if the parameters are present in the config and adds them to the args dictionary.

    Parameters
    ----------
    config : dict[str, Any]
        The configuration dictionary containing the function parameters.
    wrapper : ConfigWrapper
        The ConfigWrapper instance used to access flattened configuration values.
    function_key : str
        The key for the function in the configuration dictionary.
    args : dict[str, Any]
        The current dictionary of arguments to which the configuration values will be added.
    params : list
        The list of parameter names for the function.

    Returns
    -------
    args : dict[str, Any]
        The updated dictionary of arguments with values from the config added.
    """
    for param_name in [p.name for p in params]:
        if param_name in config:
            args[param_name] = config[param_name]

        for flat_key, flat_val in wrapper.flat.items():
            if flat_key.startswith(f"{function_key}.") and flat_key[len(f"{function_key}.") :] == param_name:
                args[param_name] = flat_val
                break
        # Is this not redundant?
        if param_name in config and isinstance(config[param_name], dict):
            args[param_name] = config[param_name]
    return args


# pylint: disable=too-many-branches
def _eval(obj: Any, string: str) -> Any:
    """
    Evaluate a path string on an object to access its attributes or subscripts. For example, given a list `lst`, the
    string "lst[0].name" would return the name attribute of the first element of the list. This is done without
    using `eval` to avoid security risks.

    Parameters
    ----------
    obj : Any
        The object on which to evaluate the string.
    string : str
        The path string to evaluate.

    Returns
    -------
    Any
        The result of the evaluation.
    """
    # Remove spaces from the string for easier parsing
    string = string.replace(" ", "")
    if string == "":
        # If the string is empty, return the object itself
        return obj

    # Handle subscript access, e.g., [0], [1:3], ['key']
    if string[0] == "[":
        # Find the next punctuation to determine the subscript type
        next_punc = next_punctuation(string, 1, checking_for=",()[].")
        if next_punc != -1 and string[next_punc] == ",":
            # Handle tuple subscripts, e.g., [1,2]
            axes = []
            for i in string[1 : string.index("]", 1)].split(","):
                if i == ":":
                    axes.append(slice(None))
                elif i.isdigit():
                    axes.append(int(i))
            subscript = tuple(axes)
            obj = obj[subscript]
        else:
            # Handle single index or key, e.g., [0] or ['key']
            subscript = string[1 : string.index("]", 1)]
            if subscript.isdigit():
                obj = obj[int(subscript)]
            else:
                key = subscript.replace("'", "").replace('"', "")
                obj = obj[key]
        # Recursively evaluate the remaining string
        remaining = string[string.index("]", 1) + 1 :]
        return _eval(obj, remaining)

    # Handle attribute access or method calls, e.g., .attr or .method()
    if string[0] == ".":
        index = next_punctuation(string, 1)
        if index == -1:
            # No further punctuation, just get the attribute
            attr = string[1:]
            if hasattr(obj, attr):
                return getattr(obj, attr)
            else:
                raise AttributeError(f"'{type(obj).__name__}' object has no attribute '{attr}'")

        if string[index] == "(":
            # Handle method call, e.g., .method(args)
            func_name = string[1:index]
            if hasattr(obj, func_name):
                func = getattr(obj, func_name)
                args_str = string[index + 1 : string.index(")", index + 1)]
                args = [arg.strip() for arg in args_str.split(",") if arg.strip()]
                result = func(*args)
                remaining = string[string.index(")", index + 1) + 1 :]
                # Recursively evaluate the remaining string
                return _eval(result, remaining)
            else:
                raise AttributeError(f"'{type(obj).__name__}' object has no callable '{func_name}'")
        else:
            # Handle attribute access followed by more operations
            attr = string[1:index]
            if hasattr(obj, attr):
                obj = getattr(obj, attr)
            else:
                raise AttributeError(f"'{type(obj).__name__}' object has no attribute '{attr}'")
            remaining = string[index:]
            # Recursively evaluate the remaining string
            return _eval(obj, remaining)
    # If the string does not start with '[' or '.', return the object
    return obj


def next_punctuation(s: str, start: int = 0, checking_for: str = ".([") -> int:
    """Find the next punctuation character in a string."""
    for i in range(start, len(s)):
        if s[i] in checking_for:
            return i
    return -1


class CallableWithSignature:
    """
    A callable that wraps a function and its signature. This allows the signature of the function to be updated for
    its parameters and their defaults so that it can be used correctly with magicgui.
    """

    def __init__(self, real_func, sig):
        functools.update_wrapper(self, real_func)  # Sets __name__, __doc__, etc.
        self.real_func = real_func
        self.__signature__ = sig

    def __call__(self, *args, **kwargs):
        bound = self.__signature__.bind(*args, **kwargs)
        bound.apply_defaults()
        return self.real_func(**bound.arguments)


def get_selected_image(viewer, of_type: list = None) -> Image | None:
    """
    Get the currently selected image layer from the viewer.

    Parameters
    ----------
    viewer : Viewer
        The napari viewer instance from which to get the selected image layer.

    Returns
    -------
    Image | None
        The selected image layer, or None if no layer is selected.
    """
    selected = list(viewer.layers.selection)

    if not selected:
        show_error_dialog("No layer selected. Select a layer ")
        return None
    layer = selected[0]
    if of_type is not None and layer.__class__ not in of_type:
        pretty_types = [t.__name__ for t in of_type]
        show_error_dialog(
            f"Selected layer is not of a required type: {', '.join(pretty_types)}.",
            raise_exception=False,
        )
        return None
    if isinstance(layer, Image):
        data = layer.data
        if isinstance(data, (np.ndarray, da.Array)):  # conforms to ImageData
            return layer
        show_error_dialog("Layer data is not valid ImageData.", raise_exception=True)
    elif isinstance(layer, Labels):
        return layer
    return None


def is_binary_image(arr: np.ndarray) -> bool:
    """Check if the array is a binary image (0s and 1s or 0s and 255s).
    Parameters
    ----------
    arr : np.ndarray
        The array to check.
    Returns
    -------
    bool
        True if the array is a binary image, False otherwise.
    """
    unique_vals = np.unique(arr)
    # Check if unique values are subset of {0,1}
    return set(unique_vals).issubset({0, 1, 255})


def remove_all_but_last(word: str, text: str) -> str:
    """Remove all occurrences of 'word' in 'text' except the last one.

    Parameters
    ----------
    word : str
        The word to remove.
    text : str
        The text from which to remove the word.

    Returns
    -------
    str
        The text with all occurrences of the word removed except the last one.
    """
    parts = text.rsplit(word, maxsplit=1)
    if len(parts) == 1:
        return text  # word not found or only once
    return (parts[0].replace(word, "") + word + parts[1]).replace("  ", " ").strip()  # Remove extra spaces and return


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
    if path_to_data.startswith("return"):
        return _eval(return_value, path_to_data[6:]) if len(path_to_data) > 6 else return_value

    if path_to_data.startswith("obj"):
        if type_class:
            return _eval(instance, path_to_data[3:]) if len(path_to_data) > 3 else instance
        else:
            show_error_dialog(f"Invalid path_to_data: {path_to_data} - 'obj' requires type_class")
            return None

    show_error_dialog(f"Invalid path_to_data: {path_to_data}", topostats_error=True)
    return None


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
    uses_config : bool, optional
        Whether the function uses a configuration file to set its parameters. If True, the function will
        load the configuration file and use it to set the parameters. If False, the function will
        use only the parameters set in the widget. Note that certain parameters can also be taken from the napari
        viewer, such as the selected image or from the image metadata, such as the pixel to nm scaling factor.
    path_to_data : str | None, optional
        The path to the data that the function returns. This is used to determine how to extract the data from the
        return value of the function. It can be "return" to return the data directly (from the function), "obj" to
        return the object itself, or a specific path to access a nested attribute or subscript in the return value
        or the object instance.
    ndims : int, optional
        The number of dimensions of the data to be rendered. Can be left as default 2, but can be set to 3 if the
        function returns 3D data.
    tooltip : str | None, optional
        A tooltip for the widget, providing additional information about the function. This is displayed when the
        user hovers over the button for the function in the button grid.
    """

    # pylint: disable=too-many-arguments, too-many-positional-arguments
    def __init__(
        self,
        name: str,
        function_key: str | None = None,
        function_to_run: Callable | None = None,
        type_class: Any | None = None,
        path_to_data: str | None = None,
        uses_config: bool = False,
        ndims: int = 2,
        of_type: list = None,
        metadata_paths: dict = None,
        tooltip: str | None = None,
    ):
        self.name = name
        self.path_to_data = path_to_data
        if path_to_data is not None:
            self.function_key = function_key
            self.type_class = type_class
            self.uses_config = uses_config
            self.ndims = ndims
            self.of_type = of_type
            self.metadata_paths = metadata_paths
        self.function_to_run = function_to_run
        self.tooltip = tooltip
        self.overide_viewer = None
        self.function_gui = None

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
                updated_values = collect_values(io.full_config_container)
                io.config_wrapper.flat.update(updated_values)
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

            # pylint: disable=too-many-branches, too-many-statements, broad-exception-caught
            def func(**kwargs):
                viewer = self.overide_viewer or kwargs.get("viewer") or current_viewer()
                loading_widget = LoadingWidget(viewer)
                loading_widget.start(
                    self.name.replace("_", " ").replace("run", "running").replace("make", "making").title()
                )
                method_args = {}
                class_args = {}

                # Determine all relevant parameters
                all_params = including_config_params_from_function + (
                    including_config_params_from_class if self.type_class else []
                )

                # Handle image selection if required
                if "image" in [p.name for p in all_params]:
                    selected_image = get_selected_image(
                        kwargs.get("viewer", current_viewer()),
                        of_type=self.of_type,
                    )
                    if selected_image is None:
                        loading_widget.stop()
                        return
                    kwargs["image"] = selected_image

                # Handle pixel_to_nm_scaling if required
                if "pixel_to_nm_scaling" in [p.name for p in all_params] and "pixel_to_nm_scaling" not in kwargs:
                    kwargs["pixel_to_nm_scaling"] = kwargs["image"].metadata.get("px2nm", 1.0)
                    print(f"Using pixel_to_nm_scaling from image metadata: {kwargs['pixel_to_nm_scaling']}")

                if "filename" in [p.name for p in all_params] and "filename" not in kwargs:
                    kwargs["filename"] = "image"
                # Distribute arguments between method_args and class_args
                for key, value in kwargs.items():
                    if key in [p.name for p in including_config_params_from_function]:
                        method_args[key] = value
                    elif self.type_class and key in [p.name for p in including_config_params_from_class]:
                        class_args[key] = value

                # Add config values if needed
                if self.uses_config:
                    method_args = add_values_to_dict_from_config(
                        config,
                        io.config_wrapper,
                        self.function_key,
                        method_args,
                        including_config_params_from_function,
                    )
                    if self.type_class:
                        class_args = add_values_to_dict_from_config(
                            config,
                            io.config_wrapper,
                            self.function_key,
                            class_args,
                            including_config_params_from_class,
                        )

                # Enforce defaults
                method_args = enforce_defaults(method_args, including_config_params_from_function)
                if self.type_class:
                    class_args = enforce_defaults(class_args, including_config_params_from_class)

                # Execute function or method
                if self.type_class:
                    # ruff: noqa: BLE001
                    try:
                        instance = self.type_class(**class_args)
                    except Exception as e:
                        show_error_dialog(
                            f"Topostats is failing with {self.type_class.__name__}: {e}.",
                            topostats_error=True,
                        )
                        return
                    method = getattr(instance, self.function_to_run.__name__, None)
                    if method:
                        # ruff: noqa: BLE001
                        try:
                            return_value = method(**method_args)
                        except Exception as e:
                            show_error_dialog(
                                f"Topostats is failing with: {e}.",
                                raise_exception=True,
                                topostats_error=True,
                            )
                            return
                    else:
                        show_error_dialog(f"Method {self.function_to_run.__name__} not found on instance.")
                        loading_widget.stop()
                        return
                else:
                    # ruff: noqa: BLE001
                    try:
                        return_value = self.function_to_run(**method_args)
                    except Exception as e:
                        show_error_dialog(
                            f"Topostats is failing with: {e}.",
                            raise_exception=True,
                            topostats_error=True,
                        )
                        return

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
                                instance,
                                self.type_class,
                            )

                if self.type_class:
                    result = evaluate_path_to_data(
                        self.path_to_data,
                        return_value,
                        instance,
                        self.type_class,
                    )
                else:
                    result = evaluate_path_to_data(self.path_to_data, return_value)
                if result is None:
                    loading_widget.stop()
                    return
                return_value = result

                # Render return value
                if return_value is not None:
                    self.render_return_value(
                        return_value,
                        viewer,
                        kwargs.get("image"),
                        metadata=metadata,
                    )
                else:
                    show_error_dialog(f"Function {self.function_to_run.__name__} returned None.")
                loading_widget.stop()

            # Collect the parameters for the function and ensure defaults are set (these defaults are shown in the GUI)
            new_parameters = []
            for p in (
                (parameters_from_function + parameters_from_class)
                if self.type_class is not None
                else parameters_from_function
            ):
                if p.name == "image":
                    # Sets the default image to the currently selected image in the viewer
                    # Doneat the time of opening the widget
                    selected_image = get_selected_image(current_viewer())
                    if selected_image is not None:
                        new_p = p.replace(default=selected_image, annotation=Image)
                    else:
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
                ]:
                    new_parameters.append(new_p)
            # Create a magicgui function with the wrapped function and the new parameters
            wrapped_func = CallableWithSignature(func, inspect.Signature(parameters=new_parameters))
            magicgui_function = magicgui()(wrapped_func)
            return magicgui_function

        except Exception as e:
            show_error_dialog(f"❌ Exception in get_widget: {e}")
            raise

    # pylint: disable=too-many-statements
    def render_return_value(
        self,
        return_value: Any,
        viewer: Viewer,
        original: Layer,
        metadata: dict,
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
        ndims : int, optional
            The number of dimensions of the data to be rendered. If not provided, it will be set to 2.
        """
        # Check if the return value is a numpy array

        if isinstance(return_value, np.ndarray):
            # If the return value is a binary image, add it as a labels layer
            if is_binary_image(return_value):
                labels, num_labels = label(return_value.astype(bool))
                label_ids = list(range(1, num_labels + 1))
                properties = {"label_id": label_ids}
                viewer.add_labels(
                    labels.astype(np.uint16),
                    name=f"{original.name} {self.function_key.title()} Mask",
                    properties=properties,
                    metadata=({"px2nm": original.metadata.get("px2nm", 1.0)} if original else {}) | metadata,
                )
            # If the return value is a greyscale image array, add it as an image layer
            else:
                name = f"{original.name} {self.function_key.title()} Image"
                name = remove_all_but_last("Image", name)
                viewer.add_image(
                    return_value,
                    name=name,
                    contrast_limits=(-1, 5),
                    metadata=({"px2nm": original.metadata.get("px2nm", 1.0)} if original else {}) | metadata,
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
            original.mode = Mode.PICK

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
                # Get the grain number (or label id) from the dataframe
                grain_id = df.iloc[row]["grain_number"]  # or 'label', whatever your column is called

                # Center the view on it
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

            # pylint: disable=unused-argument
            def on_label_selected(event):
                selected = original.selected_label
                if selected == 0:  # 0 means background in napari
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
