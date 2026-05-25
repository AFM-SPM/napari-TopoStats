"""Module to handle loading and displaying the user guide for the plugin."""

import json
from importlib.metadata import version
from pathlib import Path

import markdown
from platformdirs import user_config_dir
from qtpy.QtCore import QUrl
from qtpy.QtWidgets import QDialog, QTextBrowser, QVBoxLayout

# Keep a reference to the dialog to prevent garbage collection and keep it non-modal
_guide_dialog = None


def get_readme_path():
    """
    Get the path to the README.md file.

    Returns
    -------
    Path
        The path to the README.md file.

    Raises
    ------
    FileNotFoundError
        If README.md cannot be found.
    """
    dev_path = Path(__file__).resolve().parent.parent.parent / "README.md"
    if dev_path.exists():
        return dev_path

    raise FileNotFoundError("README.md could not be found.")


def load_guide():
    """
    Load the README.md markdown file and convert it to HTML.

    Returns
    -------
    tuple[str, Path]
        A tuple containing the converted HTML string and the parent directory Path of the README.md.
    """
    readme_path = get_readme_path()
    with open(readme_path, encoding="utf-8") as f:
        text = f.read()

    # Convert markdown to HTML with powerful extensions
    html_content = markdown.markdown(text, extensions=["extra", "codehilite", "tables"])

    return html_content, readme_path.parent


def show_guide(viewer):
    """
    Show the guide to the user in a non-modal QDialog.

    Parameters
    ----------
    viewer : napari.Viewer
        The napari viewer instance.
    """
    global _guide_dialog  # pylint: disable=global-statement

    # If the dialog is already open and visible, bring it to the front
    if _guide_dialog is not None and _guide_dialog.isVisible():
        _guide_dialog.raise_()
        _guide_dialog.activateWindow()
        return

    try:
        html_content, readme_dir = load_guide()
    except FileNotFoundError:
        return

    # Use the main napari window as the parent if available
    parent_widget = None
    if hasattr(viewer, "window") and hasattr(viewer.window, "_qt_window"):
        parent_widget = viewer.window._qt_window  # pylint: disable=protected-access

    _guide_dialog = QDialog(parent_widget)
    _guide_dialog.setWindowTitle("TopoStats Guide")
    _guide_dialog.resize(810, 600)

    layout = QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)

    text_browser = QTextBrowser()
    text_browser.setOpenExternalLinks(True)

    # Provide the base directory so relative image paths (e.g. readme_images/) are resolved
    base_url = QUrl.fromLocalFile(str(readme_dir) + "/")
    text_browser.document().setBaseUrl(base_url)
    text_browser.setSearchPaths([str(readme_dir)])
    text_browser.setHtml(html_content)

    layout.addWidget(text_browser)
    _guide_dialog.setLayout(layout)
    _guide_dialog.show()


def check_guide(viewer):
    """
    Check the installed plugin version and show the guide if it is the first launch or a new version.

    Parameters
    ----------
    viewer : napari.Viewer
        The napari viewer instance.
    """
    user_settings_path = Path(user_config_dir("TopoStats", "Napari")) / "settings.json"
    if not user_settings_path.exists():
        settings = {"plugin-version": version("napari-topostats")}
        with open(user_settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f)
        show_guide(viewer)
    else:
        with open(user_settings_path, encoding="utf-8") as f:
            settings = json.load(f)

        if settings.get("plugin-version") != version("napari-topostats"):
            settings["plugin-version"] = version("napari-topostats")
            with open(user_settings_path, "w", encoding="utf-8") as f:
                json.dump(settings, f)

            show_guide(viewer)
