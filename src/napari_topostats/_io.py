"""Provides functionality for loading and editting config files"""

import contextlib
import json
import re
from argparse import Namespace
from pathlib import Path
from typing import Any

import yaml
from magicgui import magicgui
from magicgui.widgets import FunctionGui, create_widget
from napari.viewer import Viewer
from platformdirs import user_config_dir
from qtpy.QtCore import Qt
from qtpy.QtGui import QGuiApplication, QIcon
from qtpy.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from topostats import __version__ as topostats_version

from napari_topostats.utils import unflatten_dict

from ._alerts import attach_status_label, show_error_dialog
from ._components import CollapsibleBox
from ._state import MIN_TOPOSTATS_VERSION, get_widget_manager

# pylint: disable=ungrouped-imports
try:
    from topostats.config import write_config_with_comments
except ImportError:
    show_error_dialog(
        f"TopoStats version {topostats_version} is not supported. Please install the latest version of TopoStats"
        f"or if that fails, install version {MIN_TOPOSTATS_VERSION}."
    )


MISC_TITLE = "Batch Settings"
START_OPEN = {"filter", "grains"}
# Globals store currently loaded config and UI state so dialogs/widgets can reuse them.
config_wrapper = None
full_config_container = None
comment_descriptions = {}
current_config_path = None
updated_values = {}


class ConfigWrapper:
    """
    A wrapper for configuration dictionaries to provide a flat view and unflattening functionality.
    """

    def __init__(self, config: dict):
        """
        Initializes the ConfigWrapper.

        Parameters
        ----------
        config : dict
            The configuration dictionary.
        """
        self.original = config
        self.flat = self._flatten(config)

    def _flatten(self, d: dict, parent_key: str = "", sep: str = ".") -> dict:
        """
        Flattens a nested dictionary.

        Parameters
        ----------
        d : dict
            The dictionary to flatten.
        parent_key : str, optional
            The parent key, by default ""
        sep : str, optional
            The separator to use, by default "."

        Returns
        -------
        dict
            The flattened dictionary.
        """
        items = {}
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.update(self._flatten(v, new_key, sep=sep))
            else:
                items[new_key] = v
        return items

    def unflatten(self) -> dict:
        """
        Function used for reverting to the dict form where keys can correspond to dict values like json format

        Returns
        -------
        dict
            The unflattened dictionary.
        """
        return unflatten_dict(self.flat)


def should_use_line_edit_for_float(value: float) -> bool:
    """
    Determine if a float value should be edited with a LineEdit instead of a FloatSpinBox.
    This is to prevent data being lost during rounding

    Parameters
    ----------
    value : float
        The float value to check.

    Returns
    -------
    bool
        True if a LineEdit should be used, False otherwise.
    """
    return abs(value) != 0 and (abs(value) < 1e-4 or abs(value) > 1e6)


# pylint: disable=global-variable-not-assigned
def on_config_value_changed(key: str, val: Any):
    """
    Update the config wrapper when a value changes

    Parameters
    ----------
    key : str
        The key of the value that changed.
    val : Any
        The new value.
    """
    global updated_values
    if isinstance(val, str):
        stripped = val.strip()

        if stripped == "None":
            val = None
        elif stripped.startswith("["):
            # pylint: disable=import-outside-toplevel
            import ast

            with contextlib.suppress(ValueError, SyntaxError):
                val = ast.literal_eval(stripped)
        else:
            # Try float parsing (supports scientific notation)
            with contextlib.suppress(ValueError):
                val = float(stripped)
    if key.split(".")[0] == MISC_TITLE:
        key = ".".join(key.split(".")[1:])
    updated_values[key] = val


# pylint: disable=too-many-branches, too-many-statements
def build_dynamic_widget(
    config: dict[str, Any], descriptions: dict[str, Any] = None, running_reference: str = None
) -> QWidget:
    """
    Recursive function to build widgets.
    - If 'title' is None, it acts as the Root container (QWidget).
    - If 'title' is set, it creates a CollapsibleBox.

    Parameters
    ----------
    config : dict[str, Any]
        The configuration dictionary.
    descriptions : dict[str, Any], optional
        The descriptions for the config values, by default None
    running_reference : str, optional
        The running reference for the current config level, by default None

    Returns
    -------
    QWidget
        The generated widget.
    """
    config_to_display = config.copy()
    if running_reference is None:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignTop)
        misc_config = {}
        for key, value in config.items():
            if not isinstance(value, dict):
                misc_config[key] = value
                del config_to_display[key]
        config_to_display[MISC_TITLE] = misc_config

    else:
        title = running_reference.split(".")[-1].replace("_", " ").upper()

        container = CollapsibleBox(title=title, start_open=running_reference in START_OPEN)

    for key, value in config_to_display.items():

        desc_text = ""
        sub_desc = None
        if descriptions and isinstance(descriptions, dict):
            desc_text = descriptions.get(key, "")
            if isinstance(desc_text, dict):
                sub_desc = desc_text
                desc_text = ""

        if isinstance(value, dict):
            new_running_reference = key if running_reference is None else f"{running_reference}.{key}"
            sub_widget = build_dynamic_widget(value, sub_desc, running_reference=new_running_reference)

            if running_reference is None:
                layout.addWidget(sub_widget)
            else:
                container.add_widget(sub_widget)

            continue

        w = None
        name = key.replace("_", " ")
        if isinstance(value, bool):
            w = create_widget(name="", widget_type="CheckBox", value=value)
        elif isinstance(value, int):
            w = create_widget(name=name, widget_type="SpinBox", value=value)
        elif isinstance(value, float):
            if should_use_line_edit_for_float(value):
                w = create_widget(name=name, widget_type="LineEdit", value=repr(value))
            else:
                w = create_widget(name=name, widget_type="FloatSpinBox", value=value)
        elif isinstance(value, (str, list)) or value is None:
            w = create_widget(name=name, widget_type="LineEdit", value=str(value))

        if w is None:
            continue
        w.changed.connect(lambda val, k=key: on_config_value_changed(f"{running_reference}.{k}", val))
        if desc_text:
            w.native.setToolTip(desc_text)

        # Create Row for Widgets
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 5, 0, 5)
        label_widget = QLabel(key)
        label_widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label_widget.setToolTip(desc_text)
        row_layout.addWidget(label_widget)
        row_layout.addWidget(w.native)
        if desc_text != "":
            row_layout.addWidget(create_info_icon(desc_text))

        # Add Row to Container
        if running_reference is None:
            layout.addWidget(row_widget)
        else:
            container.add_widget(row_widget)

    # Handle ScrollArea (Only run at the root level to prevent multiple layers of scroll view)
    if running_reference is None:
        scroll = QScrollArea()
        scroll.setWidget(container)
        scroll.setWidgetResizable(True)
        return scroll
    return container


def write_new_default_config(config_path: Path):
    """
    Writes a default config file to the provided path using the topostats backend

    Parameters
    ----------
    config_path : Path
        The path to write the config file to.
    """
    args = Namespace()
    args.config = None
    args.filename = config_path.name
    args.output_dir = config_path.parent
    args.module = "topostats"
    write_config_with_comments(args)


def get_current_config_path() -> str | None:
    """
    Returns the current config path

    Returns
    -------
    str | None
        The current config path.
    """
    return current_config_path


def load_config_impl(viewer: Viewer, config_path: Path | None = None, use_default: bool = False) -> bool:
    """
    Loads config file using default if no path is provided and asking for data from user as required

    Parameters
    ----------
    viewer : Viewer
        The napari viewer.
    config_path : Path | None, optional
        The path to the config file, by default None
    use_default : bool, optional
        Whether to use the default config, by default False

    Returns
    -------
    bool
        True if the config was loaded successfully, False otherwise.
    """
    # pylint: disable=global-statement
    global comment_descriptions, config_wrapper, full_config_container, current_config_path  # Updated global name
    if config_path is None:
        if use_default:
            config_dir = Path(user_config_dir("TopoStats", "Napari"))
            config_path = config_dir / "config.yaml"
            if not config_path.exists():
                write_new_default_config(config_path)
        else:
            # If no path provided, prompt the user via a standard file dialog.
            file_path, _ = QFileDialog.getOpenFileName(
                parent=None,
                caption="Select Config File",
                filter="YAML Files (*.yaml *.yml);;JSON Files (*.json)",
            )
            if not file_path:
                # User cancelled the file selection; do nothing.
                return False
            config_path = Path(file_path)
            widget = load_config
            widget.viewer.value = viewer
            widget.config_path.value = config_path
    current_config_path = str(config_path)

    try:
        with open(config_path, encoding="utf-8") as f:
            if config_path.suffix.lower() in [".yaml", ".yml"]:
                config = yaml.safe_load(f)
            elif config_path.suffix.lower() == ".json":
                config = json.load(f)
            else:
                show_error_dialog("Unsupported config format.")
                return False
    except (
        FileNotFoundError,
        PermissionError,
        yaml.YAMLError,
        json.JSONDecodeError,
        UnicodeDecodeError,
        OSError,
    ) as e:
        show_error_dialog(f"Failed to load config: {e}")
        return False
    comment_descriptions = extract_inline_comments(config_path)
    if config is None:
        show_error_dialog("Please select a file containing valid config data.")
        return False
    config_wrapper = ConfigWrapper(config)

    full_config_container = build_dynamic_widget(config, comment_descriptions)
    if full_config_container is None:
        show_error_dialog("Failed to create full config container.")
        return False
    widget_manager = get_widget_manager()
    if "Edit Full Config" not in widget_manager.get_docked_widgets():

        # Create a button to open the config editor
        btn = QPushButton("Edit Config")
        btn.clicked.connect(open_config_editor)
        docked = widget_manager.add_docked_widget(btn, name="Edit Full Config")

        # Remove from state.docked_widgets when widget is closed
        docked.visibilityChanged.connect(
            lambda visible: (
                widget_manager.remove_docked_widget("Edit Full Config")
                if not visible and "Edit Full Config" in widget_manager.get_docked_widgets()
                else None
            )
        )

    return True


@magicgui(
    config_path={
        "label": "Config file",
        "mode": "r",
        "filter": "*.yaml;*.json",
    },  # Added .json filter
    call_button="Load Config",
    auto_call=True,
)
def load_config(viewer: Viewer, config_path: Path | None = None) -> bool:
    """
    Load a configuration file and build a dynamic widget to edit it.
    This is a magicgui function that can be called directly from the napari GUI and is an example of a hardcoded
    function being implemented using the dynamic function widget system.

    Parameters
    ----------
    viewer : Viewer
        The napari viewer.
    config_path : Path | None, optional
        The path to the config file, by default None

    Returns
    -------
    bool
        True if the config was loaded successfully, False otherwise.
    """
    return load_config_impl(viewer, config_path)


def set_up_load_config_widget(widget: FunctionGui):
    """
    Attach a success/error label under the FunctionGui call button.

    Parameters
    ----------
    widget : magicgui.widgets.FunctionGui
        The widget to attach the label to.
    """

    def on_success(result: bool):
        if result:
            widget.set_status_message("✅ Configuration loaded successfully!")
        else:
            widget.set_status_message("❌ Configuration did not load.")

    widget.called.connect(on_success)


def save_as_default_config(config: dict[str, Any]):
    """
    Saves the config as the new default (to the user config directory)

    Parameters
    ----------
    config : dict[str, Any]
        The config to save.
    """
    config_dir = Path(user_config_dir("TopoStats", "Napari"))
    config_path = config_dir / "config.yaml"
    config_dir.mkdir(parents=True, exist_ok=True)
    save_config_to_file(config_path, config)


def add_save_as_default_button(widget: QWidget):
    """
    Add a 'Save as Default' button to the load_config widget.

    Parameters
    ----------
    widget : magicgui.widgets.FunctionGui
        The widget to add the button to.
    """
    button_row = QHBoxLayout()
    save_button = QPushButton("Save as Default Config")
    save_button.setToolTip("Save the currently loaded configuration as the default config.")

    def on_save_clicked():
        if config_wrapper is None:
            show_error_dialog("No configuration loaded to save.")
            return
        full_config = config_wrapper.unflatten()
        save_as_default_config(full_config)
        widget.set_status_message("✅ New default configuration saved!")

    save_button.clicked.connect(on_save_clicked)

    button_row.addWidget(save_button)
    widget.native.layout().insertLayout(2, button_row)


attach_status_label(load_config)
set_up_load_config_widget(load_config)
add_save_as_default_button(load_config)


def extract_inline_comments(yaml_path: Path, top_level_key: str = None) -> dict[str, str]:
    """
    Extracts inline comments from a YAML file.

    Parameters
    ----------
    yaml_path : Path
        The path to the YAML file.
    top_level_key : str, optional
        The top level key to extract comments from, by default None

    Returns
    -------
    dict[str, str]
        A dictionary of comments.
    """
    comment_map = {}
    key_stack = []

    if not yaml_path.exists():
        show_error_dialog(f"Error: YAML file not found at {yaml_path}")
        return {}

    with open(yaml_path, encoding="utf-8") as f:
        for line in f:
            stripped_line = line.strip()

            if not stripped_line or stripped_line.startswith("#"):
                continue

            match = re.match(r"^(\s*)([a-zA-Z0-9_]+):\s*(?:[^#\n]*?)(?:#\s*(.*))?$", line)

            if match:
                indent_str, key_name, comment_text = match.groups()
                # Infer hierarchy depth from indentation; YAML uses 2 spaces per level here.
                indent_level = len(indent_str.replace("\t", "  ")) // 2

                key_stack = key_stack[:indent_level]
                key_stack.append(key_name)

                full_yaml_key_path = ".".join(key_stack)
                final_key_for_map = full_yaml_key_path

                if top_level_key:
                    if full_yaml_key_path == top_level_key:
                        final_key_for_map = ""
                    elif full_yaml_key_path.startswith(top_level_key + "."):
                        final_key_for_map = full_yaml_key_path[len(top_level_key) + 1 :]

                if comment_text is not None and final_key_for_map:
                    comment_map[final_key_for_map] = comment_text.strip()
    return unflatten_dict(comment_map)


def create_info_icon(tooltip_text: str) -> QToolButton:
    """
    Creates an info icon that can be hovered over to explain each config attribute

    Parameters
    ----------
    tooltip_text : str
        The text to display in the tooltip.

    Returns
    -------
    QToolButton
        The info icon button.
    """
    button = QToolButton()
    icon = QIcon.fromTheme("help-about")

    if icon and not icon.isNull():
        button.setIcon(icon)
    else:
        button.setText("?")
        font = button.font()
        font.setBold(True)
        button.setFont(font)

    button.setToolTip(tooltip_text)
    button.setAutoRaise(True)
    button.setCursor(Qt.WhatsThisCursor)
    return button


# pylint: disable=too-many-statements
def open_config_editor():
    """Opens and renders the config editor with only certain top level keys available"""
    # pylint: disable=global-variable-not-assigned
    global config_wrapper, full_config_container

    if config_wrapper is None:
        show_error_dialog("No config loaded.")
        return

    fresh_container = build_dynamic_widget(get_current_config(), comment_descriptions)
    fresh_container.setFrameShape(QFrame.NoFrame)
    fresh_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    dialog = QDialog()
    dialog.setStyleSheet("font-size: 9pt;")
    dialog.setWindowTitle("Edit Config")
    dialog.setMinimumWidth(550)
    screen_height = QGuiApplication.primaryScreen().availableGeometry().height()
    dialog.setMaximumHeight(int(screen_height * 0.9))

    main_layout = QVBoxLayout(dialog)
    main_layout.addWidget(fresh_container)

    button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    save_button = QPushButton("Save Config to File")
    button_box.addButton(save_button, QDialogButtonBox.ActionRole)

    set_as_default_button = QPushButton("Set config as your default")
    button_box.addButton(set_as_default_button, QDialogButtonBox.ActionRole)

    # Temporary status label for feedback when setting default

    def set_as_default():
        config_dir = Path(user_config_dir("TopoStats", "Napari"))
        config_dir.mkdir(parents=True, exist_ok=True)
        default_config_path = config_dir / "config.yaml"
        save_config_to_file(default_config_path, get_current_config())

        dialog.set_status_message("✅ Default config saved")

    def save_to_file():

        file_path, _ = QFileDialog.getSaveFileName(
            parent=dialog,
            caption="Save Config As",
            filter="YAML Files (*.yaml *.yml);;JSON Files (*.json)",
        )
        if not file_path:
            dialog.set_status_message("Config save cancelled.")
            return
        save_config_to_file(Path(file_path), get_current_config())

        dialog.set_status_message("✅ Config saved to file")

    save_button.clicked.connect(save_to_file)
    set_as_default_button.clicked.connect(set_as_default)
    button_box.accepted.connect(dialog.accept)
    button_box.rejected.connect(dialog.reject)

    attach_status_label(dialog)
    main_layout.addWidget(button_box)

    dialog.adjustSize()
    if dialog.exec_():
        config_wrapper.flat.update(updated_values)
        print("Config updated.")
        # Optionally refresh the full container for other use
        full_config_container = build_dynamic_widget(get_current_config(), comment_descriptions)
        save_current_config_as_temp()


def save_config_to_file(file_path: Path, full_config: dict[str, Any]):
    """
    Saves the config to a file with comments preserved, displaying an error message if it fails.

    Parameters
    ----------
    file_path : Path
        The path to save the file to.
    full_config : dict[str, Any]
        The config to save.
    """
    try:
        if file_path.suffix.lower() == ".json":
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(full_config, f, indent=2)
        else:
            # For YAML files, use write_config_with_comments if we have comment descriptions
            if comment_descriptions:
                # Build the comments dict in the format expected by write_config_with_comments
                # It expects nested dict structure matching the config
                comments_nested = _unflatten_comments(comment_descriptions)

                # Use write_config_with_comments to preserve inline comments
                _write_yaml_with_inline_comments(file_path, full_config, comments_nested)
            else:
                # Fallback to standard YAML dump if no comments available
                with open(file_path, "w", encoding="utf-8") as f:
                    yaml.safe_dump(full_config, f, sort_keys=False)
        print(f"Config saved to {file_path}")
    except (OSError, TypeError, yaml.YAMLError) as e:
        show_error_dialog(f"Failed to save config: {e}")


def _unflatten_comments(flat_comments: dict[str, str]) -> dict:
    """
    Convert flat dotted-key comments back to nested dictionary structure.

    Parameters
    ----------
    flat_comments : dict[str, str]
        The flat comments dictionary.

    Returns
    -------
    dict
        The unflattened comments dictionary.
    """
    result = {}
    for key, comment in flat_comments.items():
        keys = key.split(".")
        d = result
        for part in keys[:-1]:
            d = d.setdefault(part, {})
        d[keys[-1]] = comment
    return result


def _write_yaml_with_inline_comments(file_path: Path, config: dict, comments: dict):
    """
    Write YAML config file with inline comments preserved.

    Parameters
    ----------
    file_path : Path
        Path to write the YAML file
    config : dict
        Configuration dictionary to write
    comments : dict
        Nested dictionary of comments matching config structure
    """
    lines = []

    def format_value(value: Any) -> str:
        """Format a value as YAML inline style"""
        if isinstance(value, list):
            # Format lists in flow style [item1, item2]
            formatted_items = []
            for item in value:
                if item is None:
                    formatted_items.append("null")
                elif isinstance(item, str):
                    formatted_items.append(f"'{item}'")
                else:
                    formatted_items.append(str(item))
            return f"[{', '.join(formatted_items)}]"
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, str):
            # Check if string needs quoting
            if any(
                c in value
                for c in [":", "#", "[", "]", "{", "}", ",", "&", "*", "?", "|", "-", "<", ">", "=", "!", "%", "@", "`"]
            ):
                return f"'{value}'"
            return value
        return str(value)

    def write_dict(d: dict, comment_dict: dict, indent: int = 0):
        """Recursively write dictionary with comments"""
        indent_str = "  " * indent

        for key, val in d.items():
            key_comment = comment_dict.get(key) if isinstance(comment_dict, dict) else None

            if isinstance(val, dict):
                # Nested dictionary - only use comment if it's a string, not a dict
                if key_comment and isinstance(key_comment, str):
                    lines.append(f"{indent_str}{key}: # {key_comment}")
                else:
                    lines.append(f"{indent_str}{key}:")
                # Pass the comment dict for children if it exists and is a dict
                write_dict(val, key_comment if isinstance(key_comment, dict) else {}, indent + 1)
            else:
                # Simple value (including lists) - only use string comments
                formatted_val = format_value(val)
                if key_comment and isinstance(key_comment, str):
                    lines.append(f"{indent_str}{key}: {formatted_val} # {key_comment}")
                else:
                    lines.append(f"{indent_str}{key}: {formatted_val}")

    write_dict(config, comments)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def save_current_config_as_temp(overides: dict[str, Any] | None = None):
    """
    Saves the current config as a temporary file with optional overides.
    This is used for maintaining an up to date config file and path for TopoStats backend functions.

    Parameters
    ----------
    overides : dict[str, Any] | None
        A dictionary of config keys and values to override in the saved config.
    """
    # pylint: disable=global-statement
    global current_config_path
    full_current_config = get_current_config()

    if overides:
        for key, value in overides.items():
            config_wrapper.flat[key] = value
    config_dir = Path(user_config_dir("TopoStats", "Napari"))
    config_path = config_dir / "_temp_config.yaml"
    config_dir.mkdir(parents=True, exist_ok=True)
    save_config_to_file(config_path, full_current_config)
    current_config_path = str(config_path)


def get_current_config(flat: bool = False) -> dict[str, Any]:
    """Returns the current config with any updates from the edit config window applied"""
    if flat:
        return config_wrapper.flat
    full_current_config = config_wrapper.unflatten()
    return full_current_config


def config_loaded() -> bool:
    """
    Returns True if a config has been loaded, False otherwise.

    Returns
    -------
    bool
        True if a config has been loaded, False otherwise.
    """
    return config_wrapper is not None and full_config_container is not None


def get_topostats_default_config():
    """
    Returns the default config from the TopoStats backend as a dictionary.

    Returns
    -------
    dict
        The default config.
    """
    # this function is currently bugged for some reason, it seems write_config_with_comments fails to write the file
    config_path = Path(user_config_dir("TopoStats", "Napari")) / "default_config.yaml"
    write_new_default_config(config_path)

    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config


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
