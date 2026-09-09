from typing import Any

from napari import Viewer
import numpy as np
import pandas as pd
from napari.layers import Labels
from napari.layers.labels._labels_constants import Mode
from qtpy.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from napari_topostats._alerts import attach_status_label


def render_label_matched_table(
    viewer: Viewer,
    base_layer: Labels,
    data_frame: pd.DataFrame,
    table_group: str,
    container: QWidget,
):
    """
    Render a table widget for the given dataframe and link it with the napari viewer.

    viewer : Viewer
        Napari viewer instance.
    base_layer : Labels
        The source labels layer
    data_frame : pd.DataFrame
        Dataframe containing the grain measurements.
    table_group : str
        Identifier for the table group.
    container : QWidget
        The container widget for the table.
    """
    layout = QVBoxLayout(container)
    nm_checkbox = QCheckBox("Convert to nm")
    nm_checkbox.setChecked(False)

    # Create table widget
    table = QTableWidget()
    table.setRowCount(len(data_frame))
    table.setColumnCount(len(data_frame.columns))
    table.setHorizontalHeaderLabels(data_frame.columns.tolist())

    if isinstance(base_layer, Labels):
        # Create a copy of the dataframe with an extra row for the background for proper alignmemt of labels
        # This will not affect the original dataframe used for the table
        features_df = data_frame.copy()
        features_df.index = features_df.index + 1
        if 0 not in features_df.index:
            # Get the first row to copy the columns and dtypes
            bg_row = features_df.iloc[[0]].copy()
            bg_row.index = [0]
            # Fill the row with NaN
            bg_row.loc[0] = np.nan
            if "grain_number" in bg_row.columns:
                # Set grain_number to -1 for the background row so it is different from real grains (0-indexed)
                bg_row["grain_number"] = -1
            features_df = pd.concat([bg_row, features_df])
        features_df["label_id"] = features_df.index
        # Add the table data to the features of the labels layer so that data can also be viewed in the bottom bar
        base_layer.features = features_df

    # Set the labels layer to PICK mode to allow selecting individual grains (by clicking)
    base_layer.mode = Mode.PICK

    # Selecting a row in the table will update the labels layer and vice versa. Updating the selection programmatically
    # also triggers the update callback, so we use a flag to prevent recursive, infinite updates.
    is_updating = False

    def convert_to_nm(df_m: pd.DataFrame) -> pd.DataFrame:
        """
        Convert the pd.DataFrame from m to nm.

        We assume that units are in metres, and that very small values are in metres. Smaller values are
        assumed to be areas or volumes.

        Parameters
        ----------
        df_m : pd.DataFrame
            Grain measurements expressed in metre-based units.

        Returns
        -------
        pd.DataFrame
            Copy of the measurements converted to nanometre-based units.
        """
        # The original dataframe is maintained, and a copy is used for conversion to nanometres.
        df_nm = df_m.copy()
        m_to_nm = 1e9
        for col in df_nm.select_dtypes(include=[np.number]).columns:
            if df_nm[col].max() == 0:
                continue
            if df_nm[col].max() < 1e-23:  # Volume in m^3
                df_nm[col] = df_nm[col] * (m_to_nm**3)
            elif df_nm[col].max() < 1e-14:  # Area in m^2
                df_nm[col] = df_nm[col] * (m_to_nm**2)
            elif df_nm[col].max() < 1e-5:  # Length in m
                df_nm[col] = df_nm[col] * m_to_nm
        return df_nm

    def on_checkbox_changed(checked: bool):
        """
        Switch the displayed table values between metres and nanometres.

        Parameters
        ----------
        checked : bool
            Whether nanometre-based values should be displayed.
        """
        # Convert table from m to nm
        if checked:
            df_nm = convert_to_nm(data_frame)

            # Update table
            for i in range(len(df_nm)):
                for j in range(df_nm.shape[1]):
                    item = QTableWidgetItem(str(df_nm.iat[i, j]))
                    table.setItem(i, j, item)
        else:
            df_m = data_frame.copy()
            # Update table
            for i in range(len(df_m)):
                for j in range(df_m.shape[1]):
                    item = QTableWidgetItem(str(df_m.iat[i, j]))
                    table.setItem(i, j, item)

    # pylint: disable=unused-argument
    def on_row_clicked(row: int, column: int):
        """
        Triggered when a table row is clicked to also select that label in the viewer.

        Parameters
        ----------
        row : int
            Table row containing the selected grain.
        column : int
            Clicked table column; selection is applied to the entire row.
        """
        nonlocal is_updating
        # Get the grain number (or label id) from the dataframe
        grain_id = data_frame.iloc[row]["grain_number"]

        # Find coordinates of that label in the image
        mask = base_layer.data == int(grain_id) + 1
        if mask.any() and isinstance(base_layer, Labels):
            coords = np.argwhere(mask)
            if coords.size > 0:
                centroid = coords.mean(axis=0)
                # Ensure we're only using (y, x) order for 2D
                y, x = centroid[-2], centroid[-1]
                # Set the camera center in world coordinates
                viewer.scene.camera.center = (y, x)
            base_layer.show_selected_label = True
            base_layer.selected_label = int(grain_id) + 1
            base_layer.mode = Mode.PICK
            viewer.layers.selection.active = base_layer
            is_updating = True

    # pylint: disable=unused-argument
    def on_label_selected(event: Any):
        """
        Select the table row corresponding to the picked label.

        Parameters
        ----------
        event : Any
            Napari label-selection event.
        """
        nonlocal is_updating
        # If the update is triggered programmatically, we skip to avoid recursion, and set the flag to False so the
        # next update can proceed as normal
        if is_updating:
            is_updating = False
            return
        selected = base_layer.selected_label
        if selected == 0:  # 0 means background
            base_layer.show_selected_label = False
            return

        # Find matching row
        match = data_frame.index[data_frame["grain_number"] + 1 == selected]
        if len(match):
            row = int(match[0])
            table.selectRow(row)
            table.scrollToItem(table.item(row, 0), QTableWidget.PositionAtCenter)
            base_layer.show_selected_label = True

    nm_checkbox.toggled.connect(on_checkbox_changed)
    nm_checkbox.setObjectName("nm_checkbox")
    layout.addWidget(nm_checkbox)
    base_layer.events.selected_label.connect(on_label_selected)

    # Populate table with the dataframe
    for i in range(len(data_frame)):
        for j in range(data_frame.shape[1]):
            item = QTableWidgetItem(str(data_frame.iat[i, j]))
            table.setItem(i, j, item)

    layout.addWidget(table)

    save_button = QPushButton("Save to CSV")
    layout.addWidget(save_button)
    attach_status_label(container) 

    def save_to_csv():
        """Prompt for a path and export the displayed grain statistics as CSV."""
        # Open a file dialog to choose where to save
        file_path, _ = QFileDialog.getSaveFileName(
            table,
            "Save Table as CSV",
            f"{base_layer.name.lower().replace(' ', '_')}_stats.csv",
            "CSV Files (*.csv)",
        )
        # If the user selected a file path, save the dataframe to CSV
        if file_path:
            # Save the currently viewed version which may be converted to nm based on the checkbox state
            df_to_save = convert_to_nm(data_frame) if nm_checkbox.isChecked() else data_frame
            df_to_save.to_csv(file_path, index=False)
            container.set_status_message(f"Saved CSV to: {file_path}")
        else:
            container.set_status_message("Save CSV cancelled.")

    save_button.clicked.connect(save_to_csv)
    table.cellClicked.connect(on_row_clicked)

    # Keep tables for different source layers as tabs
    table_name = f"{table_group.title()}: {base_layer.name}"

    return table_name, table_group
