"""Provides functionality for loading and editting config files"""

import json
import re
from argparse import Namespace
from pathlib import Path
from typing import Any

import yaml
from magicgui import magicgui
from magicgui.widgets import Container, create_widget
from napari.viewer import Viewer
from platformdirs import user_config_dir
from qtpy.QtCore import QTimer, Qt
from qtpy.QtGui import QIcon
from qtpy.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
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


config_wrapper = None
full_config_container = None
comment_descriptions = {}
# Globals store currently loaded config and UI state so dialogs/widgets can reuse them.


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
        result = {}
        for k, v in self.flat.items():
            keys = k.split(".")
            d = result
            for part in keys[:-1]:
                d = d.setdefault(part, {})
            d[keys[-1]] = v
        return result


def collect_values(container: Container) -> dict[str, Any]:
    """Collect config values from edit config window"""
    result = {}
    for widget in container:
        val = widget.value
        name = widget.name
        # Allow lists to be entered as literal strings and parsed back to Python types.
        if isinstance(val, str) and val.strip().startswith("["):
            try:
                # pylint: disable=import-outside-toplevel
                import ast

                val = ast.literal_eval(val)
            except (ValueError, SyntaxError):
                pass
        # Treat the literal string "None" as an actual None value when saving.
        elif val == "None":
            val = None
        result[name] = val
    return result


def build_dynamic_widget(flat_config: dict[str, Any], descriptions: dict[str, str] = None) -> Container:
    """Builds a widget for each editable item in the config and add it to a container"""
    widgets = []
    # Choose an appropriate widget type based on the value's Python type.
    for key, value in flat_config.items():
        current_tooltip_text = descriptions.get(key, "") if descriptions else ""

        if isinstance(value, bool):
            w = create_widget(name=key, widget_type="CheckBox", value=value)
        elif isinstance(value, int):
            w = create_widget(name=key, widget_type="SpinBox", value=value)
        elif isinstance(value, float):
            w = create_widget(name=key, widget_type="FloatSpinBox", value=value)
        elif isinstance(value, str):
            w = create_widget(name=key, widget_type="LineEdit", value=value)
        elif isinstance(value, list):
            w = create_widget(name=key, widget_type="LineEdit", value=str(value))
        elif value is None:
            w = create_widget(name=key, widget_type="LineEdit", value="None")
        else:
            continue

        label = QLabel(w.name)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        if current_tooltip_text:
            # Reuse inline YAML comments as tooltips for both the editor and label.
            w.native.setToolTip(current_tooltip_text)
            label.setToolTip(current_tooltip_text)

        w.label = label
        widgets.append(w)
    return Container(widgets=widgets)


def write_new_default_config(config_path: Path):
    """Writes a default config file to the provided path using the topostats backend"""
    args = Namespace()
    args.config = None
    args.filename = config_path.name
    args.output_dir = config_path.parent
    args.module = "topostats"
    write_config_with_comments(args)


def load_config_impl(viewer: Viewer, config_path: Path | None = None, use_default: bool = False):
    """Loads config file using default if no path is provided and asking for data from user as required"""
    # pylint: disable=global-statement
    global comment_descriptions, config_wrapper, full_config_container  # Updated global name
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

    full_config_container = build_dynamic_widget(config_wrapper.flat.copy(), comment_descriptions)
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
    return comment_map


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

    # Keys to include
    EDITABLE_TOP_LEVEL_KEYS = {"filter", "grains"}

    # Keys to exclude
    EXCLUDED_KEYS = {"filter.run", "grains.run"}

    # Restrict editing to select top-level blocks while avoiding run toggles.
    filtered_flat_config = {
        k: v
        for k, v in config_wrapper.flat.items()
        if any(k.startswith(f"{prefix}.") for prefix in EDITABLE_TOP_LEVEL_KEYS) and k not in EXCLUDED_KEYS
    }

    # Mirror the same filtering for tooltip descriptions.
    filtered_descriptions = {
        k: v
        for k, v in comment_descriptions.items()
        if any(k.startswith(f"{prefix}.") for prefix in EDITABLE_TOP_LEVEL_KEYS) and k not in EXCLUDED_KEYS
    }

    fresh_container = build_dynamic_widget(filtered_flat_config, filtered_descriptions)

    dialog = QDialog()
    dialog.setWindowTitle("Edit Filters and Grains Config")
    dialog.resize(600, 800)

    main_layout = QVBoxLayout(dialog)
    scroll_area = QScrollArea()
    scroll_area.setWidgetResizable(True)

    scroll_content = QWidget()
    scroll_layout = QVBoxLayout(scroll_content)

    # Build one row per editable field with its label, widget, and optional info icon.
    for widget in fresh_container:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.addWidget(widget.label)
        row_layout.addWidget(widget.native)

        tooltip = widget.native.toolTip()
        if tooltip:
            info_btn = create_info_icon(tooltip)
            row_layout.addWidget(info_btn)

        scroll_layout.addWidget(row)

    scroll_content.setLayout(scroll_layout)
    scroll_area.setWidget(scroll_content)

    button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    save_button = QPushButton("Save Config to File")
    button_box.addButton(save_button, QDialogButtonBox.ActionRole)

    set_as_default_button = QPushButton("Set config as your default")
    button_box.addButton(set_as_default_button, QDialogButtonBox.ActionRole)

    # Temporary status label for feedback when setting default
    status_label = QLabel("")
    status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

    def set_as_default():
        updated_values = collect_values(fresh_container)
        config_wrapper.flat.update(updated_values)
        full_config = config_wrapper.unflatten()

        config_dir = Path(user_config_dir("TopoStats", "Napari"))
        config_dir.mkdir(parents=True, exist_ok=True)
        default_config_path = config_dir / "config.yaml"
        save_config_to_file(default_config_path, full_config)

        status_label.setText("✅ Default config saved")
        # Clear the transient status message after a short delay.
        QTimer.singleShot(3000, lambda: status_label.setText(""))

    def save_to_file():
        updated_values = collect_values(fresh_container)
        config_wrapper.flat.update(updated_values)
        full_config = config_wrapper.unflatten()

        file_path, _ = QFileDialog.getSaveFileName(
            parent=dialog,
            caption="Save Config As",
            filter="YAML Files (*.yaml *.yml);;JSON Files (*.json)",
        )
        if not file_path:
            status_label.setText("Config save cancelled.")
            QTimer.singleShot(3000, lambda: status_label.setText(""))
            return
        save_config_to_file(Path(file_path), full_config)

        status_label.setText("✅ Config saved to file")
        # Clear the transient status message after a short delay.
        QTimer.singleShot(3000, lambda: status_label.setText(""))

    save_button.clicked.connect(save_to_file)
    set_as_default_button.clicked.connect(set_as_default)
    button_box.accepted.connect(dialog.accept)
    button_box.rejected.connect(dialog.reject)

    main_layout.addWidget(scroll_area)
    main_layout.addWidget(status_label)
    main_layout.addWidget(button_box)

    if dialog.exec_():
        updated_values = collect_values(fresh_container)
        config_wrapper.flat.update(updated_values)
        print("Config updated.")
        # Optionally refresh the full container for other use
        full_config_container = build_dynamic_widget(config_wrapper.flat.copy(), comment_descriptions)


def save_config_to_file(file_path: Path, full_config: dict[str, Any]):
    """Saves the config to a file, displaying an error message if it fails."""
    try:
        print(json.dumps(full_config, indent=2))
        if file_path.suffix.lower() == ".json":
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(full_config, f, indent=2)
        else:
            with open(file_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(full_config, f, sort_keys=False)
        print(f"Config saved to {file_path}")
    except (OSError, TypeError, yaml.YAMLError) as e:
        show_error_dialog(f"Failed to save config: {e}")
