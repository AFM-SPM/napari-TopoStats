from magicgui.widgets import FunctionGui
from qtpy.QtCore import QTimer, Qt
from qtpy.QtGui import QMovie
from qtpy.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

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


def attach_status_label(widget: FunctionGui | QWidget):
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

class LoadingWidget(QWidget):
    """A semi-transparent overlay for napari viewer."""
    
    def __init__(self, viewer):
        # Parent to the main napari window so it covers everything
        super().__init__(viewer.window._qt_window)
        self.viewer = viewer
        
        # Make overlay semi-transparent
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 120);")
        
        # Center layout
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        
        # Create container with rounded background
        loading_container = QWidget()
        loading_container.setStyleSheet("""
            QWidget {
                background-color: rgba(40, 40, 40, 240);
                border-radius: 15px;
                padding: 30px;
            }
        """)
        
        loading_layout = QVBoxLayout()
        loading_layout.setAlignment(Qt.AlignCenter)
        
        self.loading_label = QLabel()
        self.loading_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 18px;
                font-weight: bold;
                background-color: transparent;
            }
        """)
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