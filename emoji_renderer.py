"""Render bundled Twemoji artwork inline without system fonts or network access."""

from functools import lru_cache
from html import escape
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from threading import Lock
from zipfile import ZipFile

from reportlab.platypus import Paragraph


ASSETS = Path(__file__).parent / "assets" / "twemoji" / "72x72.zip"
_asset_lock = Lock()


@lru_cache(maxsize=1)
def _emoji_pattern():
    with ZipFile(ASSETS) as bundle:
        sequences = {
            "".join(chr(int(part, 16)) for part in name[:-4].split("-")).replace("\ufe0f", ""): name
            for name in bundle.namelist()
        }
    # Longest first keeps flags, skin tones, and joined families as one image.
    patterns = []
    for sequence in sorted(sequences, key=lambda value: (-len(value), value)):
        patterns.append("".join(re.escape(char) + "\ufe0f?" for char in sequence))
    return re.compile("|".join(patterns)), sequences


@lru_cache(maxsize=1)
def _asset_directory():
    return TemporaryDirectory(prefix="pdf-compiler-emoji-")


@lru_cache(maxsize=None)
def _image_path(filename):
    with _asset_lock:
        path = Path(_asset_directory().name) / filename
        if not path.exists():
            with ZipFile(ASSETS) as bundle:
                path.write_bytes(bundle.read(filename))
        return escape(str(path), quote=True)


def _dash_markup(text):
    # Standard PDF Times lacks these Unicode hyphens and the figure dash.
    text = text.replace("\u2010", "-").replace("\u2012", "\u2013")
    return re.sub(
        r"\S*\u2011\S*",
        lambda match: "<nobr>" + match.group().replace("\u2011", "-") + "</nobr>",
        text,
    )


def emoji_markup(text, font_size):
    pattern, sequences = _emoji_pattern()

    def replace(match):
        filename = sequences[match.group().replace("\ufe0f", "")]
        return (
            f'<img src="{_image_path(filename)}" width="{font_size}" '
            f'height="{font_size}" valign="middle"/>'
        )

    # Never modify link destinations, anchors, or other markup attributes.
    return "".join(
        part if index % 2 else pattern.sub(replace, _dash_markup(part))
        for index, part in enumerate(re.split(r"(<[^>]+>)", text))
    )


class EmojiParagraph(Paragraph):
    def __init__(self, text, style=None, bulletText=None, frags=None, **kwargs):
        if text and frags is None:
            text = emoji_markup(text, style.fontSize if style is not None else 10)
        super().__init__(text, style, bulletText=bulletText, frags=frags, **kwargs)
