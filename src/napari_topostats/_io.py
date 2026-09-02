"""Provides functionality for loading and editting config files"""

# pylint: disable=too-many-lines

import contextlib
import json
import re
import shutil
from argparse import Namespace
from pathlib import Path
from typing import Any, Literal

import yaml
from magicgui import magicgui
from magicgui.widgets import FunctionGui, create_widget
from napari.viewer import Viewer
from platformdirs import user_config_dir
from qtpy.QtCore import Qt
from qtpy.QtGui import QIcon
from qtpy.QtWidgets import (
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

from napari_topostats._alerts import attach_status_label, show_error_dialog
from napari_topostats._components import CollapsibleBox
from napari_topostats._state import MIN_TOPOSTATS_VERSION, get_loaded_function_path, get_widget_manager
from napari_topostats.utils import unflatten_dict

try:
    from forcestats.config import write_config_with_comments as write_config_with_comments_forcestats
except ModuleNotFoundError as error:
    if error.name != "forcestats":
        raise
    write_config_with_comments_forcestats = None

ConfigType = (
    Literal["topostats", "forcestats"] if write_config_with_comments_forcestats is not None else Literal["topostats"]
)

# pylint: disable=ungrouped-imports
try:
    from topostats.config import write_config_with_comments as write_config_with_comments_topostats
except ImportError:
    show_error_dialog(
        f"TopoStats version {topostats_version} is not supported. Please install the latest version of TopoStats"
        f"or if that fails, install version {MIN_TOPOSTATS_VERSION}."
    )


MISC_TITLE = "Batch Settings"
START_OPEN = {"filter", "grains"}
# Globals store currently loaded config and UI state so dialogs/widgets can reuse them.
config_wrappers = {}
comment_descriptions = {}
current_config_paths = {}
updated_values = {}


def _format_config_label(key: str) -> str:
    """
    Format a config key for display without changing the stored key.

    Parameters
    ----------
    key : str
        Configuration key to convert into a display label.

    Returns
    -------
    str
        Label with underscores replaced by spaces.
    """
    return key.replace("_", " ")


def _format_config_tooltip(key: str, description: str = "") -> str:
    """
    Build a tooltip that keeps the original config key visible.

    Parameters
    ----------
    key : str
        Original configuration key to show in the tooltip.
    description : str
        Optional explanatory text for the setting.

    Returns
    -------
    str
        Tooltip containing the key and, when present, its description.
    """
    if description:
        return f"{key}\n\n{description}"
    return key


class ConfigWrapper:
    """
    A wrapper for configuration dictionaries to provide a flat view and unflattening functionality.

    Parameters
    ----------
    config : dict
        The configuration dictionary.
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


def on_config_value_changed(key: str, val: Any, config_type: str = "topostats"):
    """
    Update the config wrapper when a value changes

    Parameters
    ----------
    key : str
        The key of the value that changed.
    val : Any
        The new value.
    config_type : str
        The module (usually topostats) whose config value is being updated.
    """
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
    if config_type not in updated_values:
        updated_values[config_type] = {}
    updated_values[config_type][key] = val


# pylint: disable=too-many-branches, too-many-statements
def build_dynamic_widget(
    config: dict[str, Any],
    descriptions: dict[str, Any] = None,
    running_reference: str = None,
    config_type: str = "topostats",
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
    config_type : str
        The module (usually topostats) whose config widget is being built.

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
        if misc_config:
            config_to_display[MISC_TITLE] = misc_config

    else:
        title = _format_config_label(running_reference.split(".")[-1]).title()

        container = CollapsibleBox(title=title, start_open=running_reference in START_OPEN, subtle=True)

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
            sub_widget = build_dynamic_widget(
                value, sub_desc, running_reference=new_running_reference, config_type=config_type
            )

            if running_reference is None:
                layout.addWidget(sub_widget)
            else:
                container.add_widget(sub_widget)

            continue

        w = None
        if isinstance(value, bool):
            w = create_widget(name="", widget_type="CheckBox", value=value)
        elif isinstance(value, int):
            w = create_widget(name="", widget_type="SpinBox", value=value)
        elif isinstance(value, float):
            if should_use_line_edit_for_float(value):
                w = create_widget(name="", widget_type="LineEdit", value=repr(value))
            else:
                w = create_widget(name="", widget_type="FloatSpinBox", value=value)
        elif isinstance(value, (str, list)) or value is None:
            w = create_widget(name="", widget_type="LineEdit", value=str(value))

        if w is None:
            continue
        w.changed.connect(
            lambda val, k=key: on_config_value_changed(f"{running_reference}.{k}", val, config_type=config_type)
        )
        tooltip_text = _format_config_tooltip(key, desc_text)
        w.native.setToolTip(tooltip_text)

        # Create Row for Widgets
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 5, 0, 5)
        label_widget = QLabel(_format_config_label(key))
        label_widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label_widget.setToolTip(tooltip_text)
        row_layout.addWidget(label_widget)
        row_layout.addWidget(w.native)
        row_layout.setStretch(1, 1)
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


def write_new_default_config(config_path: Path, config_type: str = "topostats"):
    """
    Writes a default config file to the provided path using the topostats backend

    Parameters
    ----------
    config_path : Path
        The path to write the config file to.
    config_type : str
        The module (usually topostats) to create the default config for.
    """
    args = Namespace()
    args.config = None
    args.filename = config_path.name
    args.output_dir = config_path.parent
    args.module = config_type
    if config_type == "topostats":
        write_config_with_comments_topostats(args)
    elif config_type == "forcestats":
        if write_config_with_comments_forcestats is None:
            raise RuntimeError("ForceStats must be installed to create a ForceStats configuration.")
        write_config_with_comments_forcestats(args)


def get_current_config_path(config_type: str = "topostats") -> str | None:
    """
    Returns the current config path

    Returns
    -------
    str | None
        The current config path.

    Parameters
    ----------
    config_type : str
        The module (usually topostats) whose current config path is returned.
    """
    return current_config_paths.get(config_type)


def load_config_impl(
    viewer: Viewer,
    config_path: Path | None = None,
    config_type: str = "topostats",
    use_default: bool = False,
    report_errors: bool = True,
) -> bool:
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
    config_type : str
        The module (usually topostats) to load the config for.
    report_errors : bool
        Whether loading failures should be shown in an error dialog.

    Returns
    -------
    bool
        True if the config was loaded successfully, False otherwise.
    """
    if config_path is None:
        if use_default:
            config_dir = Path(user_config_dir("TopoStats", "Napari"))
            config_path = config_dir / f"{config_type}_config.yaml"
            if not config_path.exists():
                config_dir.mkdir(parents=True, exist_ok=True)
                write_new_default_config(config_path, config_type=config_type)
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
        if report_errors:
            show_error_dialog(f"Failed to load config: {e}")
        return False
    current_config_paths[config_type] = str(config_path)
    comment_descriptions[config_type] = extract_inline_comments(config_path)
    if config is None:
        if report_errors:
            show_error_dialog("Please select a file containing valid config data.")
        return False
    config_wrappers[config_type] = ConfigWrapper(config)

    return True


@magicgui(
    config_path={
        "label": "Config file",
        "mode": "r",
        "filter": "*.yaml;*.json",
    },  # Added .json filter
    config_type={"label": "Config type"},
    call_button="Load Config",
)
def load_config(viewer: Viewer, config_path: Path | None = None, config_type: ConfigType = "topostats") -> bool:
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
    config_type : Literal["topostats", "forcestats"], optional
        The module (usually topostats) to load the config for.

    Returns
    -------
    bool
        True if the config was loaded successfully, False otherwise.
    """
    return load_config_impl(viewer, config_path, config_type=config_type)


def set_up_load_config_widget(widget: FunctionGui):
    """
    Attach a success/error label under the FunctionGui call button.

    Parameters
    ----------
    widget : magicgui.widgets.FunctionGui
        The widget to attach the label to.
    """
    attach_status_label(widget)

    def on_success(result: bool):
        """
        Function to run once the load_config function has been called.

        Parameters
        ----------
        result : bool
            Result of the loading of the config.
        """
        if result:
            widget.set_status_message("✅ Configuration loaded successfully!")
        else:
            widget.set_status_message("❌ Configuration did not load.")

    widget.called.connect(on_success)
    add_save_as_default_button(widget)


def save_as_default_config(config: dict[str, Any], config_type: str = "topostats"):
    """
    Saves the config as the new default (to the user config directory)

    Parameters
    ----------
    config : dict[str, Any]
        The config to save.
    config_type : str, optional
        The module (usually topostats) to save the default config for.
    """
    config_dir = Path(user_config_dir("TopoStats", "Napari"))
    config_path = config_dir / f"{config_type}_config.yaml"
    config_dir.mkdir(parents=True, exist_ok=True)
    save_config_to_file(config_path, config, config_type=config_type)


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
        """Save the config to the user config directory for the napari plugin so it persists between napari instances"""
        config_type = widget.config_type.value
        if config_wrappers is None or config_type not in config_wrappers:
            show_error_dialog("No configuration loaded to save.")
            return
        full_config = config_wrappers[config_type].unflatten()
        save_as_default_config(full_config, config_type=config_type)
        widget.set_status_message("✅ New default configuration saved!")

    save_button.clicked.connect(on_save_clicked)

    button_row.addWidget(save_button)
    widget.native.layout().insertLayout(3, button_row)


set_up_load_config_widget(load_config)


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
def _apply_editor_values(config_type: str):
    """
    Commit pending values for one configuration type.

    Parameters
    ----------
    config_type : str
        The module (usually topostats) whose pending config edits are applied.
    """
    config_wrappers[config_type].flat.update(updated_values.pop(config_type, {}))
    save_current_config_as_temp(config_type=config_type)


class ConfigEditorWidget(QWidget):
    """
    Reusable dock content for editing one configuration type at a time.

    Parameters
    ----------
    config_type : str
        The module (usually topostats) whose config is edited.
    """

    def __init__(self, config_type: str):
        """
        Initialises ConfigEditorWidget.

        Parameters
        ----------
        config_type : str
            The module (usually topostats) whose config is edited.
        """
        super().__init__()
        self.config_type = config_type
        self.setMinimumWidth(550)
        self.main_layout = QVBoxLayout(self)
        self.form = None
        self._build_form(config_type)
        button_row = QHBoxLayout()
        save_button = QPushButton("Save to File")
        default_button = QPushButton("Set as Default")
        apply_button = QPushButton("Apply")
        for button in (save_button, default_button, apply_button):
            button_row.addWidget(button)
        self.main_layout.addLayout(button_row)
        attach_status_label(self)
        save_button.clicked.connect(self.save_to_file)
        default_button.clicked.connect(self.set_as_default)
        apply_button.clicked.connect(self.apply)

    def _build_form(self, config_type: str):
        """
        Build the editor form for a configuration type.

        Parameters
        ----------
        config_type : str
            The module (usually topostats) whose config form is built.
        """
        if self.form is not None:
            self.main_layout.removeWidget(self.form)
            self.form.deleteLater()
        self.config_type = config_type
        updated_values.pop(config_type, None)
        self.form = build_dynamic_widget(
            get_current_config(config_type=config_type),
            comment_descriptions.get(config_type, {}),
            config_type=config_type,
        )
        self.form.setFrameShape(QFrame.NoFrame)
        self.form.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.main_layout.insertWidget(0, self.form)

    def show_config(self, config_type: str):
        """
        Display a configuration type in the editor.

        Parameters
        ----------
        config_type : str
            The module (usually topostats) whose config is displayed.
        """
        if config_type != self.config_type:
            updated_values.pop(self.config_type, None)
            self._build_form(config_type)

    def apply(self):
        """Apply the edited values to the current configuration."""
        _apply_editor_values(self.config_type)
        self.set_status_message("✅ Configuration applied successfully.")

    def save_to_file(self):
        """Save the edited configuration to a selected file."""
        self.apply()
        file_path, _ = QFileDialog.getSaveFileName(
            parent=self, caption="Save Configuration As", filter="YAML Files (*.yaml *.yml);;JSON Files (*.json)"
        )
        if not file_path:
            self.set_status_message("Configuration save cancelled.")
            return
        save_config_to_file(Path(file_path), get_current_config(self.config_type), self.config_type)
        self.set_status_message("✅ Configuration saved to file.")

    def set_as_default(self):
        """Save the edited configuration as the user default."""
        self.apply()
        save_as_default_config(get_current_config(self.config_type), self.config_type)
        self.set_status_message("✅ Default configuration saved.")


def open_config_editor(viewer: Viewer, main_widget: QWidget, config_type: str = "topostats"):
    """
    Open or raise the reusable native napari configuration editor dock.

    Parameters
    ----------
    viewer : Viewer
        The current napari viewer
    main_widget : QWidget
        Plugin main widget (TopoStatsWidget) used to display status messages and tabify the dock.
    config_type : str
        The module (usually topostats) whose config is opened in the editor.
    """
    if config_type not in config_wrappers:
        main_widget.bottom_widget.set_status_message(f"Could not edit {config_type}: no configuration is loaded.")
        return
    manager = get_widget_manager()
    manager.ensure_valid("Edit Configuration")
    config_editor_widget = manager.get_widget("Edit Configuration", raw=True)
    config_editor_dock = manager.get_widget("Edit Configuration")
    if config_editor_widget is None:
        config_editor_widget = ConfigEditorWidget(config_type)
        config_editor_dock = manager.add_docked_widget(config_editor_widget, area="right", name="Edit Configuration")
    else:
        config_editor_widget.show_config(config_type)
    main_dock = main_widget.parentWidget()
    while main_dock is not None and not hasattr(main_dock, "toggleViewAction"):
        main_dock = main_dock.parentWidget()
    if main_dock is not None:
        viewer.window._qt_window.tabifyDockWidget(main_dock, config_editor_dock)  # pylint: disable=protected-access
    config_editor_dock.show()
    config_editor_dock.raise_()


def save_config_to_file(file_path: Path, full_config: dict[str, Any], config_type: str = "topostats"):
    """
    Saves the config to a file with comments preserved, displaying an error message if it fails.

    Parameters
    ----------
    file_path : Path
        The path to save the file to.
    full_config : dict[str, Any]
        The config to save.
    config_type : str
        The module (usually topostats) whose config is saved to the file.
    """
    try:
        if file_path.suffix.lower() == ".json":
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(full_config, f, indent=2)
        else:
            # For YAML files, use write_config_with_comments if we have comment descriptions
            config_comment_descriptions = comment_descriptions.get(config_type, {})
            if config_comment_descriptions:
                # Build the comments dict in the format expected by write_config_with_comments
                # It expects nested dict structure matching the config
                comments_nested = _unflatten_comments(config_comment_descriptions)

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


def _write_yaml_with_inline_comments(file_path: Path, config: dict[str, Any], comments: dict[str, Any]):
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
        """
        Format a value as YAML inline style

        Parameters
        ----------
        value : Any
            Value to serialise in YAML flow style.

        Returns
        -------
        str
            YAML representation of the value.
        """
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

    def write_dict(current_dictionary: dict, comment_dict: dict, indent: int = 0):
        """
        Recursively write dictionary with comments

        Parameters
        ----------
        current_dictionary : dict
            Dictionary at the current nesting level.
        comment_dict : dict
            Comments associated with the current dictionary level.
        indent : int
            Current YAML indentation depth.
        """
        indent_str = "  " * indent

        for key, val in current_dictionary.items():
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


def save_current_config_as_temp(overides: dict[str, Any] | None = None, config_type: str = "topostats"):
    """
    Saves the current config as a temporary file with optional overides.
    This is used for maintaining an up to date config file and path for TopoStats backend functions.

    Parameters
    ----------
    overides : dict[str, Any] | None
        A dictionary of config keys and values to override in the saved config.
    config_type : str
        The module (usually topostats) whose config is saved temporarily.
    """
    full_current_config = get_current_config(config_type=config_type)

    if overides:
        for key, value in overides.items():
            config_wrappers[config_type].flat[key] = value
    config_dir = Path(user_config_dir("TopoStats", "Napari"))
    config_path = config_dir / f"_temp_{config_type}_config.yaml"
    config_dir.mkdir(parents=True, exist_ok=True)
    save_config_to_file(config_path, full_current_config, config_type=config_type)
    current_config_paths[config_type] = str(config_path)


def get_current_config(flat: bool = False, config_type: str = "topostats") -> dict[str, Any]:
    """
    Returns the current config with any updates from the edit config window applied

    Parameters
    ----------
    flat : bool
        Whether to return dotted keys instead of the nested configuration.
    config_type : str
        The module (usually topostats) whose current config is returned.

    Returns
    -------
    dict[str, Any]
        Current configuration, in flat or nested form as requested.
    """
    if flat:
        return config_wrappers[config_type].flat
    full_current_config = config_wrappers[config_type].unflatten()
    return full_current_config


def config_loaded(config_type: str = "topostats") -> bool:
    """
    Returns True if a config has been loaded, False otherwise.

    Returns
    -------
    bool
        True if a config has been loaded, False otherwise.

    Parameters
    ----------
    config_type : str
        The module (usually topostats) whose config loaded state is checked.
    """
    return config_type in config_wrappers


def add_values_to_dict_from_config(
    config: dict[str, Any],
    wrapper: ConfigWrapper,
    function_key: str,
    args: dict[str, Any],
    params: list[Any],
) -> dict[str, Any]:
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


def save_scripts(selected_scripts: list[str]) -> set[str]:
    """
    Saves selected scripts to the TopoStats configuration directory.

    Parameters
    ----------
    selected_scripts : list of str
        Names of the scripts/functions to save.

    Returns
    -------
    set of str
        The names of the files that were successfully saved.
    """
    save_dir = Path(user_config_dir("TopoStats", "Napari")) / "scripts"
    save_dir.mkdir(parents=True, exist_ok=True)

    metadata_path = save_dir / "saved_scripts.json"

    if metadata_path.exists():
        with open(metadata_path, encoding="utf-8") as f:
            metadata = json.load(f)
    else:
        metadata = {}

    saved_files = set()

    for name in selected_scripts:
        file_path_str = get_loaded_function_path(name)
        if file_path_str:
            file_path = Path(file_path_str)
            if file_path.exists() and file_path.suffix == ".py":
                dest_path = save_dir / file_path.name
                if file_path.resolve() != dest_path.resolve():
                    shutil.copy(file_path, dest_path)
                saved_files.add(file_path.name)

                # Update metadata mapping filename to selected functions
                if file_path.name not in metadata:
                    metadata[file_path.name] = []
                if name not in metadata[file_path.name]:
                    metadata[file_path.name].append(name)

    # Write metadata back
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=4)

    return saved_files


def unsave_scripts(selected_scripts: list[str]) -> set[str]:
    """
    Unsaves selected scripts from the TopoStats configuration directory.

    Parameters
    ----------
    selected_scripts : list of str
        Names of the scripts/functions to unsave.

    Returns
    -------
    set of str
        The names of the files that were successfully unsaved.
    """
    save_dir = Path(user_config_dir("TopoStats", "Napari")) / "scripts"
    metadata_path = save_dir / "saved_scripts.json"

    if not metadata_path.exists():
        return set()

    with open(metadata_path, encoding="utf-8") as f:
        metadata = json.load(f)

    unsaved_files = set()

    for name in selected_scripts:
        file_path_str = get_loaded_function_path(name)
        if file_path_str:
            file_path = Path(file_path_str)
            if (
                file_path.exists()
                and file_path.suffix == ".py"
                and file_path.name in metadata
                and name in metadata[file_path.name]
            ):
                # Update metadata
                metadata[file_path.name].remove(name)

    for file_path, file_list in metadata.items():
        file_path = save_dir / file_path
        if not file_list and file_path.exists():
            file_path.unlink()
            unsaved_files.add(file_path)
    for file_path in unsaved_files:
        if file_path.name in metadata:
            del metadata[file_path.name]
    unsaved_files = {f.name for f in unsaved_files}

    # Write updated metadata back
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=4)

    return unsaved_files


def fetch_saved_scripts() -> dict[str, list[str]]:
    """
    Fetches the metadata of saved scripts.

    Returns
    -------
    dict
        Metadata mapping filenames to lists of selected function names.
    """
    save_dir = Path(user_config_dir("TopoStats", "Napari")) / "scripts"
    metadata_path = save_dir / "saved_scripts.json"

    if not metadata_path.exists():
        return {}

    with open(metadata_path, encoding="utf-8") as f:
        metadata = json.load(f)

    return metadata
