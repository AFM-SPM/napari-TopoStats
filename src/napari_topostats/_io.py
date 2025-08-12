
import json
import re
from pathlib import Path
from typing import Any, Dict

import yaml
from magicgui import magicgui
from magicgui.widgets import Container, create_widget
from napari.viewer import Viewer
from qtpy.QtWidgets import QLabel, QPushButton
from qtpy.QtCore import Qt
from topostats.io import write_config_with_comments
from qtpy.QtWidgets import QDialog, QScrollArea, QVBoxLayout, QHBoxLayout, QWidget, QDialogButtonBox, QFileDialog, QToolButton
from qtpy.QtGui import QIcon

from . import _state as state
from ._alerts import show_error_dialog

config_wrapper = None
full_config_container = None
comment_descriptions = {}

class ConfigWrapper:
    """
    A wrapper for configuration dictionaries to provide a flat view and unflattening functionality.
    """
    def __init__(self, config: dict):
        self.original = config
        self.flat = self._flatten(config)

    def _flatten(self, d, parent_key='', sep='.'):
        items = {}
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.update(self._flatten(v, new_key, sep=sep))
            else:
                items[new_key] = v
        return items

    def unflatten(self) -> dict:
        result = {}
        for k, v in self.flat.items():
            keys = k.split('.')
            d = result
            for part in keys[:-1]:
                d = d.setdefault(part, {})
            d[keys[-1]] = v
        return result
    
def collect_values(container: Container) -> Dict[str, Any]:
    result = {}
    for widget in container:
        val = widget.value
        name = widget.name
        if isinstance(val, str) and val.strip().startswith("["):
            try:
                import ast
                val = ast.literal_eval(val)
            except (ValueError, SyntaxError):
                pass
        elif val == "None":
            val = None
        result[name] = val
    return result
    
def build_dynamic_widget(flat_config: Dict[str, Any], descriptions: Dict[str, str] = None) -> Container:
    widgets = []
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
            w.native.setToolTip(current_tooltip_text)
            label.setToolTip(current_tooltip_text)

        w.label = label
        widgets.append(w)
    return Container(widgets=widgets)

@magicgui(
    config_path={"label": "Config file", "mode": "r", "filter": "*.yaml;*.json"}, # Added .json filter
    call_button="Load Config",
    auto_call=True,
)
def load_config(viewer: Viewer, config_path: Path | None = None):
    """
    Load a configuration file and build a dynamic widget to edit it.
    This is a magicgui function that can be called directly from the napari GUI and is an example of a hardcoded
    function being implemented using the dynamic function widget system. 
    """
    global comment_descriptions, config_wrapper, full_config_container  # Updated global name
    if config_path is None:
        write_config_with_comments()
        config_path = Path("config.yaml")

    try:
        with open(config_path, "r") as f:
            if config_path.suffix.lower() in [".yaml", ".yml"]:
                config = yaml.safe_load(f)
            elif config_path.suffix.lower() == ".json":
                config = json.load(f)
            else:
                show_error_dialog("Unsupported config format.")
                return
    except Exception as e:
        show_error_dialog(f"Failed to load config: {e}")
        return

    comment_descriptions = extract_inline_comments(config_path)
    
    config_wrapper = ConfigWrapper(config)

    full_config_container = build_dynamic_widget(config_wrapper.flat.copy(), comment_descriptions)
    if full_config_container is None:
        show_error_dialog("Failed to create full config container.")
        return
    if "Edit Full Config" not in state.docked_widgets:
        # Create a button to open the config editor
        btn = QPushButton("Edit Config")
        btn.clicked.connect(lambda: open_config_editor(viewer))
        viewer.window.add_dock_widget(btn, name="Edit Full Config")
        # Add the button to the docked widgets list so it can be accessed
        state.docked_widgets.append("Edit Full Config")

def extract_inline_comments(yaml_path: Path, top_level_key: str = None) -> Dict[str, str]:
    """
    Extracts inline comments from a YAML file.
    (This function remains the same as our last debugged version)
    """
    comment_map = {}
    key_stack = [] 

    if not yaml_path.exists():
        show_error_dialog(f"Error: YAML file not found at {yaml_path}")
        return {}

    with open(yaml_path, "r") as f:
        for line_num, line in enumerate(f, 1):
            stripped_line = line.strip()

            if not stripped_line or stripped_line.startswith("#"):
                continue

            match = re.match(r"^(\s*)([a-zA-Z0-9_]+):\s*(?:[^#\n]*?)(?:#\s*(.*))?$", line)
            
            if match:
                indent_str, key_name, comment_text = match.groups()
                indent_level = len(indent_str.replace("\t", "  ")) // 2

                key_stack = key_stack[:indent_level]
                key_stack.append(key_name)

                full_yaml_key_path = ".".join(key_stack)
                final_key_for_map = full_yaml_key_path
                
                if top_level_key:
                    if full_yaml_key_path == top_level_key:
                        final_key_for_map = ""
                    elif full_yaml_key_path.startswith(top_level_key + "."):
                        final_key_for_map = full_yaml_key_path[len(top_level_key) + 1:]

                if comment_text is not None and final_key_for_map:
                    comment_map[final_key_for_map] = comment_text.strip()
    return comment_map

def create_info_icon(tooltip_text: str) -> QToolButton:
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

def open_config_editor(viewer: Viewer):
    global config_wrapper, full_config_container, comment_descriptions

    if config_wrapper is None:
        show_error_dialog("No config loaded.")
        return
    
    # Keys to include
    EDITABLE_TOP_LEVEL_KEYS = {"filter", "grains"}

    # Keys to exclude
    EXCLUDED_KEYS = {"filter.run", "grains.run"}

    filtered_flat_config = {
        k: v for k, v in config_wrapper.flat.items()
        if any(k.startswith(f"{prefix}.") for prefix in EDITABLE_TOP_LEVEL_KEYS)
        and k not in EXCLUDED_KEYS
    }

    filtered_descriptions = {
        k: v for k, v in comment_descriptions.items()
        if any(k.startswith(f"{prefix}.") for prefix in EDITABLE_TOP_LEVEL_KEYS)
        and k not in EXCLUDED_KEYS
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

    def save_to_file():
        updated_values = collect_values(fresh_container)
        config_wrapper.flat.update(updated_values)
        full_config = config_wrapper.unflatten()

        file_path, _ = QFileDialog.getSaveFileName(
            parent=dialog,
            caption="Save Config As",
            filter="YAML Files (*.yaml *.yml);;JSON Files (*.json)"
        )
        if file_path:
            try:
                if file_path.endswith(".json"):
                    with open(file_path, "w") as f:
                        json.dump(full_config, f, indent=2)
                else:
                    with open(file_path, "w") as f:
                        yaml.safe_dump(full_config, f, sort_keys=False)
                print(f"Config saved to {file_path}")
            except Exception as e:
                print(f"Failed to save config: {e}")

    save_button.clicked.connect(save_to_file)
    button_box.accepted.connect(dialog.accept)
    button_box.rejected.connect(dialog.reject)

    main_layout.addWidget(scroll_area)
    main_layout.addWidget(button_box)

    if dialog.exec_():
        updated_values = collect_values(fresh_container)
        config_wrapper.flat.update(updated_values)
        print("Config updated.")
        # Optionally refresh the full container for other use
        full_config_container = build_dynamic_widget(config_wrapper.flat.copy(), comment_descriptions)