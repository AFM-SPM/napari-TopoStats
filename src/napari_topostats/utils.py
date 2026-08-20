"""Contains functions surrounding utilities and cosmetics."""

# pylint: disable=import-outside-toplevel,too-many-nested-blocks,too-many-statements

from __future__ import annotations

import inspect
import multiprocessing
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import numpy as np
from joblib import Parallel, delayed
from tqdm import tqdm

if TYPE_CHECKING:
    from napari.types import ImageData


def image_to_surface(
    image: ImageData,
    pixel_to_nm_scaling: float = 1.0,
    input_z_units: str = "nm",
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Convert a 2D AFM image into surface data for a napari Surface layer.

    Each image pixel becomes a vertex whose height is the corresponding
    image value. Adjacent pixels are connected by two triangular faces, and
    the flattened image values are used as the per-vertex surface values.

    Parameters
    ----------
    image : napari.types.ImageData
        Two-dimensional image to convert.
    pixel_to_nm_scaling : float, optional
        Width of each pixel in nanometres, by default 1.0.
    input_z_units : str, optional
        Unit of the image values. Values in metres are converted to
        nanometres, by default ``"nm"``.

    Returns
    -------
    tuple of np.ndarray
        Vertices, triangular face indices, and per-vertex values in the
        format expected by a napari Surface layer.
    """
    shape_y, shape_x = image.shape

    vertices = []

    if input_z_units == "m":
        image = image * 1e9  # Convert meters to nanometers for visualization

    # Convert the 2D image into a list of vertices in 3D space with each vertex as (z, y, x)
    for y in range(shape_y):
        for x in range(shape_x):
            vertices.append((image[y, x], y * pixel_to_nm_scaling, x * pixel_to_nm_scaling))

    faces = []

    for y in range(shape_y - 1):
        for x in range(shape_x - 1):
            # Draw a grid of squares between the vertices
            top_left = y * shape_x + x
            top_right = top_left + 1
            bottom_left = top_left + shape_x
            bottom_right = bottom_left + 1

            # Create two triangles for each square in the grid by cutting the square diagonally
            faces.append([top_left, bottom_left, bottom_right])
            faces.append([top_left, bottom_right, top_right])

    return np.array(vertices), np.array(faces), image.ravel()


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


def _all_curves_raw_worker(
    curve: dict[str, dict[str, np.ndarray]],
    func: Callable[..., Any],
    type_class: type[Any] | None,
    func_kwargs: dict[str, Any],
    class_kwargs: dict[str, Any],
    has_curve_in_func_sig: bool,
) -> Any:
    """Worker function for parallel curve processing returning full value from function."""
    if type_class is not None:
        # Instantiate the class with curve if it's a parameter, otherwise just with class_kwargs
        instance = type_class(curve=curve, **class_kwargs) if "curve" in class_kwargs else type_class(**class_kwargs)

        # Get the bound method from the instance
        method = getattr(instance, func.__name__)
        return method(curve=curve, **func_kwargs) if has_curve_in_func_sig else method(**func_kwargs)
    return func(curve=curve, **func_kwargs)


# pylint: disable=too-many-arguments,too-many-locals
def all_curves(
    curves: Any,
    func: Callable[..., Any],
    shape_x: int | None = None,
    shape_y: int | None = None,
    type_class: type[Any] | None = None,
    parallel: bool | None = None,
    num_workers: int | None = None,
    h5file: Any | None = None,
    new_volume_name: str | None = None,
    **kwargs: Any,
) -> tuple[np.ndarray, str] | bool:
    """
    Apply a function to all curves in a list of curves, with optional parameters for shaping the output and handling
    classes. Should return a 2D array of the same shape as the input curves, where each element is the result of
    applying the function to the corresponding curve.

    Parameters
    ----------
    curves : CurveVolume
        The volume of curves to apply the function to.
    func : function
        The function to apply to each curve.
    shape_x : int, optional
        The number of columns in the output map, by default None. If None, it will be inferred from the input curves.
    shape_y : int, optional
        The number of rows in the output map, by default None. If None, it will be inferred from the input curves.
    type_class : class, optional
        A class to instantiate for each curve, by default None.
    flip_image : bool, optional
        Whether to flip the output image vertically, by default False.
    parallel : bool, optional
        Whether to run the processing in parallel, by default None (auto-detect based on process intensity).
    num_workers : int, optional
        The number of worker processes to use for parallel processing, by default None (cpu_count).
    **kwargs : dict
        Additional keyword arguments to pass to the function or class.

    Returns
    -------
    np.ndarray
        A 2D array of the results of applying the function to each curve.
    """
    if None in (shape_x, shape_y):
        if hasattr(curves, "shape"):
            shape_y = curves.shape[0]
            shape_x = curves.shape[1] if len(curves.shape) > 1 else 1
        else:
            raise ValueError("Curves must be of the CurvesDataset type defined by AFMReader.")

    # Prepare keyword arguments for class and function
    class_kwargs = {}
    if type_class is not None:
        class_sig = inspect.signature(type_class)
        for p in class_sig.parameters:
            if p in kwargs:
                class_kwargs[p] = kwargs[p]

    func_sig = inspect.signature(func)
    func_kwargs = {}
    for p in func_sig.parameters:
        if p in kwargs:
            func_kwargs[p] = kwargs[p]

    has_curve_in_func_sig = "curve" in func_sig.parameters

    # Try to get z_units from the first curve
    first_curve = dict(curves[0, 0])
    start_time = time.perf_counter()
    return_value = _all_curves_raw_worker(
        first_curve, func, type_class, func_kwargs, class_kwargs, has_curve_in_func_sig
    )
    execution_time = time.perf_counter() - start_time
    z_units = "nm"
    if parallel is None:
        # Auto-detect based on execution time of first curve
        parallel = execution_time > 0.002  # Threshold of 0.002 seconds for deciding to parallelize
    if isinstance(return_value, tuple):
        actual_value = return_value[0]
        if len(return_value) > 1 and isinstance(return_value[1], str):
            z_units = return_value[1]
            if len(return_value) > 2 and isinstance(return_value[2], dict):
                for key, value in return_value[2].items():
                    curves.analysis_results[key] = np.empty((shape_y, shape_x), dtype=type(value))
    else:
        actual_value = return_value
    curve_correcting = isinstance(actual_value, dict)
    if not curve_correcting:
        first_result_array = np.asarray(actual_value)
        result_is_array = first_result_array.ndim > 0
        if result_is_array:
            image_map = np.empty(
                (
                    first_result_array.shape[0],
                    shape_y,
                    shape_x,
                ),
                dtype=float,
            )
        else:
            image_map = np.empty((shape_y, shape_x), dtype=type(actual_value))

    def _all_curves_worker(curve: dict[str, dict[str, np.ndarray]]) -> Any:
        """Worker function for parallel curve processing."""
        return_value = _all_curves_raw_worker(curve, func, type_class, func_kwargs, class_kwargs, has_curve_in_func_sig)
        return return_value

    if curve_correcting:
        # AFMReader needs to be imported here to prevent it being imported for every worker process
        from AFMReader.data_classes import CurvesVolumeMetadata
        from AFMReader.h5_jpk import CurvesH5Volume
        from AFMReader.h5_saver import H5Saver

        saver = h5file if isinstance(h5file, H5Saver) else H5Saver(h5file=h5file)
        new_volume_name = f"{curves.name}_{func.__name__}" if new_volume_name is None else new_volume_name
        processed_metadata = CurvesVolumeMetadata(
            shape=curves.shape,
            channel_units=curves.metadata.channel_units.copy(),  # .copy() prevents sharing this dictionary
            segment_names=curves.metadata.segment_names.copy(),
            flip_image=curves.flip_image,
        )

        processed_volume = CurvesH5Volume(
            name=new_volume_name,
            shape=curves.shape,
            volume_data_group=curves.volume_data_group,
            metadata=processed_metadata,
            flip_image=curves.flip_image,
        )
        processed_volume.volume_data_group = saver.setup_volume(processed_volume)

    if num_workers is None:
        # Default to all but 2 cores, minimum 1
        num_workers = max(1, multiprocessing.cpu_count() - 2)

    if parallel and num_workers > 1:
        # Use joblib.Parallel with a generator expression to keep it lazy.
        if curve_correcting:
            processed_generator = Parallel(n_jobs=num_workers, return_as="generator")(
                delayed(_all_curves_worker)(curve) for curve in curves.iter_curves(flip_image=False)
            )
            for idx, curve_out in enumerate(
                tqdm(processed_generator, total=len(curves), desc=f"Running {func.__name__} (Parallel)")
            ):
                saver.save_curve(
                    curve_data=curve_out,
                    volume_name=new_volume_name,
                    num_of_curves=len(processed_volume),
                    curve_num=idx,
                    segment_names=processed_volume.metadata.segment_names,
                )
        else:
            results = Parallel(n_jobs=num_workers)(
                delayed(_all_curves_worker)(curve)
                for curve in tqdm(
                    curves.iter_curves(flip_image=False), total=len(curves), desc=f"Running {func.__name__} (Parallel)"
                )
            )
            # Reshape results into the image map
            for i, result in enumerate(results):
                y = i // shape_x
                x = i % shape_x
                if isinstance(result, tuple) and len(result) > 1:
                    extracted_result = result[0]
                    if len(result) > 2 and isinstance(result[2], dict):
                        for key, value in result[2].items():
                            curves.analysis_results[key][y][x] = value
                else:
                    extracted_result = result
                if result_is_array:
                    # image_map is initialised whenever curve_correcting is false, as it is in this branch.
                    # pylint: disable-next=used-before-assignment
                    image_map[:, y, x] = extracted_result
                else:
                    image_map[y][x] = extracted_result

    else:
        if curve_correcting:
            for i, curve in enumerate(
                tqdm(
                    curves.iter_curves(flip_image=False),
                    total=len(curves),
                    desc=f"Running {func.__name__} (Sequential)",
                )
            ):
                worker_result = _all_curves_worker(curve)
                saver.save_curve(
                    curve_data=worker_result,
                    volume_name=new_volume_name,
                    num_of_curves=len(processed_volume),
                    curve_num=i,
                    segment_names=processed_volume.metadata.segment_names,
                )
        else:
            for i, curve in enumerate(
                tqdm(
                    curves.iter_curves(flip_image=False),
                    total=len(curves),
                    desc=f"Running {func.__name__} (Sequential)",
                )
            ):
                worker_result = _all_curves_worker(curve)
                y = i // shape_x
                x = i % shape_x
                if isinstance(worker_result, tuple) and len(worker_result) > 1:
                    if len(worker_result) > 2 and isinstance(worker_result[2], dict):
                        for key, value in worker_result[2].items():
                            curves.analysis_results[key][y][x] = value
                    extracted_result = worker_result[0]
                else:
                    extracted_result = worker_result
                if result_is_array:
                    image_map[:, y, x] = extracted_result
                else:
                    image_map[y][x] = extracted_result

    if curve_correcting:
        saver.complete_saving(volume=processed_volume)
        return True
    image_map = np.array(image_map)
    if curves.flip_image:
        image_map = np.flip(image_map, axis=-2)
    return image_map, z_units
