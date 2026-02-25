"""Contains functions surrounding utilities and cosmetics."""

import copy

import numpy as np
import pandas as pd
from napari.layers import Labels
from napari.types import ImageData
from topostats.grainstats import GrainStats


# ------- Misc -------
def afm2stack(
    image: ImageData,
    by_slices: bool = True,
    numslices: int = 255,
    resolution: float = 1.0,
):
    """Turns a 2D AFM image to a 3D stack where the stack is separated
    by either specifying the number of slices, or the resolution of the
    split.

    Parameters
    ----------
    image : Napari.types.ImageData
        The image as an np.ndarray.
    by_slices : bool, optional
        Wether to stack by slices, by default True
    numslices : int, optional
        The number of slices in the stack, by default 255
    resolution : float, optional
        The resolution or distance between each slice, by default 1.0

    Returns
    -------
    np.ndarray
        _description_
    """
    shape = image.shape
    minval, maxval = image.min(), image.max()
    totalrange = maxval - minval
    if not by_slices:
        numslices = int(totalrange / resolution)
    increment = totalrange / numslices
    output = np.empty((numslices, shape[0], shape[1]))
    current_z = minval
    for z in range(numslices):
        dup = copy.deepcopy(image)
        dup[dup >= current_z] = current_z
        dup[dup < current_z] = 0
        output[z, :, :] = dup
        current_z += increment

    return output


def grainstats(image: Labels):
    """Function used for running topostats grainstats function on a labels layer"""
    cfg = image.metadata["config"]["grainstats"]
    cfg.pop("run")
    cfg.pop("class_names")
    topostats_object = image.metadata["topostats_object"]
    stats = GrainStats(
        topostats_object,
        base_output_dir="grains",
        **cfg,
    )
    stats.calculate_stats()
    df = get_grainstats_df(stats)

    # Get scaling factors from metadata

    # Convert centre coordinates back to pixels if they exist
    if "centre_x" in df.columns and "centre_y" in df.columns:
        pixel_to_nm_scaling = image.metadata.get("px2nm", 1.0)
        metre_scaling_factor = image.metadata.get("metre_scaling_factor", 1e-9)
        length_scaling_factor = pixel_to_nm_scaling * metre_scaling_factor
        df["centre_x_px"] = df["centre_x"] / length_scaling_factor
        df["centre_y_px"] = df["centre_y"] / length_scaling_factor

        return df

    return df


def get_grainstats_df(stats) -> pd.DataFrame:
    """
    Reconstructs the 'grainstats' DataFrame from the nested
    grain_crops.stats attributes.
    """
    rows = []

    # 1. Check if grains exist
    if not stats.grain_crops:
        # Return empty DF with expected columns if no grains (optional, mimics old behavior)
        return pd.DataFrame()

    # Iterate through the nested structure
    for grain_index, grain_crop in stats.grain_crops.items():

        # Skip if stats haven't been calculated yet
        if not hasattr(grain_crop, "stats") or not grain_crop.stats:
            continue

        for class_index, subgrains in grain_crop.stats.items():
            for subgrain_index, stats_dict in subgrains.items():

                # Create a copy of the stats to avoid modifying the object
                row = stats_dict.copy()

                # Inject the ID columns
                row["grain_number"] = grain_index
                row["class_number"] = class_index
                row["subgrain_number"] = subgrain_index

                # Handle Image Name
                if hasattr(stats.topostats_object, "filename"):
                    row["image"] = stats.topostats_object.filename
                elif hasattr(stats.topostats_object, "image_name"):
                    row["image"] = stats.topostats_object.image_name
                    print("Using image_name")
                else:
                    row["image"] = "unknown"

                # Handle 'threshold'
                if hasattr(stats.topostats_object, "direction"):
                    row["threshold"] = stats.topostats_object.direction

                rows.append(row)

    # Create DataFrame
    df = pd.DataFrame(rows)
    return df


def calculate_contrast_limits(image: np.ndarray, percentage: float = 2.0) -> tuple[float, float]:
    """
    Calculate contrast limits for an image using the 2nd and 98th percentiles.

    Parameters
    ----------
    image : ImageData
        The input image data.

    Returns
    -------
    tuple[float, float]
        The calculated contrast limits (min, max).
    """
    vmin = np.percentile(image, percentage)
    vmax = np.percentile(image, 100 - percentage)
    return vmin, vmax
