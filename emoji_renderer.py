"""Render author-selected, fixed emoji artwork; never use viewer-native emoji fonts."""

from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache, wraps
from hashlib import sha256
from html import escape
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from threading import Lock
from zipfile import BadZipFile, ZipFile

from reportlab.platypus import Paragraph
from emoji_unicode import embed_unicode_emoji, emoji_from_image, emit_unicode_text


ASSETS = Path(__file__).parent / "assets" / "twemoji" / "72x72.zip"
STYLE_PACK_ROOT = Path(__file__).parent / "assets" / "emoji-styles"
EMOJI_STYLES = {
    "twemoji": "Twemoji (bundled)",
    "fluent": "Fluent Emoji",
    "noto": "Noto Emoji",
    "openmoji": "OpenMoji",
    "blobmoji": "Blobmoji",
    "emojitwo": "Emojitwo",
    "mutant-standard": "Mutant Standard",
}
_active_style = ContextVar("pdf_compiler_emoji_style", default=("twemoji", str(ASSETS)))
_asset_lock = Lock()
_PNG = b"\x89PNG\r\n\x1a\n"
_NAME = re.compile(r"(?:emoji_u)?([0-9a-f]{2,6}(?:-[0-9a-f]{2,6})*)\.png\Z")


def _archive(style, pack=None):
    if style not in EMOJI_STYLES:
        raise ValueError(f"Unknown emoji style: {style}")
    if style == "twemoji":
        if pack is not None:
            raise ValueError("Twemoji uses bundled artwork; omit the external pack.")
        path = ASSETS
    else:
        path = Path(pack) if pack is not None else STYLE_PACK_ROOT / style / "72x72.zip"
    if not path.is_file():
        raise ValueError(f"{EMOJI_STYLES[style]} is unavailable: supply its PNG ZIP pack.")
    return str(path)


def _pack_index(archive):
    try:
        with ZipFile(archive) as bundle:
            if len(bundle.infolist()) > 10000:
                raise ValueError("Emoji ZIP contains too many entries.")
            entries = {}
            total = 0
            for info in bundle.infolist():
                name = Path(info.filename).name.lower()
                matched = _NAME.fullmatch(name)
                if not matched:
                    continue
                total += info.file_size
                if info.file_size > 1024 * 1024 or total > 128 * 1024 * 1024:
                    raise ValueError("Emoji ZIP exceeds image size limits.")
                key = "".join(chr(int(part, 16)) for part in matched.group(1).split("-")
                              if int(part, 16) != 0xfe0f)
                if key in entries:
                    raise ValueError(f"Duplicate emoji sequence: {name}")
                entries[key] = info.filename
            if not entries:
                raise ValueError("Emoji ZIP must contain codepoint-named PNG files.")
            return entries
    except (BadZipFile, OSError) as exc:
        raise ValueError("Emoji artwork must be a valid PNG ZIP file.") from exc


def validate_emoji_style(style, pack=None):
    return _pack_index(_archive(style, pack))


@contextmanager
def emoji_style_scope(style="twemoji", pack=None):
    archive = _archive(style, pack)
    _pack_index(archive)
    token = _active_style.set((style, archive))
    try:
        yield
    finally:
        _active_style.reset(token)


def render_with_emoji_style(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with emoji_style_scope(self.emoji_style, self.emoji_pack):
            result = method(self, *args, **kwargs)
            embed_unicode_emoji(self.output)
            return result
    return wrapped


@lru_cache(maxsize=32)
def _emoji_pattern(archive):
    selected = _pack_index(archive)
    reference = selected if archive == str(ASSETS) else _pack_index(str(ASSETS))
    sequences = selected.keys() | reference.keys()
    parts = [
        "".join(re.escape(char) + "\ufe0f?" for char in sequence)
        for sequence in sorted(sequences, key=lambda value: (-len(value), value))
    ]
    return re.compile("|".join(parts)), selected


@lru_cache(maxsize=1)
def _asset_directory():
    return TemporaryDirectory(prefix="pdf-compiler-emoji-")


@lru_cache(maxsize=1024)
def _image_path(archive, filename, original):
    with _asset_lock:
        prefix = sha256(archive.encode()).hexdigest()[:16]
        directory = Path(_asset_directory().name) / prefix
        directory.mkdir(exist_ok=True)
        codepoints = "-".join(f"{ord(char):x}" for char in original)
        path = directory / f"{codepoints}__{Path(filename).name}"
        if not path.exists():
            with ZipFile(archive) as bundle:
                data = bundle.read(filename)
            if not data.startswith(_PNG):
                raise ValueError(f"Invalid PNG emoji artwork: {filename}")
            path.write_bytes(data)
        return escape(str(path), quote=True)


def emoji_preview(style, pack=None):
    archive = _archive(style, pack)
    entries = _pack_index(archive)
    sample = next((entries.get(item) for item in ("😀", "🌐", "👍🏽", "❤️")
                   if entries.get(item)), None)
    if sample is None:
        raise ValueError("This emoji pack lacks a common preview glyph.")
    with ZipFile(archive) as bundle:
        data = bundle.read(sample)
    if not data.startswith(_PNG):
        raise ValueError("Emoji preview must be a PNG.")
    return data


def _dash_markup(text):
    text = text.replace("\u2010", "-").replace("\u2012", "\u2013")
    return re.sub(
        r"\S*\u2011\S*",
        lambda match: "<nobr>" + match.group().replace("\u2011", "-") + "</nobr>",
        text,
    )


def emoji_markup(text, font_size):
    style, archive = _active_style.get()
    pattern, selected = _emoji_pattern(archive)

    def replace(match):
        normalized = match.group().replace("\ufe0f", "")
        filename = selected.get(normalized)
        if filename is None:
            raise ValueError(
                f"{EMOJI_STYLES[style]} does not include emoji {match.group()!r}. "
                "Choose a compatible artwork pack."
            )
        return (
            f'<img src="{_image_path(archive, filename, match.group())}" width="{font_size}" '
            f'height="{font_size}" valign="middle"/>'
        )

    # Do not change markup attributes, link destinations, or anchors.
    return "".join(
        part if index % 2 else pattern.sub(replace, _dash_markup(part))
        for index, part in enumerate(re.split(r"(<[^>]+>)", text))
    )


class EmojiParagraph(Paragraph):
    def __init__(self, text, style=None, bulletText=None, frags=None, **kwargs):
        if text and frags is None:
            text = emoji_markup(text, style.fontSize if style is not None else 10)
        super().__init__(text, style, bulletText=bulletText, frags=frags, **kwargs)

    def beginText(self, *args, **kwargs):
        tx = super().beginText(*args, **kwargs)
        self._emoji_tx = tx
        return tx

    def drawPara(self, *args, **kwargs):
        # ReportLab draws inline images separately from its paragraph text.
        # Insert the exact Unicode sequence into that same text run at the
        # image's position, while retaining the full-color PNG for display.
        canvas = self.canv
        original_draw_image = canvas.drawImage

        def draw_image(image, x, y, *image_args, **image_kwargs):
            result = original_draw_image(image, x, y, *image_args, **image_kwargs)
            sequence = emoji_from_image(image, Path(_asset_directory().name))
            if sequence is not None:
                emit_unicode_text(
                    canvas, self._emoji_tx, sequence,
                    self.style.fontSize, self.style.fontName,
                )
            return result

        canvas.drawImage = draw_image
        try:
            return super().drawPara(*args, **kwargs)
        finally:
            canvas.drawImage = original_draw_image
