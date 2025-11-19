"""Implemention of TopoStats as a plugin in napari"""

try:
    from ._version import version as __version__
except ImportError:
    __version__ = "unknown"
from packaging.version import parse as parse_version
from topostats import __version__ as topostats_version

from ._alerts import show_error_dialog
from ._sample_data import make_sample_data
from ._state import MIN_TOPOSTATS_VERSION
from ._widget import (
    ImageThreshold,
    TopoStatsRootWidget,
    gaussian_filter_image,
    median_align_rows,
    remove_nonlinear_background,
    remove_planar_tilt,
    remove_quadratic_background,
    remove_scars_from_image,
    zero_average_background,
)
from ._writer import write_multiple, write_single_image

if parse_version(topostats_version) < parse_version(MIN_TOPOSTATS_VERSION):
    show_error_dialog(
        f"TopoStats version {topostats_version} is outdated and does not work with this plugin."
        f"Please install at least TopoStats version {MIN_TOPOSTATS_VERSION}.\n"
        f"This can be done with `pip install topostats=={MIN_TOPOSTATS_VERSION}`",
        raise_exception=True,
    )

__all__ = (
    "write_single_image",
    "write_multiple",
    "make_sample_data",
    "ImageThreshold",
    "remove_scars_from_image",
    "median_align_rows",
    "remove_planar_tilt",
    "remove_quadratic_background",
    "remove_nonlinear_background",
    "zero_average_background",
    "gaussian_filter_image",
    "TopoStatsRootWidget",
)
