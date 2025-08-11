import functools
import inspect
from typing import Any, Callable, Dict

import dask.array as da
import numpy as np
from magicgui import magicgui
from magicgui.widgets import Container, FunctionGui
from napari import current_viewer
from napari.layers import Image
from napari.viewer import Viewer
from scipy.ndimage import label

from . import _io as io
from ._io import ConfigWrapper, collect_values
from ._alerts import show_error_dialog
from . import _state as state


def enforce_defaults(args: Dict[str, Any], params: list[Any]) -> Dict[str, Any]:
    """
    Ensure that all required parameters have default values.
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
            print(f"Converting ImageData to ndarray for key: {key}")
            args[key] = np.asarray(value.data)
    return args

def add_values_to_dict_from_config(
    config: Dict[str, Any],
    wrapper: ConfigWrapper,
    function_key: str,
    args: Dict[str, Any],
    params: list,):
    # for key, value in config.items():
    #     print(f"Processing key: {key}, value: {value}")
    
    #     if value is not None and key in [p.name for p in params]:
    #         args[key] = value
    for param_name in [p.name for p in params]:
        if param_name in config:
            args[param_name] = config[param_name]

        for flat_key, flat_val in wrapper.flat.items():
            if flat_key.startswith(f"{function_key}.") and flat_key[len(f"{function_key}."):] == param_name:
                args[param_name] = flat_val
                break
        # Is this not redundant?
        if param_name in config and isinstance(config[param_name], dict):
            args[param_name] = config[param_name]
    return args

def _eval(obj: Any, string: str) -> Any:

    string = string.replace(" ", "")
    if string == "":
        return obj

    if string[0] == "[":
        next_punc = next_punctuation(string, 1, checking_for=",()[].")
        if next_punc != -1 and string[next_punc] == ",":
            axes = []
            for i in string[1:string.index("]", 1)].split(","):
                if i == ":":
                    axes.append(slice(None))
                elif i.isdigit():
                    axes.append(int(i))
            subscript = tuple(axes)
            obj = obj[subscript]
        else:
            subscript = string[1:string.index("]", 1)]
            if subscript.isdigit():
                obj = obj[int(subscript)]
            else:
                key = subscript.replace("'", "").replace('"', '')
                obj = obj[key]
        remaining = string[string.index("]", 1) + 1:]
        return _eval(obj, remaining)

    elif string[0] == ".":
        index = next_punctuation(string, 1)
        if index == -1:
            attr = string[1:]
            if hasattr(obj, attr):
                return getattr(obj, attr)
            else:
                raise AttributeError(f"'{type(obj).__name__}' object has no attribute '{attr}'")

        if string[index] == "(":
            func_name = string[1:index]
            if hasattr(obj, func_name):
                func = getattr(obj, func_name)
                args_str = string[index + 1:string.index(")", index + 1)]
                args = [arg.strip() for arg in args_str.split(",") if arg.strip()]
                result = func(*args)
                remaining = string[string.index(")", index + 1) + 1:]
                return _eval(result, remaining)
            else:
                raise AttributeError(f"'{type(obj).__name__}' object has no callable '{func_name}'")
        else:
            attr = string[1:index]
            if hasattr(obj, attr):
                obj = getattr(obj, attr)
            else:
                raise AttributeError(f"'{type(obj).__name__}' object has no attribute '{attr}'")
            remaining = string[index:]
            return _eval(obj, remaining)

    else:
        return obj


def next_punctuation(s: str, start: int = 0, checking_for: str = ".([") -> int:
    """Find the next punctuation character in a string."""
    for i in range(start, len(s)):
        if s[i] in checking_for:
            return i
    return -1

class CallableWithSignature:
    def __init__(self, real_func, sig):
        functools.update_wrapper(self, real_func)  # Sets __name__, __doc__, etc.
        self.real_func = real_func
        self.__signature__ = sig

    def __call__(self, *args, **kwargs):
        bound = self.__signature__.bind(*args, **kwargs)
        bound.apply_defaults()
        return self.real_func(**bound.arguments)


def get_selected_image(viewer) -> Image | None:
    selected = list(viewer.layers.selection)

    if not selected:
        print("No layer selected.")
        return None

    layer = selected[0]
    if isinstance(layer, Image):
        data = layer.data
        if isinstance(data, (np.ndarray, da.Array)):  # conforms to ImageData
            return layer
        else:
            print("Layer data is not valid ImageData.")
    else:
        print("Selected layer is not an Image layer.")

    return None

def is_binary_image(arr: np.ndarray) -> bool:
    unique_vals = np.unique(arr) 
    # Check if unique values are subset of {0,1}
    return set(unique_vals).issubset({0, 1, 255})

def remove_all_but_last(word: str, text: str) -> str:
    parts = text.rsplit(word, maxsplit=1)
    if len(parts) == 1:
        return text  # word not found or only once
    return (parts[0].replace(word, "") + word + parts[1]).replace("  ", " ").strip()  # Remove extra spaces and return

def render_return_value(return_value: Any,
    function_key: str,
    viewer: Viewer = None,
    original: Image = None,
    ndims: int = 2) -> None:
    if isinstance(return_value, np.ndarray):
        if is_binary_image(return_value):
            labels, num_labels = label(return_value.astype(bool))
            label_ids = list(range(1, num_labels + 1))
            properties = {"label_id": label_ids}
            viewer.add_labels(
                labels.astype(np.uint16),
                name=f"{original.name} {function_key.title()} Mask",
                properties=properties
            )
        else:
            name = f"{original.name} {function_key.title()} Image"
            name = remove_all_but_last("Image", name)
            viewer.add_image(
                return_value,
                name=name,
                contrast_limits=(-1, 5),
                metadata={"px2nm": original.metadata.get("px2nm", 1.0)} if original else {}
            )
            viewer.dims.ndisplay = ndims



# Class representation of each function in the button grid.
class WidgetFunction:
    def __init__(self, name: str, function_key: str | None = None, function_to_run: Callable | FunctionGui | None = None, type_class: Any | None = None, path_to_data: str | None = None, uses_config: bool = False, ndims: int = 2, tooltip: str | None = None):

        self.name = name
        self.function_key = function_key
        if function_key is not None:
            self.function_key = function_key
            self.function_to_run = function_to_run
            self.type_class = type_class
            self.path_to_data = path_to_data
            self.uses_config = uses_config
            self.ndims = ndims
        else:
            self.function_to_run = function_to_run
        self.tooltip = tooltip

    def set_function_gui(self, function_gui: FunctionGui):
        self.function_gui = function_gui

    def get_function_gui(self) -> FunctionGui:
        if not hasattr(self, 'function_gui'):
            self.function_gui = self.get_widget()
        return self.function_gui


    def get_widget(self) -> FunctionGui:
        function_key = self.function_key
        function_to_run = self.function_to_run
        type_class = self.type_class
        path_to_data = self.path_to_data
        uses_config = self.uses_config
        ndims = self.ndims
        if uses_config:
            if io.config_wrapper is None or io.full_config_container is None:
                print("Config wrapper or full config container is not set.")
                io.load_config(current_viewer())
        try:
            if path_to_data is None:
                if type_class is not None:
                    path_to_data = "obj"
                else:
                    path_to_data = "return"
            parameters_from_function = [
                p for p in inspect.signature(function_to_run).parameters.values() if p.name != "self"
            ]

            if type_class is not None:
                sig = inspect.signature(type_class.__init__)
                parameters_from_class = [
                    p for name, p in sig.parameters.items()
                    if name != "self"
                ]
                all_parameters = parameters_from_class + parameters_from_function
            else:
                sig = inspect.signature(function_to_run)
                all_parameters = parameters_from_function
                

            including_config_params_from_function = parameters_from_function.copy()
            including_config_params_from_class = parameters_from_class.copy() if type_class is not None else []
            if uses_config:
                updated_values = collect_values(io.full_config_container)
                io.config_wrapper.flat.update(updated_values)
                full_current_config = io.config_wrapper.unflatten()
                config = full_current_config.get(function_key, {})
                for param_name in [p.name for p in all_parameters]:
                    if param_name in config:
                        parameters_from_function = [p for p in parameters_from_function if p.name != param_name]
                        if type_class is not None:
                            parameters_from_class = [p for p in parameters_from_class if p.name != param_name]
                    else:
                        for flat_key, flat_val in io.config_wrapper.flat.items():
                            if flat_key.startswith(f"{function_key}.") and flat_key[len(f"{function_key}."):] == param_name:
                                parameters_from_function = [p for p in parameters_from_function if p.name != param_name]
                                if type_class is not None:
                                    parameters_from_class = [p for p in parameters_from_class if p.name != param_name]
                                break
                    if param_name in config and isinstance(config[param_name], dict):
                        parameters_from_function = [p for p in parameters_from_function if p.name != param_name]
                        if type_class is not None:
                            parameters_from_class = [p for p in parameters_from_class if p.name != param_name]
            if type_class is not None:
                def func(**kwargs):
                    class_args = {}
                    method_args = {}
                    if "image" in [p.name for p in including_config_params_from_class + including_config_params_from_function]:
                        if kwargs["image"] is None:
                            show_error_dialog("Please select an image before running this function.")
                            return
                    if (
                        "pixel_to_nm_scaling" in [p.name for p in including_config_params_from_class + including_config_params_from_function]
                        and "pixel_to_nm_scaling" not in kwargs
                    ):
                        kwargs["pixel_to_nm_scaling"] = kwargs["image"].metadata.get("px2nm", 1.0)
                        print(f"Using pixel_to_nm_scaling from image metadata: {kwargs['pixel_to_nm_scaling']}")

                    for key, value in kwargs.items():
                        if key in [p.name for p in including_config_params_from_function]:
                            method_args[key] = value
                        elif key in [p.name for p in including_config_params_from_class]:
                            class_args[key] = value
                    if uses_config:
                        method_args = add_values_to_dict_from_config(
                            config, io.config_wrapper, function_key, method_args, including_config_params_from_function
                        )
                        class_args = add_values_to_dict_from_config(
                            config, io.config_wrapper, function_key, class_args, including_config_params_from_class
                        )

                    method_args = enforce_defaults(method_args, including_config_params_from_function)
                    class_args = enforce_defaults(class_args, including_config_params_from_class)
                    instance = type_class(**class_args)
                    method = getattr(instance, function_to_run.__name__, None)
                    if method:
                        return_value = method(**method_args)

                        if path_to_data.startswith("return"):
                            return_value = _eval(return_value, path_to_data[6:]) if len(path_to_data) > 6 else return_value
                        elif path_to_data.startswith("obj"):
                            return_value = _eval(instance, path_to_data[3:]) if len(path_to_data) > 3 else instance
                        else:
                            raise ValueError(f"Invalid path_to_data: {path_to_data}")
                        
                        if return_value is not None:
                            viewer = kwargs["viewer"] if "viewer" in kwargs else current_viewer()
                            render_return_value(return_value, function_key, viewer, kwargs.get("image", None))
            else:
                def func(**kwargs):
                    method_args = {}

                    for key, value in kwargs.items():
                        if key in [p.name for p in including_config_params_from_function]:
                            method_args[key] = value
                    if uses_config:
                        method_args = add_values_to_dict_from_config(
                            config, io.config_wrapper, function_key, method_args, including_config_params_from_function
                        )

                    method_args = enforce_defaults(method_args, including_config_params_from_function)

                    return_value = function_to_run(**method_args)
                    if path_to_data.startswith("return"):
                        return_value = _eval(return_value, path_to_data[6:]) if len(path_to_data) > 6 else return_value
                    if return_value is not None:
                        viewer = kwargs["viewer"] if "viewer" in kwargs else current_viewer()
                        render_return_value(return_value, function_key, viewer, original=kwargs.get("image", None), ndims=ndims)
                    else:
                        show_error_dialog(f"Function {function_to_run.__name__} returned None.") 
            new_parameters = []
            for p in (parameters_from_function + parameters_from_class) if type_class is not None else parameters_from_function:
                if p.name == "image":
                    new_p = p.replace(default=get_selected_image(current_viewer()), annotation=Image)
                elif p.name == "pixel_to_nm_scaling":
                    new_p = p.replace(default=1.0)
                elif p.name == "filename":
                    new_p = p.replace(default="image")
                else:
                    new_p = p
                if new_p.name != "pixel_to_nm_scaling":
                    new_parameters.append(new_p)
            wrapped_func = CallableWithSignature(func, inspect.Signature(parameters=new_parameters))
            magicgui_function = magicgui()(wrapped_func)
            return magicgui_function

        except Exception as e:
            show_error_dialog(f"❌ Exception in get_widget: {e}")
            raise

