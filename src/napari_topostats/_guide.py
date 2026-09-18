"""Module to handle loading and displaying the user guide for the plugin."""

import json
from collections.abc import Iterator
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
import time
import markdown
from napari import Viewer
from platformdirs import user_config_dir
from qtpy.QtCore import QRectF, QTimer, QUrl
from qtpy.QtGui import QMovie, QResizeEvent, QTextBlock, QTextCursor, QTextDocument, QTextDocumentFragment, QTextFragment
from qtpy.QtWidgets import QDialog, QTextBrowser, QVBoxLayout, QWidget

from napari_topostats._alerts import show_error_dialog

# Keep a reference to the dialog to prevent garbage collection and keep it non-modal
_guide_dialog = None


@dataclass(frozen=True)
class GuideSection:
    """Rendered guide HTML and the directory containing its local resources."""

    html: str
    directory: Path


@dataclass
class _AnimatedImage:
    """A movie and every place its resource appears in the guide document."""

    movie: QMovie
    resource_url: QUrl
    position: tuple[int, int]
    block: QTextBlock
    is_visible: bool


def get_guide_path() -> Path:
    """
    Get the path to the GUIDE.md file.

    Returns
    -------
    Path
        The path to the GUIDE.md file.

    Raises
    ------
    FileNotFoundError
        If GUIDE.md cannot be found.
    """
    dev_path = Path(__file__).resolve().parent / "GUIDE.md"
    if dev_path.exists():
        return dev_path

    raise FileNotFoundError("GUIDE.md could not be found.")


def load_base_guide() -> GuideSection:
    """
    Load the TopoStats guide and convert it to HTML.

    Returns
    -------
    GuideSection
        The rendered HTML and the directory containing its local resources.
    """
    guide_path = get_guide_path()
    with open(guide_path, encoding="utf-8") as f:
        text = f.read()

    html_content = markdown.markdown(text, extensions=["extra", "codehilite", "tables"])
    return GuideSection(html=html_content, directory=guide_path.parent)


def _load_guide_sections() -> list[GuideSection]:
    """Load the TopoStats guide and any optional guide sections."""
    guide_sections = [load_base_guide()]

    try:
        # Attempt to add the forcestats guide if it is installed
        from forcestats.guide import get_guide_html  # pylint: disable=import-outside-toplevel

        html_content, guide_directory = get_guide_html()
        guide_sections.append(GuideSection(html=html_content, directory=guide_directory))
    except ModuleNotFoundError as error:
        # If the forcestats guide is not installed, we simply skip it.
        if error.name not in {"forcestats", "forcestats.guide"}:
            raise

    return guide_sections


def _iter_image_fragments(
    document: QTextDocument, return_blocks: bool = False
) -> Iterator[QTextFragment | tuple[QTextFragment, QTextBlock]]:
    """Yield every image fragment in a rich-text document."""

    # A QTextDocument is composed of blocks (essentially paragraphs)
    block = document.begin()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            # Each block can contain multiple fragments (text or components that have the same formatting)
            fragment = iterator.fragment()
            # Fragments are basically assumed to be text, with bold and italic text in the same line being separate 
            # fragments, but images are basically treated as some special text component with special formatting
            if fragment.isValid() and fragment.charFormat().isImageFormat():
                if return_blocks:
                    # Block may be needed for finding the bounding box of the fragment
                    yield fragment, block
                else:
                    yield fragment
            iterator += 1
        block = block.next()


def _resolve_image_paths(document: QTextDocument) -> None:
    """Replace relative image names with URLs resolved against the document base URL."""
    # Store image data needed to make an update for later application so iteration isn't affected.
    updates = []

    for fragment in _iter_image_fragments(document):
        image_format = fragment.charFormat().toImageFormat()
        source_url = QUrl(image_format.name())
        if source_url.isRelative():
            # Resolve relative image paths to absolute URLs using the document's base URL.
            image_format.setName(document.baseUrl().resolved(source_url).toString())
            updates.append((fragment.position(), fragment.length(), image_format))

    # Apply changes after iteration because changing a format can alter the document's fragment boundaries.
    for position, length, image_format in updates:
        # Text documents require using a cursor to apply character format changes, as components like images
        # cannot be directly modified through the fragment itself. Conceptually, we select the bit we want to
        # update at its position to its end then apply the change to the selection.
        cursor = QTextCursor(document)
        cursor.setPosition(position)
        cursor.setPosition(position + length, QTextCursor.KeepAnchor)
        cursor.setCharFormat(image_format)


def _create_section_document(section: GuideSection) -> QTextDocument:
    """Create a document for each guide section whose local image names are absolute URLs."""
    document = QTextDocument()
    # This is basically just storing the base url and is not used automatically for resolving relative image paths
    # and is instead used 'manually' in `_resolve_image_paths`. This is because the sections QTextDocument later loses
    # its base URL when inserted into the combined document.
    document.setBaseUrl(QUrl.fromLocalFile(str(section.directory.resolve()) + "/"))
    document.setHtml(section.html)
    _resolve_image_paths(document)
    return document


def _combine_guide_sections(sections: list[GuideSection], parent: QWidget) -> QTextDocument:
    """Combine independently resolved guide sections into one document."""
    combined_document = QTextDocument(parent)
    # Cursor is used for inserting sections into the combined document at the cursor's current position.
    cursor = QTextCursor(combined_document)

    for index, section in enumerate(sections):
        if index:
            # We need to add a new block past the first section
            cursor.insertBlock()

        # Insert the section as a fragment into the combined document.
        section_document = _create_section_document(section)
        cursor.insertFragment(QTextDocumentFragment(section_document))
        # Move to the end of the combined document to prepare to insert the next section.
        cursor.movePosition(QTextCursor.End)

    return combined_document


class _AnimatedGuideBrowser(QTextBrowser):
    """Display a combined guide and animate only GIFs in the visible viewport."""

    _VISIBILITY_DELAY_MS = 50

    def __init__(self, sections: list[GuideSection], parent: QWidget | None = None):
        super().__init__(parent)
        self.setOpenExternalLinks(True)

        # Setup a timer to check the visibility of animated images (as the user scrolls)
        self._visibility_timer = QTimer(self)
        self._visibility_timer.setSingleShot(True)
        self._visibility_timer.setInterval(self._VISIBILITY_DELAY_MS)
        self._visibility_timer.timeout.connect(self._update_movie_visibility)
        self._first_update = True

        self.setDocument(_combine_guide_sections(sections, self))
        self._animated_images = self._create_animated_images()

        # As the user scrolls, schedule a visibility update for the GIF animations.
        self.verticalScrollBar().valueChanged.connect(self._schedule_visibility_update)
        self.horizontalScrollBar().valueChanged.connect(self._schedule_visibility_update)
        # Schedule an initial visibility update for the GIF animations to start the animations currently in view.
        QTimer.singleShot(0, self._update_movie_visibility)

    def resizeEvent(self, event: QResizeEvent):  # noqa: N802 - Qt method name
        """Recheck GIF visibility after the viewport changes size."""
        super().resizeEvent(event)
        self._schedule_visibility_update()

    def _create_animated_images(self) -> dict[str, _AnimatedImage]:
        """Create one movie for each local GIF resource in the document."""
        animated_images: dict[str, _AnimatedImage] = {}

        for fragment, block in _iter_image_fragments(self.document(), return_blocks=True):
            # Images are treated as a kind of special kind of character in the text block
            image_format = fragment.charFormat().toImageFormat()
            resource_url = QUrl(image_format.name())
            local_path = Path(resource_url.toLocalFile()) if resource_url.isLocalFile() else None

            # Skip non-GIF images as we only animate GIFs
            if local_path is None or local_path.suffix.lower() != ".gif":
                continue

            resource_key = resource_url.toString()

            # Create a QMovie for the GIF.
            movie = QMovie(str(local_path), parent=self)
            if not movie.isValid():
                movie.deleteLater()
                continue

            # Store the newly created animated image in the dictionary.
            animated_image = _AnimatedImage(
                movie=movie,
                resource_url=resource_url,
                position=(fragment.position(), fragment.length()),
                block=block,
                is_visible=False,
            )
            animated_images[resource_key] = animated_image

            # Connect the frameChanged signal to update the GIF frame in the document.
            movie.frameChanged.connect(
                lambda _frame_number, key=resource_key: self._replace_gif_frame(key)
            )


        return animated_images

    def _schedule_visibility_update(self, *_args) -> None:
        """
        Schedule visibility checks while the guide is scrolling or resizing.
        
        The start method resets the timer if it is already running, this means the check will wait until 50
        milliseconds after the user finishes scrolling.
        """
        self._visibility_timer.start()

    def _visible_document_rect(self) -> QRectF:
        """Return the portion of the document currently covered by the viewport."""
        return QRectF(
            self.horizontalScrollBar().value(),
            self.verticalScrollBar().value(),
            self.viewport().width(),
            self.viewport().height(),
        )

    def _update_movie_visibility(self) -> None:
        """Start visible GIFs from frame zero and stop offscreen GIFs."""
        visible_rect = self._visible_document_rect()
        document_layout = self.document().documentLayout()

        for animated_image in self._animated_images.values():
            # GIF is visible if it intersects with the visible portion of the document.
            is_visible = visible_rect.intersects(document_layout.blockBoundingRect(animated_image.block))
            animated_image.is_visible = is_visible

        for animated_image in self._animated_images.values():

            # If the GIF is visible and not already running, start it from frame zero.
            if animated_image.is_visible and animated_image.movie.state() != QMovie.Running:
                animated_image.movie.stop()
                animated_image.movie.jumpToFrame(0)
                animated_image.movie.start()
            # If the GIF is not visible and is running, stop it (so it doesn't consume unnecessary resources)
            elif not animated_image.is_visible and animated_image.movie.state() != QMovie.NotRunning:
                animated_image.movie.stop()

        if self._first_update:
            self._first_update = False
            self.document().markContentsDirty(0, self.document().characterCount())

    def _replace_gif_frame(self, resource_key: str) -> None:
        """Replace a GIF resource with its movie's current decoded frame."""
        animated_image = self._animated_images[resource_key]
        document = self.document()
        # Replace the GIF resource with the current frame of its movie.
        document.addResource(
            QTextDocument.ImageResource,
            animated_image.resource_url,
            animated_image.movie.currentImage(),
        )
        # Marking as dirty so that the document knows this portion needs to be repainted.
        document.markContentsDirty(*animated_image.position)

        self.viewport().update()


def show_guide(viewer: Viewer):
    """
    Show the guide to the user in a non-modal QDialog.

    Parameters
    ----------
    viewer : napari.Viewer
        The napari viewer instance.
    """
    global _guide_dialog  # pylint: disable=global-statement

    # If the dialog is already open and visible, bring it to the front
    if _guide_dialog is not None and _guide_dialog.isVisible():
        _guide_dialog.raise_()
        _guide_dialog.activateWindow()
        return

    try:
        guide_sections = _load_guide_sections()
    except FileNotFoundError:
        show_error_dialog("The guide could not be loaded because GUIDE.md was not found.")
        return

    # Use the main napari window as the parent if available
    parent_widget = None
    if hasattr(viewer, "window") and hasattr(viewer.window, "_qt_window"):
        parent_widget = viewer.window._qt_window  # pylint: disable=protected-access

    _guide_dialog = QDialog(parent_widget)
    _guide_dialog.setWindowTitle("TopoStats Guide")
    _guide_dialog.resize(810, 600)

    layout = QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(_AnimatedGuideBrowser(guide_sections))

    _guide_dialog.setLayout(layout)
    _guide_dialog.show()


def check_guide(viewer: Viewer):
    """
    Check the installed plugin version and show the guide if it is the first launch or a new version.

    Parameters
    ----------
    viewer : napari.Viewer
        The napari viewer instance.
    """
    user_settings_path = Path(user_config_dir("TopoStats", "Napari")) / "settings.json"
    user_settings_path.parent.mkdir(parents=True, exist_ok=True)
    # If no plugin settings exist yet, create them with plugin version and show the guide (as first launch)
    if not user_settings_path.exists():
        settings = {"plugin-version": version("napari-topostats")}
        with open(user_settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f)
        show_guide(viewer)
    else:
        # Load existing settings if the settings file exists
        with open(user_settings_path, encoding="utf-8") as f:
            settings = json.load(f)

        # Show the guide if the plugin version has changed, then record new version
        if settings.get("plugin-version") != version("napari-topostats"):
            settings["plugin-version"] = version("napari-topostats")
            with open(user_settings_path, "w", encoding="utf-8") as f:
                json.dump(settings, f)

            show_guide(viewer)
