import unittest
from io import BytesIO
from unittest.mock import patch

from PIL import Image
import pymupdf

from app import LETTERHEAD_PRESETS, app


class LetterheadPresetTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_index_loads_letterhead_preset_ui(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"/static/letterhead-presets.js", response.data)

    def test_whydrs_preset_assets_are_present(self):
        svg = LETTERHEAD_PRESETS["whydrs"]
        self.assertEqual(svg.suffix, ".svg")
        self.assertTrue(svg.exists())

    def test_whydrs_preset_renders_pdf(self):
        response = self.client.post(
            "/render",
            data={"markdown": "# Test\n\nPreset letterhead.", "letterhead_preset": "whydrs"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")
        self.assertTrue(response.data.startswith(b"%PDF-"))
        with pymupdf.open(stream=response.data, filetype="pdf") as pdf:
            self.assertTrue(pdf[0].get_images())

    def test_blocktransfer_preset_asset_is_renderable(self):
        svg = LETTERHEAD_PRESETS["blocktransfer"]
        self.assertEqual(svg.suffix, ".svg")
        self.assertTrue(svg.exists())
        with pymupdf.open(svg) as artwork:
            self.assertGreater(artwork[0].rect.width, artwork[0].rect.height)
            pixmap = artwork[0].get_pixmap(alpha=True)
            self.assertTrue(any(pixmap.samples[3::4]))

    def test_blocktransfer_preset_renders_pdf(self):
        response = self.client.post(
            "/render",
            data={"markdown": "# Test\n\nBlockTransfer letterhead.", "letterhead_preset": "blocktransfer"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")
        with pymupdf.open(stream=response.data, filetype="pdf") as pdf:
            self.assertTrue(pdf[0].get_images())

    def test_custom_upload_overrides_svg_preset(self):
        logo = BytesIO()
        Image.new("RGB", (20, 10), "blue").save(logo, format="PNG")
        logo.seek(0)
        with patch("app.pymupdf.open") as open_svg:
            response = self.client.post(
                "/render",
                data={"markdown": "# Test", "letterhead_preset": "blocktransfer", "logo": (logo, "logo.png")},
            )
        self.assertEqual(response.status_code, 200)
        open_svg.assert_not_called()

    def test_unknown_letterhead_preset_is_rejected(self):
        response = self.client.post(
            "/render",
            data={"markdown": "# Test", "letterhead_preset": "unknown"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Unknown letterhead preset", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
