from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image, ImageDraw

from signature_layout import (
    DEFAULT_HEIGHT,
    DEFAULT_LINE_WIDTH,
    MAX_LINE_WIDTH,
    MIN_LINE_WIDTH,
    create_signature_asset,
)


class SignatureLayoutTests(unittest.TestCase):
    def make_signature(self, path: Path, size: tuple[int, int]) -> None:
        image = Image.new("RGBA", size, "white")
        draw = ImageDraw.Draw(image)
        draw.line(
            (max(1, size[0] // 10), size[1] * 3 // 4, size[0] * 9 // 10, size[1] // 4),
            fill="black",
            width=max(1, size[1] // 12),
        )
        image.save(path)

    def test_blank_signature_uses_compact_default_line(self):
        asset = create_signature_asset(None)
        try:
            with Image.open(asset) as generated:
                self.assertEqual(generated.size, (DEFAULT_LINE_WIDTH, DEFAULT_HEIGHT))
        finally:
            asset.unlink(missing_ok=True)

    def test_line_width_tracks_rendered_signature_width_with_bounds(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            narrow = root / "narrow.png"
            wide = root / "wide.png"
            self.make_signature(narrow, (120, 120))
            self.make_signature(wide, (900, 120))

            narrow_asset = create_signature_asset(narrow)
            wide_asset = create_signature_asset(wide)
            try:
                with Image.open(narrow_asset) as narrow_rendered:
                    narrow_width = narrow_rendered.width
                with Image.open(wide_asset) as wide_rendered:
                    wide_width = wide_rendered.width

                self.assertGreaterEqual(narrow_width, MIN_LINE_WIDTH)
                self.assertGreater(wide_width, narrow_width)
                self.assertLessEqual(wide_width, MAX_LINE_WIDTH)
            finally:
                narrow_asset.unlink(missing_ok=True)
                wide_asset.unlink(missing_ok=True)

    def test_low_resolution_scan_is_normalized_without_page_sprawl(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            scan = root / "low-res.png"
            self.make_signature(scan, (24, 8))

            asset = create_signature_asset(scan)
            try:
                with Image.open(asset) as generated:
                    self.assertLessEqual(generated.width, MAX_LINE_WIDTH)
                    self.assertLessEqual(generated.height, 60)
                    self.assertIsNotNone(generated.getchannel("A").getbbox())
            finally:
                asset.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
