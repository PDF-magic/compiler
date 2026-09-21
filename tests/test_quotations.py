from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pymupdf
from reportlab.lib.enums import TA_RIGHT

from pdf_compiler import PdfRenderer
from typography_renderer import TypographyPdfRenderer, TypographySettings


class QuotationTests(unittest.TestCase):
    def _renderer(self, root: Path, text: str, *, typography=None):
        source = root / "source.md"
        source.write_text(text, encoding="utf-8")
        renderer_class = TypographyPdfRenderer if typography else PdfRenderer
        kwargs = {"typography": typography} if typography else {}
        return renderer_class(source, root / "output.pdf", **kwargs)

    def test_quote_and_source_markers_render_as_joined_quotation(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            renderer = self._renderer(
                root,
                "> [!QUOTE]\n> Stay curious.\n> [!SOURCE] Ada Lovelace",
            )
            flowables = renderer.blockquote_flowables(
                ["[!QUOTE]", "Stay curious.", "[!SOURCE] Ada Lovelace"]
            )

            self.assertEqual(len(flowables), 2)
            body, source = flowables
            self.assertEqual(body.getPlainText(), "Stay curious.")
            self.assertEqual(source.getPlainText(), "— Ada Lovelace")
            self.assertEqual(source.style.alignment, TA_RIGHT)
            self.assertFalse(body.style.quoteRoundBottom)
            self.assertFalse(source.style.quoteRoundTop)

    def test_source_supports_inline_markdown_and_footnote_references(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            renderer = self._renderer(
                root,
                "> [!QUOTE]\n> Words.\n> [!SOURCE] *Author*[^bio]\n\n[^bio]: Biography.",
            )
            flowables = renderer.blockquote_flowables(
                ["[!QUOTE]", "Words.", "[!SOURCE] *Author*[^bio]"]
            )

            source = flowables[-1]
            self.assertEqual(source.getPlainText(), "— Author1")
            self.assertEqual(source.footnote_refs, [1])

    def test_source_marker_is_literal_in_an_ordinary_blockquote(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            renderer = self._renderer(
                root,
                "> Ordinary.\n> [!SOURCE] Still ordinary.",
            )
            flowables = renderer.blockquote_flowables(
                ["Ordinary.", "[!SOURCE] Still ordinary."]
            )

            self.assertEqual(len(flowables), 1)
            self.assertIn("[!SOURCE] Still ordinary.", flowables[0].getPlainText())

    def test_quotation_uses_configured_blockquote_styling(self):
        typography = TypographySettings(
            body_font_size=14,
            blockquote_color="#123456",
            blockquote_corner_radius=7,
        )
        with TemporaryDirectory() as temp:
            root = Path(temp)
            renderer = self._renderer(
                root,
                "> [!QUOTE]\n> Words.\n> [!SOURCE] Author",
                typography=typography,
            )

            source_style = renderer.styles["QuotationSourceX"]
            self.assertEqual(source_style.fontSize, 12.6)
            self.assertEqual(source_style.quoteCornerRadius, 7)
            self.assertEqual(source_style.quoteAccent.hexval(), "0x123456")

    def test_web_renderer_supports_sourced_quotations(self):
        from app import app

        response = app.test_client().post(
            "/render",
            data={
                "markdown": "> [!QUOTE]\n> Stay curious.\n> [!SOURCE] Ada",
                "admonitions_enabled": "0",
            },
        )

        self.assertEqual(response.status_code, 200)
        with pymupdf.open(stream=response.data, filetype="pdf") as pdf:
            text = "".join(item[4] for item in pdf[0].get_text("blocks"))
            self.assertIn("— Ada", text)
            self.assertNotIn("[!QUOTE]", text)
            self.assertNotIn("[!SOURCE]", text)

    def test_rendered_source_is_right_aligned_and_markers_are_hidden(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            renderer = self._renderer(
                root,
                "> [!QUOTE]\n> Stay curious.\n> [!SOURCE] Ada",
            )
            renderer.build()

            with pymupdf.open(renderer.output) as pdf:
                page = pdf[0]
                source_matches = page.search_for("— Ada")
                self.assertTrue(source_matches)
                self.assertGreater(source_matches[0].x0, page.rect.width / 2)
                text = "".join(item[4] for item in page.get_text("blocks"))
                self.assertNotIn("[!QUOTE]", text)
                self.assertNotIn("[!SOURCE]", text)


if __name__ == "__main__":
    unittest.main()
