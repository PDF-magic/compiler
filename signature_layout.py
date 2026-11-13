"""Signature image normalization for the PDF compiler."""

from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

from PIL import Image as PILImage
from PIL import ImageChops, ImageDraw, ImageOps


TARGET_SIGNATURE_HEIGHT = 38
MAX_SIGNATURE_WIDTH = 180
MIN_LINE_WIDTH = 110
MAX_LINE_WIDTH = 196
LINE_SIDE_PADDING = 8
TOP_PADDING = 3
BASELINE_GAP = 3
BOTTOM_PADDING = 8
DEFAULT_LINE_WIDTH = 132
DEFAULT_HEIGHT = 50
DEFAULT_LINE_Y = 40


def create_signature_asset(signature_path: Path | None) -> Path:
    """Create a compact signature-over-line PNG with responsive line sizing."""
    signature = None

    if signature_path:
        signature = PILImage.open(signature_path).convert("RGBA")
        original_alpha = signature.getchannel("A")
        white = PILImage.new("RGBA", signature.size, "white")
        white.paste(signature, mask=original_alpha)
        diff = ImageChops.difference(
            white.convert("RGB"),
            PILImage.new("RGB", signature.size, "white"),
        )
        ink_alpha = ImageOps.grayscale(diff).point(
            lambda value: 0 if value < 8 else min(255, value * 4)
        )
        signature.putalpha(ImageChops.multiply(original_alpha, ink_alpha))
        bbox = signature.getchannel("A").getbbox()
        if bbox:
            signature = signature.crop(bbox)
            scale = min(
                TARGET_SIGNATURE_HEIGHT / signature.height,
                MAX_SIGNATURE_WIDTH / signature.width,
            )
            target_width = max(1, round(signature.width * scale))
            target_height = max(1, round(signature.height * scale))
            signature = signature.resize(
                (target_width, target_height),
                PILImage.Resampling.LANCZOS,
            )
        else:
            signature = None

    if signature:
        width = max(
            MIN_LINE_WIDTH,
            min(MAX_LINE_WIDTH, signature.width + (2 * LINE_SIDE_PADDING)),
        )
        line_y = TOP_PADDING + signature.height + BASELINE_GAP
        height = line_y + BOTTOM_PADDING
    else:
        width = DEFAULT_LINE_WIDTH
        height = DEFAULT_HEIGHT
        line_y = DEFAULT_LINE_Y

    canvas = PILImage.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(canvas)
    draw.line((2, line_y, width - 2, line_y), fill=(24, 24, 24, 230), width=1)

    if signature:
        x = max(2, (width - signature.width) // 2)
        canvas.alpha_composite(signature, (x, TOP_PADDING))

    with NamedTemporaryFile(prefix="pdf-compiler-signature-", suffix=".png", delete=False) as temp:
        asset = Path(temp.name)
    canvas.save(asset, format="PNG")
    return asset
