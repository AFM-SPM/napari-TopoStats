"""Implemention of TopoStats as a plugin in napari"""

import importlib
import multiprocessing
import warnings

try:
    from ._version import version as __version__
except ImportError:
    __version__ = "unknown"

# Only import widget GUI elements in the main process to prevent child workers
# from loading heavy napari/Qt GUI libraries.
if multiprocessing.parent_process() is None:
    # topoly 1.1.0 contains non-raw regex strings whose compile warnings can
    # become SyntaxErrors when the host environment promotes warnings to errors.
    # Preload only that dependency with those warnings suppressed so napari can
    # import the plugin command. This can be removed once topoly publishes a fixed release.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        warnings.simplefilter("ignore", SyntaxWarning)
        importlib.import_module("topoly")

    from ._widget import TopoStatsRootWidget
else:
    TopoStatsRootWidget = None

__all__ = ("TopoStatsRootWidget",)
