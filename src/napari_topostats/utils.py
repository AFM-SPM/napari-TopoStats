"""Contains functions surrounding utilities and cosmetics."""

import copy
import inspect
from typing import Any

import numpy as np
from napari.types import ImageData


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


def unflatten_dict(flat: dict) -> dict:
    """
    Function used for reverting to the dict form where keys can correspond to dict values like json format

    Parameters
    ----------
    flat : dict
        The dictionary to unflatten

    Returns
    -------
    dict
        The unflattened dictionary
    """
    result = {}
    for k, v in flat.items():
        keys = k.split(".")
        d = result
        for part in keys[:-1]:
            d = d.setdefault(part, {})
        d[keys[-1]] = v
    return result


# pylint: disable=too-many-branches
def _eval(obj: Any, string: str) -> Any:
    """
    Evaluate a path string on an object to access its attributes or subscripts. For example, given a list `lst`, the
    string "lst[0].name" would return the name attribute of the first element of the list. This is done without
    using `eval` to avoid security risks.

    Parameters
    ----------
    obj : Any
        The object on which to evaluate the string.
    string : str
        The path string to evaluate.

    Returns
    -------
    Any
        The result of the evaluation.
    """
    # Remove spaces from the string for easier parsing
    string = string.replace(" ", "")
    if string == "":
        # If the string is empty, return the object itself
        return obj

    # Handle subscript access, e.g., [0], [1:3], ['key']
    if string[0] == "[":
        # Find the next punctuation to determine the subscript type
        next_punc = next_punctuation(string, 1, checking_for=",()[].")
        if next_punc != -1 and string[next_punc] == ",":
            # Handle tuple subscripts, e.g., [1,2]
            axes = []
            for i in string[1 : string.index("]", 1)].split(","):
                if i == ":":
                    axes.append(slice(None))
                elif i.isdigit():
                    axes.append(int(i))
            subscript = tuple(axes)
            obj = obj[subscript]
        else:
            # Handle single index or key, e.g., [0] or ['key']
            subscript = string[1 : string.index("]", 1)]
            if subscript.isdigit():
                obj = obj[int(subscript)]
            else:
                key = subscript.replace("'", "").replace('"', "")
                obj = obj[key]
        # Recursively evaluate the remaining string
        remaining = string[string.index("]", 1) + 1 :]
        return _eval(obj, remaining)

    # Handle attribute access or method calls, e.g., .attr or .method()
    if string[0] == ".":
        index = next_punctuation(string, 1)
        if index == -1:
            # No further punctuation, just get the attribute
            attr = string[1:]
            if hasattr(obj, attr):
                return getattr(obj, attr)
            raise AttributeError(f"'{type(obj).__name__}' object has no attribute '{attr}'")

        if string[index] == "(":
            # Handle method call, e.g., .method(args)
            func_name = string[1:index]
            if hasattr(obj, func_name):
                func = getattr(obj, func_name)
                args_str = string[index + 1 : string.index(")", index + 1)]
                args = [arg.strip() for arg in args_str.split(",") if arg.strip()]
                result = func(*args)
                remaining = string[string.index(")", index + 1) + 1 :]
                # Recursively evaluate the remaining string
                return _eval(result, remaining)
            raise AttributeError(f"'{type(obj).__name__}' object has no callable '{func_name}'")

        # Otherwise, handle attribute access followed by more operations
        attr = string[1:index]
        if hasattr(obj, attr):
            obj = getattr(obj, attr)
        else:
            raise AttributeError(f"'{type(obj).__name__}' object has no attribute '{attr}'")
        remaining = string[index:]
        # Recursively evaluate the remaining string
        return _eval(obj, remaining)

    # If the string does not start with '[' or '.', return the object
    return obj


def next_punctuation(s: str, start: int = 0, checking_for: str = ".([") -> int:
    """Find the next punctuation character in a string."""
    for i in range(start, len(s)):
        if s[i] in checking_for:
            return i
    return -1


def is_binary_image(arr: np.ndarray) -> bool:
    """Check if the array is a binary image (0s and 1s or 0s and 255s).
    Parameters
    ----------
    arr : np.ndarray
        The array to check.
    Returns
    -------
    bool
        True if the array is a binary image, False otherwise.
    """
    unique_vals = np.unique(arr)
    # Check if unique values are subset of {0,1,255}
    return set(unique_vals).issubset({0, 1, 255})


def remove_all_but_last(word: str, text: str) -> str:
    """Remove all occurrences of 'word' in 'text' except the last one.

    Parameters
    ----------
    word : str
        The word to remove.
    text : str
        The text from which to remove the word.

    Returns
    -------
    str
        The text with all occurrences of the word removed except the last one.
    """
    parts = text.rsplit(word, maxsplit=1)
    if len(parts) == 1:
        return text  # word not found or only once
    return (parts[0].replace(word, "") + word + parts[1]).replace("  ", " ").strip()  # Remove extra spaces and return


def all_curves(
    curves,
    func,
    shape_x: int | None = None,
    shape_y: int | None = None,
    type_class=None,
    flip_image: bool = False,
    **kwargs,
):
    print(f"Running {func.__name__} on all curves with shape ({shape_x}, {shape_y})")
    print(f"Curves is object of type {type(curves)}")
    if None in (shape_x, shape_y):
        if hasattr(curves, "dims"):
            shape_y = curves.dims[0]
            shape_x = curves.dims[1] if len(curves.dims) > 1 else 1
        elif isinstance(curves[0], list):
            shape_x = len(curves[0])
            shape_y = len(curves)
        else:
            shape_x = len(curves)
            shape_y = 1

    if isinstance(curves[0], list):
        # If curves is a list of lists, flatten it.
        curves = [item for sublist in curves for item in sublist]

    image_map = [[None for _ in range(shape_x)] for _ in range(shape_y)]

    if type_class is not None:
        class_sig = inspect.signature(type_class)
        class_kwargs = {}
        for p in class_sig.parameters:
            if p in kwargs:
                class_kwargs[p] = kwargs[p]

    func_sig = inspect.signature(func)
    func_kwargs = {}
    for p in func_sig.parameters:
        if p in kwargs:
            func_kwargs[p] = kwargs[p]

    for y in range(shape_y):
        for x in range(shape_x):
            idx = y * shape_x + x
            curve = curves[idx]
            if type_class is not None:
                if "curve" in class_kwargs:
                    # If curve is a parameter in type_class parameters, instantiate the class with curve and class_kwargs
                    instance = type_class(curve=curve, **class_kwargs)
                else:
                    # Otherwise, just pass the class_kwargs without curve
                    instance = type_class(**class_kwargs)

                # Run function on instance, passing func_kwargs
                func = getattr(instance, func.__name__)
                if "curve" in func_sig.parameters:
                    point = func(curve=curve, **func_kwargs)
                else:
                    point = func(**func_kwargs)
            else:
                point = func(curve=curve, **func_kwargs)
            image_map[y][x] = point
    if isinstance(image_map[0][0], dict):
        return image_map
    image_map = np.array(image_map)
    if flip_image:
        image_map = np.flipud(image_map)
    return image_map
