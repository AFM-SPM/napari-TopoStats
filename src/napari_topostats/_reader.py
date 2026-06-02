"""Reader module to tell napari how to handle dropped python files"""

from napari.viewer import current_viewer

from ._script_handler import load_py_files


def napari_get_reader(path: list | str):
    """Return the reader to allow python files to be loaded"""
    if isinstance(path, list):
        path = path[0]

    if not path.endswith((".py", ".ipynb")):
        return None

    return reader_function


def reader_function(path):
    """Reader to return functions from python file path"""
    viewer = current_viewer()
    load_py_files(paths=[path] if isinstance(path, str) else path, viewer=viewer)
    return [(None,)]
