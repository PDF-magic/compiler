from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from typography_renderer import TypographyPdfRenderer, TypographySettings


class TypographyRendererTests(unittest.TestCase):
    def _renderer(self, root: Path, typography: TypographySettings | None = None):
        source = root / "source.md"
        source.write_text("## Heading\n\nBody text.\n\n[^1]: Footnote text.", encoding="utf-8")
        return TypographyPdfRenderer(
            source,
            root / "output.pdf",
            typography=typography,
        )

    def test_default_body_is_twelve_point_with_1_3_spacing(self):
        with TemporaryDirectory() as temp:
            renderer = self._renderer(Path(temp))
            self.assertEqual(renderer.typography.body_font_size, 12.0)
            self.assertEqual(renderer.typography.line_spacing, 1.3)
            self.assertEqual(renderer.styles["BodyX"].fontSize, 12.0)
            self.assertAlmostEqual(renderer.styles["BodyX"].leading, 15.6)
            self.assertEqual(renderer.styles["ListX"].fontSize, 12.0)
            self.assertAlmostEqual(renderer.styles["QuoteX"].leading, 15.6)

    def test_font_sizes_and_spacing_are_customizable(self):
        typography = TypographySettings(
            body_font_size=10.5,
            line_spacing=1.5,
            h1_font_size=18.0,
            h2_font_size=15.0,
            h3_font_size=13.0,
            h4_font_size=12.0,
            footnote_font_size=9.0,
        )
        with TemporaryDirectory() as temp:
            renderer = self._renderer(Path(temp), typography)
            self.assertEqual(renderer.styles["BodyX"].fontSize, 10.5)
            self.assertAlmostEqual(renderer.styles["BodyX"].leading, 15.75)
            self.assertEqual(renderer.styles["H1X"].fontSize, 18.0)
            self.assertEqual(renderer.styles["H2X"].fontSize, 15.0)
            self.assertEqual(renderer.styles["H3X"].fontSize, 13.0)
            self.assertEqual(renderer.styles["H4X"].fontSize, 12.0)
            self.assertEqual(renderer.styles["FootX"].fontSize, 9.0)

    def test_toc_marker_renders_with_typography(self):
        from app import app
        response = app.test_client().post("/render", data={
            "markdown": "Intro.\n\n[[TOC]]\n\n## Heading\n\nBody.",
            "toc_title_font_size": "18",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.startswith(b"%PDF-"))

    def test_heading_toc_marker_renders_with_typography(self):
        from app import app
        response = app.test_client().post("/render", data={
            "markdown": "Intro.\n\n### [TOC]\n\n## Heading\n\nBody.",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.startswith(b"%PDF-"))

    def test_typography_ranges_are_validated(self):
        with self.assertRaises(ValueError):
            TypographySettings(body_font_size=5.9)
        with self.assertRaises(ValueError):
            TypographySettings(line_spacing=3.1)


if __name__ == "__main__":
    unittest.main()
