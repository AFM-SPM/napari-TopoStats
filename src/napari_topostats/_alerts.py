from qtpy.QtWidgets import QDialog, QLabel, QVBoxLayout, QApplication
from . import _state as state


class ErrorDialog(QDialog):
    def __init__(self, message: str):
        super().__init__()
        self.setWindowTitle("Error")
        layout = QVBoxLayout()
        self.label = QLabel(message)
        layout.addWidget(self.label)
        self.setLayout(layout)
        self.setModal(True)


def show_error_dialog(message: str):
    global current_error_dialog
    print(f"Error: {message}")
    if state.current_error_dialog is not None:
        state.current_error_dialog.close()
    state.current_error_dialog = ErrorDialog(message)
    state.current_error_dialog.show()

    QApplication.processEvents()  # Ensure the dialog is shown immediately

class LoadingDialog(QDialog):
    def __init__(self, text="Loading..."):
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