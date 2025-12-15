"""Provides a worker thread for parallel processing of intensive functions."""

from PyQt5.QtCore import QThread, pyqtSignal


class ProcessWorker(QThread):
    """
    Worker thread for processing an intensive function in parallel.
    """

    result_ready = pyqtSignal(object)

    def __init__(self, func, *args, **kwargs):
        """
        Generate a worker to process the batch in a separate thread.
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
        Run the batch processing.
        """
        self.result = self.func(*self.args, **self.kwargs)

        self.result_ready.emit(self.result)
