"""Contains functions surrounding utilities and cosmetics."""

import copy

import numpy as np
from topostats.filters import Filters


def afm2stack(
    image: "Napari.types.ImageData",
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

def median_flattened(
    image: "Napari.types.ImageData",
    row_alignment_quantile: float = 0.5
):
    filtered_image = Filters(
        image=image, 
        filename="FILE", 
        pixel_to_nm_scaling=1, 
        row_alignment_quantile=row_alignment_quantile,
        threshold_method="std_dev",
        otsu_threshold_multiplier=1.0,
        threshold_std_dev=1.0,
        threshold_absolute=1.0,
        gaussian_size=1.0121397464510862,
        gaussian_mode="nearest"
        )
    median_flattened = filtered_image.median_flatten(image=image, row_alignment_quantile=row_alignment_quantile)
    #remove_tilt = filtered_image.median_flatten(image=image)
    return median_flattened


