"""Contains functions surrounding utilities and cosmetics."""

import copy

import numpy as np
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
    stats = GrainStats(
        image.metadata["grains"].image_grain_crops.above.crops,
        direction="above",
        base_output_dir="grains",
        **cfg,
    )
    df = stats.calculate_stats()[0]
    # Get scaling factors from metadata

    pixel_to_nm_scaling = image.metadata.get("px2nm", 1.0)
    metre_scaling_factor = image.metadata.get("metre_scaling_factor", 1e-9)
    length_scaling_factor = pixel_to_nm_scaling * metre_scaling_factor

    # Convert centre coordinates back to pixels if they exist
    if "centre_x" in df.columns and "centre_y" in df.columns:
        df["centre_x_px"] = df["centre_x"] / length_scaling_factor
        df["centre_y_px"] = df["centre_y"] / length_scaling_factor

        return (df, "centre_y_px", "centre_x_px")

    return (df, "centre_x", "centre_y")
