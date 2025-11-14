"""Module used for providing error alerts in the gui and show/ handle loading messages"""

from magicgui.widgets import FunctionGui
from qtpy.QtCore import QTimer
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

from . import _state as state


class ErrorDialog(QDialog):  # pylint: disable=too-few-public-methods
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

        # Error message
        self.label = QLabel(message)
        self.label.setWordWrap(True)
        self.label.setStyleSheet(
            """
            QLabel {
                font-size: 13px;
                color: #333333;
                padding: 10px;
            }
        """
        )
        layout.addWidget(self.label)

        # OK button
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        ok_button = QPushButton("OK")
        ok_button.setMinimumWidth(80)
        ok_button.setStyleSheet(
            """
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
            QPushButton:pressed {
                background-color: #005a9e;
            }
        """
        )
        ok_button.clicked.connect(self.accept)
        button_layout.addWidget(ok_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)
        self.setModal(True)

        # Dialog styling
        self.setStyleSheet(
            """
            QDialog {
                background-color: white;
            }
        """
        )


def show_error_dialog(
    message: str = "",
    raise_exception: bool = False,
    topostats_error: bool = False,
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
            "\nThis error is potentially caused by an error in TopoStats rather than in this "
            "napari implementation. You can report your issue on the TopoStats GitHub page."
        )

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
        raise ValueError(message)


class LoadingDialog(QDialog):  # pylint: disable=too-few-public-methods
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
    label.setStyleSheet(
        """
        QLabel {
            border: none;
            padding: 0px;
            margin: 0px;
        }
    """
    )
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
        label.setText("")
        label.adjustSize()
        # Force the parent widget to recalculate its size
        to_adjust = widget.native if hasattr(widget, "native") else widget
        to_adjust.adjustSize()
        to_adjust.updateGeometry()
        if to_adjust.parent():
            to_adjust.parent().adjustSize()
            to_adjust.parent().updateGeometry()
            if to_adjust.parent().parent():
                to_adjust.parent().parent().adjustSize()
                to_adjust.parent().parent().updateGeometry()
        label.setStyleSheet(
            """
            QLabel {
                font-size: 4px
            }
        """
        )

    label_timer.timeout.connect(remove_label)
    widget.label_timer = label_timer

    def set_status_message(message: str):
        label.setText(message)
        label.setStyleSheet(
            """
            QLabel {
                font-size: 12px
            }
        """
        )
        label.adjustSize()
        to_adjust = widget.native if hasattr(widget, "native") else widget
        to_adjust.updateGeometry()
        label_timer.stop()
        label_timer.start(3000)  # Clear message after 3 seconds

    widget.set_status_message = set_status_message
