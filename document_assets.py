"""Restrict browser document assets to safe local raster images."""

from pathlib import Path, PurePosixPath
import re

from PIL import Image as PILImage

IMAGE_FORMATS = {
    ".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG",
    ".gif": "GIF", ".webp": "WEBP", ".bmp": "BMP",
    ".tif": "TIFF", ".tiff": "TIFF",
}
MARKDOWN_SUFFIXES = {".md", ".markdown"}
MAX_ASSETS = 100
MAX_IMAGE_PIXELS = 20_000_000


def safe_upload_path(filename: str) -> Path:
    """Reject traversal, markup characters and ambiguous upload paths."""
    if not filename or len(filename) > 400 or "\\" in filename or "\x00" in filename:
        raise ValueError("Invalid document upload filename.")
    parts = filename.split("/")
    if (
        len(parts) > 16
        or any(part in {"", ".", ".."} or len(part) > 128 for part in parts)
        or any(not re.fullmatch(r"[A-Za-z0-9._ -]+", part) for part in parts)
    ):
        raise ValueError("Unsafe document upload filename or path.")
    return Path(*parts)


def document_in_folder(uploads):
    """Find one Markdown source and refuse executable files in folder uploads."""
    document = None
    seen = set()
    for upload in uploads:
        if not upload.filename:
            continue
        path = safe_upload_path(upload.filename)
        if any(part.startswith(".") for part in path.parts):
            continue
        key = str(path).casefold()
        if key in seen:
            raise ValueError("Document folder contains duplicate file paths.")
        seen.add(key)
        if path.suffix.lower() in MARKDOWN_SUFFIXES:
            if document is not None:
                raise ValueError("Choose a folder with only one Markdown document.")
            document = upload
        elif path.suffix.lower() not in IMAGE_FORMATS:
            raise ValueError("Document folders can contain only Markdown and raster images (no scripts, HTML or SVG).")
    if len(seen) > MAX_ASSETS + 1:
        raise ValueError("Document folder contains too many files (maximum 101).")
    return document


def validate_image(upload, path: Path) -> None:
    expected_format = IMAGE_FORMATS.get(path.suffix.lower())
    if not expected_format:
        raise ValueError("Only PNG, JPEG, GIF, WebP, BMP and TIFF images are supported (not SVG).")
    try:
        with PILImage.open(upload.stream) as image:
            if image.format != expected_format or image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValueError("Image format does not match its extension, or image dimensions are too large.")
            image.verify()
    except (OSError, PILImage.DecompressionBombError) as exc:
        raise ValueError("Image upload is not a valid raster image.") from exc
    finally:
        upload.stream.seek(0)


def save_document_images(folder_uploads, inline_uploads, root: Path, source: Path) -> None:
    """Stage verified raster assets without extracting or executing uploaded files."""
    staged = []
    seen = {str(source.relative_to(root)).casefold()}
    for upload in folder_uploads:
        if not upload.filename:
            continue
        path = safe_upload_path(upload.filename)
        if any(part.startswith(".") for part in path.parts):
            continue
        if path.suffix.lower() in MARKDOWN_SUFFIXES:
            continue
        if path.suffix.lower() not in IMAGE_FORMATS:
            raise ValueError("Unsupported file in document folder; scripts, HTML and SVG are not allowed.")
        staged.append((upload, path))
    for upload in inline_uploads:
        if not upload.filename:
            continue
        filename = safe_upload_path(upload.filename)
        if len(filename.parts) != 1:
            raise ValueError("Individual image uploads must use a filename, not a directory path.")
        staged.append((upload, source.relative_to(root).parent / filename))
    if len(staged) > MAX_ASSETS:
        raise ValueError("Too many document images (maximum 100).")
    for upload, relative in staged:
        key = str(relative).casefold()
        if key in seen:
            raise ValueError("Duplicate image filename: " + str(relative))
        seen.add(key)
        validate_image(upload, relative)
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        upload.save(destination)


def resolve_document_image(source: Path, reference: str, allowed_root: Path | None = None) -> Path:
    """Keep Markdown image references inside the selected document root."""
    if not reference or "\\" in reference or "\x00" in reference:
        raise ValueError("Invalid Markdown image reference.")
    relative = PurePosixPath(reference)
    if relative.is_absolute() or any(part.startswith(".") and part not in {".", ".."} for part in relative.parts):
        raise ValueError("Markdown image references must stay inside the document folder.")
    if relative.suffix.lower() not in IMAGE_FORMATS:
        raise ValueError("Markdown images must refer to supported raster image files.")
    root = (allowed_root or source.parent).resolve()
    source_dir = source.parent.resolve()
    if not source_dir.is_relative_to(root):
        raise ValueError("Markdown source is outside the allowed document root.")
    image = (source_dir / Path(*relative.parts)).resolve()
    if not image.is_relative_to(root):
        raise ValueError("Markdown image reference escapes the document folder.")
    return image
