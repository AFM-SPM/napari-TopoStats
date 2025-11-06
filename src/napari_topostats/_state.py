"""
State management for napari-TopoStats.
This module contains global state variables used for the representation of the gui across the napari-TopoStats plugin.
"""

docked_widgets = [] # List to keep track of docked widgets
topostats_widget = None # The main TopoStats widget
current_error_dialog = None # To keep track of the currently open error dialog
current_workflows = []  # List to keep track of the workflow steps
original_import_layer = None  # To store the original imported layer for workflow reference
