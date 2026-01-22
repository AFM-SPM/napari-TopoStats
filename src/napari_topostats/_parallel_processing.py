# ruff: noqa: BLE001
# pylint: disable=broad-exception-caught
"""Provides a worker thread for parallel processing of intensive functions."""
from qtpy.QtCore import QThread, Signal
from qtpy.QtWidgets import QPushButton


class ProcessWorker(QThread):
    """
    Worker thread for processing an intensive function in parallel.
    """

    result_ready = Signal(object)
    error_signal = Signal(Exception)

    def __init__(self, func, *args, **kwargs):
        """
        Generate a worker to run function in a separate thread.
        """
        super().__init__()
        self.args = args
        self.kwargs = kwargs
        self.func = func
        self.result = None

    def set_parameters(self, *args, **kwargs):
        """
        Set the parameters for the function to be executed.
        """
        self.args = args
        self.kwargs = kwargs

    def run(self):
        """
        Run the function.
        """
        try:
            self.result = self.func(*self.args, **self.kwargs)
            self.result_ready.emit(self.result)
        except Exception as e:
            self.error_signal.emit(e)


def add_interrupt_button(widget, worker, process_name=""):
    """
    Add an interrupt button to the widget to stop the worker thread.

    Parameters
    ----------
    widget : magicgui.widgets.FunctionGui
        The widget to add the interrupt button to.
    worker : ProcessWorker
        The worker thread to be interrupted.
    """

    interrupt_button = QPushButton(f"Interrupt {process_name}")
    interrupt_button.clicked.connect(worker.terminate)
    widget.native.layout().addWidget(interrupt_button)
    widget.interrupt_button = interrupt_button

    def remove_interrupt_button():
        """Remove the interrupt button from the widget."""
        try:
            widget.native.layout().removeWidget(interrupt_button)
            interrupt_button.deleteLater()
        except Exception:
            pass

    worker.finished.connect(remove_interrupt_button)
