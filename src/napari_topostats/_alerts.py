from qtpy.QtWidgets import QApplication, QDialog, QLabel, QVBoxLayout

from . import _state as state


class ErrorDialog(QDialog):
    """
    A simple dialog window to display error messages.
    """

    def __init__(self, message: str):
        """
        Initialize the error dialog with the provided message.

        Parameters
        ----------
        message : str
            The error message to display in the dialog.
        """
        super().__init__()
        self.setWindowTitle("Error")
        layout = QVBoxLayout()
        self.label = QLabel(message)
        layout.addWidget(self.label)
        self.setLayout(layout)
        self.setModal(True)


def show_error_dialog(message: str, raise_exception: bool = False):
    """
    Show an error dialog with the given message. Optionally raise an exception.

    Parameters
    ----------
    message : str
        The error message to display.
    raise_exception : bool, optional
        If True, raise a ValueError after showing the dialog. Used for errors that should halt execution.
    """
    global current_error_dialog
    print(f"Error: {message}")
    # Close any existing error dialog before showing a new one
    if state.current_error_dialog is not None:
        state.current_error_dialog.close()
    # Create a new error dialog
    state.current_error_dialog = ErrorDialog(message)
    state.current_error_dialog.show()

    # Ensure the dialog is shown immediately
    QApplication.processEvents()
    # If raise_exception is True, raise a ValueError
    if raise_exception:
        raise ValueError(message)


class LoadingDialog(QDialog):
    """
    A dialog window to indicate a loading or processing state.
    """

    def __init__(self, text="Loading..."):
        """
        Initialize the loading dialog with optional text.

        Parameters
        ----------
        text : str, optional
            The message to display in the loading dialog (default is "Loading...").
        """
        super().__init__()
        self.setWindowTitle("Please wait")
        layout = QVBoxLayout()

        self.label_text = QLabel(text)
        layout.addWidget(self.label_text)

        self.spinner_label = QLabel()
        layout.addWidget(self.spinner_label)

        self.setLayout(layout)
        self.setModal(True)

        self.adjustSize()
