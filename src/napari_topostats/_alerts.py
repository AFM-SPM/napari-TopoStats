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
    """A semi-transparent overlay with a centered spinner for napari viewer."""
    
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
        
        # Create spinner container with rounded background
        spinner_container = QWidget()
        spinner_container.setStyleSheet("""
            QWidget {
                background-color: rgba(40, 40, 40, 240);
                border-radius: 15px;
                padding: 30px;
            }
        """)
        
        spinner_layout = QVBoxLayout()
        spinner_layout.setAlignment(Qt.AlignCenter)
        
        self.spinner_label = QLabel()
        self.spinner_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 18px;
                font-weight: bold;
                background-color: transparent;
            }
        """)
        self.spinner_label.setAlignment(Qt.AlignCenter)
        
        spinner_layout.addWidget(self.spinner_label)
        spinner_container.setLayout(spinner_layout)
        
        layout.addWidget(spinner_container)
        self.setLayout(layout)
        
        # Animation setup
        self.frames = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.current_frame = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_frame)
        self.message = ""
        
        self.hide()
            
    def start(self, message="Loading"):
        """Show the spinner with a message."""
        self.message = message
        self.current_frame = 0
        self._update_frame()
        
        # Cover the entire napari window
        self.setGeometry(self.parent().rect())
        
        self.show()
        self.raise_()  # Bring to front
        self.timer.start(80)  # Update every 80ms
        QApplication.processEvents()
        
    def stop(self):
        """Hide the spinner."""
        self.timer.stop()
        self.hide()
        QApplication.processEvents()
        
    def _update_frame(self):
        """Update the spinner animation frame."""
        spinner = self.frames[self.current_frame]
        self.spinner_label.setText(f"{spinner}  {self.message}  {spinner}")
        self.current_frame = (self.current_frame + 1) % len(self.frames)
        
    def resizeEvent(self, event):
        """Keep overlay covering the parent when window resizes."""
        if self.parent():
            self.setGeometry(self.parent().rect())
        super().resizeEvent(event)