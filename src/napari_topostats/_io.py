"""Provides functionality for loading and editting config files"""

import contextlib
import json
import re
from argparse import Namespace
from pathlib import Path
from typing import Any

import yaml
from magicgui import magicgui
from magicgui.widgets import create_widget
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

from . import _state as state
from ._alerts import attach_status_label, show_error_dialog

try:
    from topostats.config import write_config_with_comments
except ImportError:
    show_error_dialog(
        f"TopoStats version {topostats_version} is not supported. Please install the latest version of TopoStats"
        f"or if that fails, install version {state.MIN_TOPOSTATS_VERSION}."
    )


MISC_TITLE = "Batch Settings"
# Globals store currently loaded config and UI state so dialogs/widgets can reuse them.
config_wrapper = None
full_config_container = None
comment_descriptions = {}
current_config_path = None
updated_values = {}


def _unflatten(flat: dict) -> dict:
    """Function used for reverting to the dict form where keys can correspond to dict values like json format"""
    result = {}
    for k, v in flat.items():
        keys = k.split(".")
        d = result
        for part in keys[:-1]:
            d = d.setdefault(part, {})
        d[keys[-1]] = v
    return result


class ConfigWrapper:
    """
    A wrapper for configuration dictionaries to provide a flat view and unflattening functionality.
    """

    def __init__(self, config: dict):
        self.original = config
        self.flat = self._flatten(config)

    def _flatten(self, d, parent_key="", sep="."):
        items = {}
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.update(self._flatten(v, new_key, sep=sep))
            else:
                items[new_key] = v
        return items

    def unflatten(self) -> dict:
        """Function used for reverting to the dict form where keys can correspond to dict values like json format"""
        return _unflatten(self.flat)


class CollapsibleBox(QWidget):
    """
    A widget to contain over widgets in a collapsible area
    """

    def __init__(self, title="", parent=None, start_open=False):
        super().__init__(parent)

        # Main layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Toggle Button (The Header)
        self.toggle_button = QPushButton(title)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(start_open)
        self.toggle_button.setStyleSheet(
            "QPushButton { text-align: left; font-weight: bold; padding: 5px; border: none; }"
            "QPushButton:hover { background-color: #555d68; }"
        )
        self.toggle_button.toggled.connect(self.on_toggle)
        self.layout.addWidget(self.toggle_button)

        # Content Area
        self.content_area = QFrame()
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(10, 10, 10, 10)
        self.layout.addWidget(self.content_area)

        # Start at given state
        self.on_toggle(start_open)

    def on_toggle(self, checked):
        """
        Set behaviour for expanding/ collapsing when clicked

        Parameters
        ----------
        checked : bool
            The state toggle has been changed to
        """
        self.content_area.setVisible(checked)
        arrow = "▼" if checked else "▶"
        self.toggle_button.setText(f"{arrow}  {self.toggle_button.text()[3:]}")

    def add_widget(self, widget):
        """
        Adds the widget to the collapsable view

        Parameters
        ----------
        widget : QWidget
            The widget to add
        """
        self.content_layout.addWidget(widget)


def should_use_line_edit_for_float(value: float) -> bool:
    """Determine if a float value should be edited with a LineEdit instead of a FloatSpinBox."""
    return abs(value) != 0 and (abs(value) < 1e-4 or abs(value) > 1e6)


# pylint: disable=global-variable-not-assigned
def on_config_value_changed(key: str, val: Any):
    """Update the config wrapper when a value changes"""
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
        container = CollapsibleBox(title=f"   {title}")

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
                w.native.setDecimals(4)
                w.value = value
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
    """Writes a default config file to the provided path using the topostats backend"""
    args = Namespace()
    args.config = None
    args.filename = config_path.name
    args.output_dir = config_path.parent
    args.module = "topostats"
    write_config_with_comments(args)


def get_current_config_path() -> str | None:
    """Returns the current config path"""
    return current_config_path


def load_config_impl(viewer: Viewer, config_path: Path | None = None, use_default: bool = False):
    """Loads config file using default if no path is provided and asking for data from user as required"""
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
    print(f"Current config path set to {current_config_path}")

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
    if "Edit Full Config" not in state.docked_widgets:
        # Create a button to open the config editor
        btn = QPushButton("Edit Config")
        btn.clicked.connect(open_config_editor)
        docked = viewer.window.add_dock_widget(btn, name="Edit Full Config")
        # Remove from state.docked_widgets when widget is closed
        docked.visibilityChanged.connect(
            lambda visible: (
                state.docked_widgets.remove("Edit Full Config")
                if not visible and "Edit Full Config" in state.docked_widgets
                else None
            )
        )
        # Add the button to the docked widgets list so it can be accessed
        state.docked_widgets.append("Edit Full Config")

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
def load_config(viewer: Viewer, config_path: Path | None = None):
    """
    Load a configuration file and build a dynamic widget to edit it.
    This is a magicgui function that can be called directly from the napari GUI and is an example of a hardcoded
    function being implemented using the dynamic function widget system.
    """
    return load_config_impl(viewer, config_path)


def set_up_load_config_widget(widget):
    """Attach a success/error label under the FunctionGui call button."""

    def on_success(result):
        if result:
            widget.set_status_message("✅ Configuration loaded successfully!")
        else:
            widget.set_status_message("❌ Configuration did not load.")

    widget.called.connect(on_success)


def save_as_default_config(config: dict[str, Any]):
    """Saves the config as the new default"""
    config_dir = Path(user_config_dir("TopoStats", "Napari"))
    config_path = config_dir / "config.yaml"
    config_dir.mkdir(parents=True, exist_ok=True)
    save_config_to_file(config_path, config)


def add_save_as_default_button(widget):
    """Add a 'Save as Default' button to the load_config widget."""
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
    (This function remains the same as our last debugged version)
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
    return _unflatten(comment_map)


def create_info_icon(tooltip_text: str) -> QToolButton:
    """Creates an info icon that can be hovered over to explain each config attribute"""
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
    """Saves the config to a file with comments preserved, displaying an error message if it fails."""
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

    Example:
        {"filter.threshold": "comment"} -> {"filter": {"threshold": "comment"}}
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

    def format_value(value):
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

    def write_dict(d, comment_dict, indent=0):
        """Recursively write dictionary with comments"""
        indent_str = "  " * indent

        for key, val in d.items():
            key_comment = comment_dict.get(key, None) if isinstance(comment_dict, dict) else None

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


def get_current_config() -> dict[str, Any]:
    """Returns the current config with any updates from the edit config window applied"""
    full_current_config = config_wrapper.unflatten()
    return full_current_config


def config_loaded() -> bool:
    """Returns True if a config has been loaded, False otherwise."""
    return config_wrapper is not None and full_config_container is not None
