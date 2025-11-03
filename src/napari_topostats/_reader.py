"""
This module is an example of a barebones numpy reader plugin for napari.

It implements the Reader specification, but your plugin may choose to
implement multiple readers or even other plugin contributions. see:
https://napari.org/stable/plugins/guides.html?#readers
"""

from pathlib import Path

import numpy as np
from qtpy.QtWidgets import QInputDialog
from topostats import io


def napari_get_reader(path):
    """A basic implementation of a Reader contribution.

    Parameters
    ----------
    path : str or list of str
        Path to file, or list of paths.

    Returns
    -------
    function or None
        If the path is a recognized format, return a function that accepts the
        same path or list of paths, and returns a list of layer data tuples.
    """
    if isinstance(path, list):
        # reader plugins may be handed single path, or a list of paths.
        # if it is a list, it is assumed to be an image stack...
        # so we are only going to look at the first file.
        path = path[0]

    # if we know we cannot read the file, we immediately return None.
    if not path.endswith((".spm", ".jpk", ".ibw", ".gwy", ".topostats")):
        return None

    # otherwise we return the *function* that can read ``path``.
    return reader_function


# @magicgui
# def choose_channel():

# channel = input("Channel: ")
#    return channel


def reader_function(path):
    """Take a path or list of paths and return a list of LayerData tuples.

    Readers are expected to return data as a list of tuples, where each tuple
    is (data, [add_kwargs, [layer_type]]), "add_kwargs" and "layer_type" are
    both optional.

    Parameters
    ----------
    path : str or list of str
        Path to file, or list of paths.

    Returns
    -------
    layer_data : list of tuples
        A list of LayerData tuples where each tuple in the list contains
        (data, metadata, layer_type), where data is a numpy array, metadata is
        a dict of keyword arguments for the corresponding viewer.add_* method
        in napari, and layer_type is a lower-case string naming the type of
        layer. Both "meta", and "layer_type" are optional. napari will
        default to layer_type=="image" if not provided
    """
    # handle both a string and a list of strings
    paths = [Path(path)] if isinstance(path, str) else Path(path)
    # load all files into array
    available_channels = None
    while True:
        try:
            if available_channels is None:
                message = "Channel Name: "
            else:
                message = f"Available channels: {available_channels}"
            # adds dialog box for channel input
            user_input, ok = QInputDialog.getText(
                None, "Input Channel", message
            )
            if not ok:
                return None
            all_scans = io.LoadScans(paths, user_input)
            all_scans.get_data()
            scan_data_dict = all_scans.img_dict
            if not scan_data_dict:
                raise ValueError
            break
        except ValueError:  # TODO more open exceptions?
            available_channels = "Check console error message."

    # stack arrays into single array
    arrays = []
    for values in scan_data_dict.values():
        arrays.append(values["image_original"])
    data = np.squeeze(np.stack(arrays))

    # optional kwargs for the corresponding viewer.add_* method
    add_kwargs = {}

    layer_type = "image"  # optional, default is "image"
    return [(data, add_kwargs, layer_type)]
