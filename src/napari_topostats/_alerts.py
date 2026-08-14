"""Module used for providing error alerts in the gui and show/ handle loading messages"""

from magicgui.widgets import FunctionGui
from qtpy.QtCore import QTimer, Qt
from qtpy.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import napari_topostats._state as state
from napari_topostats._state import is_valid_widget
from napari_topostats._styles import (
    ERROR_DIALOG_BUTTON_STYLE,
    ERROR_DIALOG_LABEL_STYLE,
    ERROR_DIALOG_STYLE,
    LOADING_CONTAINER_STYLE,
    LOADING_LABEL_STYLE,
    LOADING_OVERLAY_STYLE,
    STATUS_LABEL_HIDDEN_STYLE,
    STATUS_LABEL_STYLE,
    STATUS_LABEL_VISIBLE_STYLE,
)

NAPARI_TOPOSTATS_REPORT = "https://github.com/AFM-SPM/napari-TopoStats/issues/new?template=bug_report.yaml"


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
        self.setMinimumWidth(300)

        # Main layout
        layout = QVBoxLayout()
        layout.setSpacing(10)

        # Error message text itself
        self.label = QLabel(message)
        self.label.setWordWrap(True)
        self.label.setStyleSheet(ERROR_DIALOG_LABEL_STYLE)
        layout.addWidget(self.label)

        # OK button
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        ok_button = QPushButton("OK")
        ok_button.setMinimumWidth(80)
        ok_button.setStyleSheet(ERROR_DIALOG_BUTTON_STYLE)
        ok_button.clicked.connect(self.accept)
        button_layout.addWidget(ok_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)
        self.setModal(True)

        # Dialog styling
        self.setStyleSheet(ERROR_DIALOG_STYLE)


def show_error_dialog(
    message: str = "",
    raise_exception: bool = False,
    topostats_error: bool = False,
    exception: Exception | None = None,
):
    """
    Show an error dialog with the given message. Optionally raise an exception.

    Parameters
    ----------
    message : str
        The error message to display.
    raise_exception : bool, optional
        If True, raise a ValueError after showing the dialog. Used for errors that should halt execution.
    """
    if topostats_error:
        message += (
            f"\nThis error is potentially caused in the TopoStats package rather than in the Napari "
            f"front-end you are using.\nPlease report your issue at {NAPARI_TOPOSTATS_REPORT}."
        )

    if not raise_exception or exception:
        print(f"Error: {message}")

    # Close any existing error dialog before showing a new one
    if state.current_error_dialog is not None:
        state.current_error_dialog.close()

    # Create and show new error dialog
    state.current_error_dialog = ErrorDialog(message)
    state.current_error_dialog.show()

    # Ensure the dialog is shown immediately
    QApplication.processEvents()

    # If raise_exception is True, raise a ValueError
    if raise_exception:
        if exception is not None:
            raise exception
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


def attach_status_label(widget: FunctionGui | QWidget):
    """
    Add status label to passed in widget, which can be updated when then function associated with that widget runs.
    """

    label = QLabel("")
    label.setStyleSheet(STATUS_LABEL_STYLE)
    label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    label.setMinimumWidth(0)
    label.setMaximumWidth(300)  # Prevent excessive width
    label.setWordWrap(True)

    if isinstance(widget, FunctionGui):
        widget.native.layout().addWidget(label)
    else:
        widget.layout().addWidget(label)

    widget.status_label = label  # Store label as widget property
    label_timer = QTimer()
    label_timer.setSingleShot(True)

    def remove_label():
        if is_valid_widget(widget):
            label.setText("")
            label.adjustSize()
            # Force the parent widget to recalculate its size
            to_adjust = widget.native if hasattr(widget, "native") else widget
            to_adjust.adjustSize()
            to_adjust.updateGeometry()
            if to_adjust.parent():
                to_adjust.parent().adjustSize()
                to_adjust.parent().updateGeometry()
            label.setStyleSheet(STATUS_LABEL_HIDDEN_STYLE)

    label_timer.timeout.connect(remove_label)
    widget.label_timer = label_timer

    def set_status_message(message: str):
        label.setText(message)
        label.setStyleSheet(STATUS_LABEL_VISIBLE_STYLE)
        label.adjustSize()
        to_adjust = widget.native if hasattr(widget, "native") else widget
        to_adjust.updateGeometry()
        label_timer.stop()
        label_timer.start(3000)  # Clear message after 3 seconds

    widget.set_status_message = set_status_message


class LoadingWidget(QWidget):
    """A semi-transparent overlay for napari viewer."""

    def __init__(self, viewer):
        """
        Initialize the loading widget and attach it to the napari viewer.

        Parameters
        ----------
        viewer : napari.Viewer
            The napari viewer to attach the loading widget to.
        """
        # Parent to the main napari window so it covers everything
        super().__init__(viewer.window._qt_window)
        self.viewer = viewer

        # Make overlay semi-transparent
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setStyleSheet(LOADING_OVERLAY_STYLE)

        # Center layout
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)

        # Create container with rounded background
        loading_container = QWidget()
        loading_container.setStyleSheet(LOADING_CONTAINER_STYLE)

        loading_layout = QVBoxLayout()
        loading_layout.setAlignment(Qt.AlignCenter)

        self.loading_label = QLabel()
        self.loading_label.setStyleSheet(LOADING_LABEL_STYLE)
        self.loading_label.setAlignment(Qt.AlignCenter)

        loading_layout.addWidget(self.loading_label)
        loading_container.setLayout(loading_layout)

        layout.addWidget(loading_container)
        self.setLayout(layout)

        self.message = ""

        self.hide()

    def start(self, message="Loading"):
        """Show the dialog with a message."""
        self.message = message
        self.loading_label.setText(f"{self.message}")

        # Cover the entire napari window
        self.setGeometry(self.parent().rect())

        self.show()
        self.raise_()  # Bring to front
        QApplication.processEvents()

    def stop(self):
        """Hide the widget."""
        self.hide()
        QApplication.processEvents()

    def resizeEvent(self, event):
        """Keep overlay covering the parent when window resizes."""
        if self.parent():
            self.setGeometry(self.parent().rect())
        super().resizeEvent(event)


def construct_error_args(
    exception: Exception = None,
    message: str = None,
    raise_exception: bool = False,
    topostats_error: bool = False,
    type_class=None,
) -> dict:
    """
    Construct a dictionary of error arguments.

    Parameters
    ----------
    e : Exception, optional
        The exception that was caught (default is None).
    message : str, optional
        A custom error message to display (default is None). If None, a message will be constructed from the exception.
    raise_exception : bool, optional
        Whether to raise the exception after constructing the error arguments (default is False).
    topostats_error : bool, optional
        Whether the error is specific to Topostats (default is False).
    type_class : type, optional
        The class type associated with the error (default is None).

    Returns
    -------
    dict
        A dictionary containing the error arguments.
    """
    error_args = {}
    if message is not None:
        error_args["message"] = message
    else:
        if topostats_error:
            if type_class:
                error_args["message"] = (
                    f"Topostats is failing with {type_class.__name__}: {exception.__class__} {exception}."
                )
            else:
                error_args["message"] = f"Topostats is failing with: {exception.__class__} {exception}."
        else:
            error_args["message"] = f"An error occurred: {exception.__class__} {exception}."
    error_args["raise_exception"] = raise_exception
    error_args["topostats_error"] = topostats_error
    error_args["exception"] = exception
    return error_args
