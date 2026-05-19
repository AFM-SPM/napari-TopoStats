"""
Batch processing functionality for napari-TopoStats.
This module provides a function for batch processing multiple AFM images in a selected folder using the current
configuration. The batch processing is performed in a separate thread to keep the GUI responsive, and progress
is communicated through status messages and command line output.
"""

import argparse
from pathlib import Path

from magicgui import magicgui
from napari import current_viewer  # pylint: disable=no-name-in-module
from qtpy.QtWidgets import QFileDialog
from topostats.run_modules import process

from ._alerts import attach_status_label, show_error_dialog
from ._io import config_loaded, get_current_config, get_current_config_path, load_config_impl
from ._parallel_processing import ProcessWorker


# pylint: disable=protected-access
@magicgui(
    data_path={"label": "Input path", "mode": "d"},
    output_path={"label": "Output path", "mode": "d"},
    call_button="Batch Process",
)
def batch_process(
    data_path: Path = None,
    output_path: Path = None,
):
    """
    Batch process multiple AFM images in a selected folder using the current configuration.
    Parameters
    ----------
    data_path : Path | None
        The input data directory containing AFM images to process. If None, a dialog will prompt for selection.
    output_path : Path | None
        The output directory where results will be saved. If None, a dialog will prompt for selection.
    """
    widget = batch_process
    if not hasattr(widget, "set_status_message"):
        attach_status_label(widget)

    if not config_loaded():
        load_config_impl(current_viewer(), use_default=True)

    if get_current_config()["base_dir"] == "./":
        if data_path is None:
            data_path = QFileDialog.getExistingDirectory(
                parent=None,
                caption="Select Input Data Directory",
            )
            data_path = Path(data_path)
            widget.data_path.value = data_path

        if output_path is None:
            output_path = QFileDialog.getExistingDirectory(
                parent=None,
                caption="Select Output Data Directory",
            )
            output_path = Path(output_path)
            widget.output_path.value = output_path
    # ruff: noqa: SIM102
    if hasattr(widget, "_batch_worker"):
        try:
            if widget._batch_worker.isRunning():
                widget.set_status_message("⚠️ Batch processing is already running.")
                return
        except RuntimeError:
            # Worker thread has been deleted and is therefore not running
            pass
    args = argparse.Namespace(
        config_file=str(get_current_config_path()),
        module="topostats",
        summary_config=None,
    )
    if data_path is not None:
        args.base_dir = str(data_path)
    else:
        widget.data_path.value = get_current_config()["base_dir"]
    if output_path is not None:
        args.output_dir = str(output_path)
    else:
        widget.output_path.value = get_current_config()["output_dir"]

    widget.set_status_message("⏳ Starting batch processing in the background. View command line for progress.")
    worker = ProcessWorker(process, args)
    worker.finished.connect(lambda: widget.set_status_message("✅ Batch processing complete."))
    worker.finished.connect(worker.deleteLater)
    worker.error_signal.connect(handle_batch_process_error)
    widget._batch_worker = worker  # prevent garbage collection
    worker.start()


def handle_batch_process_error(e: Exception):
    """
    Handle errors that occur during batch processing.

    Parameters
    ----------
    e : Exception
        The exception that was raised during batch processing.
    """
    widget = batch_process
    if hasattr(widget, "set_status_message"):
        widget.set_status_message(f"❌ Error during batch processing: {str(e)}")
    show_error_dialog(f"Error during batch processing: {str(e)}", raise_exception=True)
