# ruff: noqa: BLE001
# pylint: disable=broad-exception-caught
"""Provides a worker thread for parallel processing of intensive functions."""

from qtpy.QtCore import QThread, Signal


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
