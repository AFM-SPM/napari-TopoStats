"""Implemention of TopoStats as a plugin in napari"""

import multiprocessing

try:
    from ._version import version as __version__
except ImportError:
    __version__ = "unknown"

# Only import widget GUI elements in the main process to prevent child workers
# from loading heavy napari/Qt GUI libraries.
if multiprocessing.parent_process() is None:
    from ._widget import TopoStatsRootWidget
else:
    TopoStatsRootWidget = None

__all__ = ("TopoStatsRootWidget",)
