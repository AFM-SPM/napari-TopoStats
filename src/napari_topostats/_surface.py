"""Create static and frame-dependent napari surface layers."""

from typing import Annotated

import numpy as np
from napari import Viewer
from napari.types import ImageData

from napari_topostats.utils import calculate_contrast_limits


def image_to_surface(
    image: ImageData,
    pixel_to_nm_scaling: float = 1.0,
    input_z_units: str = "nm",
    vertical_exaggeration: float = 1.0,
    triangle_size: Annotated[int, {"min": 1}] = 1,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Convert a 2D AFM image or image stack into napari surface data.

    A 3D ``(frame, y, x)`` stack produces a four-dimensional
    ``(z, frame, y, x)`` surface. This aligns its frame, y, and x axes with
    the source image while allowing napari to display z, y, and x.

    Parameters
    ----------
    image : napari.types.ImageData
        Two-dimensional ``(y, x)`` image or three-dimensional
        ``(frame, y, x)`` image stack to convert.
    pixel_to_nm_scaling : float, optional
        Width of each pixel in nanometres, by default 1.0.
    input_z_units : str, optional
        Length unit of the image values. Supported values are metres,
        millimetres, micrometres, nanometres, and picometres. Heights are
        converted to nanometres, by default ``"nm"``.
    vertical_exaggeration : float, optional
        Factor applied to surface heights, by default 1.0.
    triangle_size : int, optional
        Sampling interval in source-image pixels. Larger values produce
        fewer, larger triangles for faster rendering, by default 1.

    Returns
    -------
    tuple of np.ndarray
        Vertices, triangular face indices, and per-vertex values in the
        format expected by a napari Surface layer.
    """
    unit_to_nanometres = {
        "m": 1e9,
        "mm": 1e6,
        "um": 1e3,
        "µm": 1e3,
        "μm": 1e3,
        "nm": 1.0,
        "pm": 1e-3,
    }
    normalised_z_units = str(input_z_units).strip().lower()
    if normalised_z_units not in unit_to_nanometres:
        raise ValueError(f"Unsupported image height unit: {input_z_units}")

    if image.ndim not in (2, 3):
        raise ValueError("Input image must be 2D or 3D.")
    if isinstance(triangle_size, bool) or not isinstance(triangle_size, int):
        raise TypeError("Triangle size must be an integer.")
    if triangle_size < 1:
        raise ValueError("Triangle size must be at least 1.")

    image = image * unit_to_nanometres[normalised_z_units] * vertical_exaggeration

    y_indices = np.arange(0, image.shape[-2], triangle_size)
    x_indices = np.arange(0, image.shape[-1], triangle_size)
    if y_indices[-1] != image.shape[-2] - 1:
        y_indices = np.append(y_indices, image.shape[-2] - 1)
    if x_indices[-1] != image.shape[-1] - 1:
        x_indices = np.append(x_indices, image.shape[-1] - 1)

    y, x = np.meshgrid(
        y_indices,
        x_indices,
        indexing="ij",
    )

    y_coordinates = (y.ravel() * pixel_to_nm_scaling).astype(np.float32)
    x_coordinates = (x.ravel() * pixel_to_nm_scaling).astype(np.float32)
    stack_lowered = image[..., y_indices[:, np.newaxis], x_indices].astype(np.float32)
    if stack_lowered.ndim == 3:
        initial_image = stack_lowered[0]
        vertices = np.column_stack(
            (initial_image.ravel(), np.zeros(initial_image.size, dtype=np.float32), y_coordinates, x_coordinates)
        )
    else:
        vertices = np.column_stack(
            (stack_lowered.ravel(), np.zeros(stack_lowered.size, dtype=np.float32), y_coordinates, x_coordinates)
        )
    faces = make_faces(shape_y=stack_lowered.shape[-2], shape_x=stack_lowered.shape[-1])

    return vertices, faces, stack_lowered


def make_faces(shape_y: int, shape_x: int) -> np.ndarray:
    """
    Generate triangular faces for a grid of vertices.

    Parameters
    ----------
    shape_y : int
        Number of rows in the grid.
    shape_x : int
        Number of columns in the grid.

    Returns
    -------
    np.ndarray
        Array of triangular face indices.
    """
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

    return np.asarray(faces, dtype=np.int32)


def create_dynamic_surface(
    viewer: Viewer,
    return_value: tuple[np.ndarray, np.ndarray, np.ndarray],
    name: str,
):
    """
    Create a dynamic surface layer that updates with the current frame of a source image layer.

    Parameters
    ----------
    viewer : napari.Viewer
        The napari viewer instance.
    return_value : tuple[np.ndarray, np.ndarray, np.ndarray]
        Vertices, face indices, and sampled height data from ``image_to_surface``.
    name : str
        Name of the surface layer.
    """
    vertices, faces, stack = return_value
    if stack.ndim == 3:
        current_frame = viewer.dims.current_step[-3]

        vertices[:, 0] = stack[current_frame].ravel()
        vertices[:, 1] = current_frame

        surface_layer = viewer.add_surface(
            data=(vertices, faces, stack[current_frame].ravel()),
            scale=(1.0, 1.0, 1.0, 1.0),
            name=name,
            contrast_limits=calculate_contrast_limits(stack, percentage=0.5),
        )
        surface_controller = DynamicSurfaceController(
            viewer=viewer,
            surface_layer=surface_layer,
            stack=stack,
            vertices=vertices,
            faces=faces,
        )
        surface_layer._dynamic_surface_controller = surface_controller  # pylint: disable=protected-access
    else:
        surface_layer = viewer.add_surface(
            data=(vertices, faces, stack.ravel()),
            scale=(1.0, 1.0, 1.0, 1.0),
            name=name,
        )
    viewer.dims.order = (1, 0, 2, 3)
    viewer.dims.ndisplay = 3


class DynamicSurfaceController:
    """
    Update a surface layer when the selected viewer frame changes.

    Parameters
    ----------
    viewer : napari.Viewer
        Viewer containing the surface layer.
    surface_layer : napari.layers.Surface
        Surface layer updated by the controller.
    stack : np.ndarray
        Image stack containing the height values for each frame.
    vertices : np.ndarray
        Surface vertices updated for the selected frame.
    faces : np.ndarray
        Triangular face indices shared by every frame.
    """

    def __init__(self, viewer, surface_layer, stack, vertices, faces):
        """
        Initialises DynamicSurfaceController.

        Parameters
        ----------
        viewer : napari.Viewer
            Viewer containing the surface layer.
        surface_layer : napari.layers.Surface
            Surface layer updated by the controller.
        stack : np.ndarray
            Image stack containing the height values for each frame.
        vertices : np.ndarray
            Surface vertices updated for the selected frame.
        faces : np.ndarray
            Triangular face indices shared by every frame.
        """
        self.viewer = viewer
        self.surface_layer = surface_layer
        self.stack = stack
        self.vertices = vertices
        self.faces = faces
        self.pending_frame = None

        viewer.dims.events.current_step.connect(self._request_update)
        viewer.layers.events.removed.connect(self._handle_layer_removed)

    def _request_update(self, event=None):  # pylint: disable=unused-argument
        """
        Queue a surface refresh for the newly selected frame.

        Parameters
        ----------
        event : Any
            Frame-change event emitted by napari.
        """
        self.pending_frame = self.viewer.dims.current_step[-3]
        self._update_surface()

    def _update_surface(self):
        """Update surface data to a new frame."""
        frame = self.pending_frame

        if frame is None or frame < 0 or frame >= self.stack.shape[0]:
            return

        self.vertices[:, 0] = self.stack[frame].ravel()
        self.vertices[:, 1] = frame

        self.surface_layer.data = (
            self.vertices,
            self.faces,
            self.stack[frame].ravel(),
        )

    def close(self):
        """Disconnect events and release references held by the controller."""
        if self.viewer is None:
            return

        viewer = self.viewer
        surface_layer = self.surface_layer

        viewer.dims.events.current_step.disconnect(self._request_update)
        viewer.layers.events.removed.disconnect(self._handle_layer_removed)

        if getattr(surface_layer, "_dynamic_surface_controller", None) is self:
            delattr(surface_layer, "_dynamic_surface_controller")

        self.viewer = None
        self.surface_layer = None
        self.stack = None
        self.vertices = None
        self.faces = None
        self.pending_frame = None

    def _handle_layer_removed(self, event):
        """
        Release the controller when its surface layer is removed.

        Parameters
        ----------
        event : Any
            Layer-removal event emitted by napari.
        """
        if event.value is self.surface_layer:
            self.close()
