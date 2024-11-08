"""Contains functions surrounding utilities and cosmetics."""

import copy

import numpy as np
from topostats.filters import Filters
from topostats import scars


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

def remove_scars(
    image: np.ndarray,
    removal_iterations: int = 2,
    threshold_low: float = 0.250,
    threshold_high: float = 0.666,
    max_scar_width: int = 4,
    min_scar_length: int = 16,
):
    return scars.remove_scars(
        img=image,
        filename=None,
        removal_iterations=removal_iterations,
        threshold_low=threshold_low,
        threshold_high=threshold_high,
        max_scar_width=max_scar_width,
        min_scar_length=min_scar_length,
    )

def median_flattened(
    image: "Napari.types.ImageData",
    mask: "Napari.types.LabelsData"=None,
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
    median_flattened = filtered_image.median_flatten(image=image, mask=mask, row_alignment_quantile=row_alignment_quantile)
    return median_flattened

def remove_tilt(
    image: "Napari.types.ImageData",
    mask: "Napari.types.LabelsData"=None,
):
    filtered_image = Filters(
        image=image, 
        filename="FILE", 
        pixel_to_nm_scaling=1, 
        row_alignment_quantile=0.5,
        threshold_method="std_dev",
        otsu_threshold_multiplier=1.0,
        threshold_std_dev=1.0,
        threshold_absolute=1.0,
        gaussian_size=1.0121397464510862,
        gaussian_mode="nearest"
        )
    tilt_removed = filtered_image.remove_tilt(image=image, mask=mask)
    return tilt_removed

def remove_quadratic(
    image: "Napari.types.ImageData",
    mask: "Napari.types.LabelsData"=None,
):
    filtered_image = Filters(
        image=image, 
        filename="FILE", 
        pixel_to_nm_scaling=1, 
        row_alignment_quantile=0.5,
        threshold_method="std_dev",
        otsu_threshold_multiplier=1.0,
        threshold_std_dev=1.0,
        threshold_absolute=1.0,
        gaussian_size=1.0121397464510862,
        gaussian_mode="nearest"
        )
    removed_quadratic = filtered_image.remove_quadratic(image=image, mask=mask)
    return removed_quadratic

def remove_nonlinear(
    image: "Napari.types.ImageData",
    mask: "Napari.types.LabelsData"=None,
):
    filtered_image = Filters(
        image=image, 
        filename="FILE", 
        pixel_to_nm_scaling=1, 
        row_alignment_quantile=0.5,
        threshold_method="std_dev",
        otsu_threshold_multiplier=1.0,
        threshold_std_dev=1.0,
        threshold_absolute=1.0,
        gaussian_size=1.0121397464510862,
        gaussian_mode="nearest"
        )
    removed_nonlinear = filtered_image.remove_nonlinear_polynomial(image=image, mask=mask)
    return removed_nonlinear
