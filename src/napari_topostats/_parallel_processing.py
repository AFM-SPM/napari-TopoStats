"""Provides a worker thread for parallel processing of intensive functions."""

from collections.abc import Callable
from typing import Any

from qtpy.QtCore import QThread, Signal


class ProcessWorker(QThread):
    """
    Worker thread for processing an intensive function in parallel.

    Parameters
    ----------
    func : Callable[..., Any]
        Function to run in the worker thread.
    *args : Any
        Positional arguments passed to the function.
    **kwargs : Any
        Keyword arguments passed to the function.
    """

    result_ready = Signal(object)
    error_signal = Signal(Exception)

    def __init__(self, func: Callable[..., Any], *args: Any, **kwargs: Any):
        """
        Generate a worker to run function in a separate thread.

        Parameters
        ----------
        func : Callable[..., Any]
            Function to run in the worker thread.
        *args : Any
            Positional arguments passed to the function.
        **kwargs : Any
            Keyword arguments passed to the function.
        """
        super().__init__()
        self.args = args
        self.kwargs = kwargs
        self.func = func
        self.result = None

    def set_parameters(self, *args: Any, **kwargs: Any):
        """
        Set the parameters for the function to be executed.

        Parameters
        ----------
        *args : Any
            Signal arguments forwarded by the worker callback.
        **kwargs : Any
            Additional keyword arguments.
        """
        self.args = args
        self.kwargs = kwargs

    def run(self):
        """Run the function."""
        try:
            self.result = self.func(*self.args, **self.kwargs)
            self.result_ready.emit(self.result)
        except Exception as e:  # noqa: BLE001 -- forward worker failures to the GUI thread
            self.error_signal.emit(e)
