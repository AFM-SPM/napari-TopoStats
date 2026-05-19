"""Module to handle the imported scripts so they can be run on images"""

import importlib.util
import inspect
from pathlib import Path

from ._alerts import show_error_dialog
from ._components import SelectionDialog
from ._state import get_topostats_widget
from ._widget_function import WidgetFunction

loaded_functions = []
ALLOWABLE_PARAMETERS = ["viewer", "image", "curves", "curve", "channel_units"]


def load_py_files(paths, viewer):
    """Load functions from python files into the button grid"""
    global loaded_functions  # pylint: disable=global-variable-not-assigned
    py_functions = {}
    for py_file in paths:
        py_functions.update(load_functions_from_file(py_file))

    # pylint: disable=protected-access
    dialog = SelectionDialog(
        available_items=py_functions.keys(), text="Select functions to import", parent=viewer.window._qt_window
    )

    if dialog.exec_():
        selected_functions = {func_name: py_functions[func_name] for func_name in dialog.get_selected_items()}
    else:
        return
    if selected_functions != {}:
        for func_name, func in selected_functions.items():
            widget_function = WidgetFunction(
                name=func_name,
                function_key=func_name,
                path_to_data="return",
                function_to_run=func,
                tooltip=inspect.getdoc(func),
            )
            topostats_widget = get_topostats_widget()
            if widget_function not in loaded_functions:
                loaded_functions.append(widget_function)
            if topostats_widget is not None:
                topostats_widget.add_function(widget_function, to_group=True)


def fetch_saved_scripts():
    """Fetch user saved scripts from app data and load them into the button grid"""
    return []


def get_loaded_functions():
    """Get the list of currently loaded functions from python files."""
    return loaded_functions


def load_functions_from_file(file_path):
    """Loads a python file dynamically and extracts its functions."""
    path = Path(file_path)
    module_name = path.stem

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        show_error_dialog(f"Failed to load {file_path}")
        return {}

    module = importlib.util.module_from_spec(spec)

    try:
        spec.loader.exec_module(module)
    except Exception as e:  # pylint: disable=broad-exception-caught #noqa: BLE001
        show_error_dialog(f"Error executing {file_path}: {e}")
        return {}

    extracted_functions = {}

    for name, obj in inspect.getmembers(module):
        if inspect.isfunction(obj) and getattr(obj, "__module__", None) == module.__name__ and not name.startswith("_"):
            sig = inspect.signature(obj)
            valid_func = True
            for param_name, param in sig.parameters.items():
                if (
                    param_name not in ALLOWABLE_PARAMETERS
                    and param.default is inspect.Parameter.empty
                    and param.annotation not in [int, str, float, bool, Path]
                ):
                    valid_func = False
                    break
            if valid_func:
                extracted_functions[name] = obj

    return extracted_functions
