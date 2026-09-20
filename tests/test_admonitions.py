from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER

from pdf_compiler import PdfRenderer
from typography_renderer import TypographyPdfRenderer, TypographySettings


class AdmonitionTests(unittest.TestCase):
    def _source(self, root: Path, text: str = "> [!NOTE]\n> Body text.") -> Path:
        source = root / "source.md"
        source.write_text(text, encoding="utf-8")
        return source

    def test_github_marker_selects_style_without_printing_category_label(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            renderer = PdfRenderer(self._source(root), root / "output.pdf")
            flowables = renderer.blockquote_flowables(["[!NOTE]", "Body text."])
            self.assertEqual(len(flowables), 1)
            self.assertEqual(flowables[0].getPlainText(), "Body text.")
            self.assertEqual(flowables[0].style.name, "AdmonitionNoteBodyX")

    def test_optional_header_is_centered_bold_and_joins_body(self):
        typography = TypographySettings(
            admonition_headers={"NOTE": "Context"},
            admonition_colors={"NOTE": "#123456"},
            admonition_indents={"NOTE": 30},
        )
        with TemporaryDirectory() as temp:
            root = Path(temp)
            renderer = TypographyPdfRenderer(
                self._source(root),
                root / "output.pdf",
                typography=typography,
            )
            flowables = renderer.blockquote_flowables(["[!NOTE]", "Body text."])
            self.assertEqual(len(flowables), 2)
            header, body = flowables
            self.assertEqual(header.getPlainText(), "Context")
            self.assertEqual(header.style.fontName, "Times-Bold")
            self.assertEqual(header.style.alignment, TA_CENTER)
            self.assertFalse(header.style.quoteRoundBottom)
            self.assertFalse(body.style.quoteRoundTop)
            self.assertEqual(body.style.leftIndent, 30)
            self.assertEqual(
                body.style.quoteAccent,
                colors.HexColor("#123456"),
            )

    def test_categories_can_use_different_indents_and_colors(self):
        typography = TypographySettings(
            admonition_colors={"TIP": "#112233", "WARNING": "#445566"},
            admonition_indents={"TIP": 9, "WARNING": 42},
        )
        with TemporaryDirectory() as temp:
            root = Path(temp)
            renderer = TypographyPdfRenderer(
                self._source(root),
                root / "output.pdf",
                typography=typography,
            )
            self.assertEqual(renderer.styles["AdmonitionTipBodyX"].leftIndent, 9)
            self.assertEqual(renderer.styles["AdmonitionWarningBodyX"].leftIndent, 42)
            self.assertEqual(
                renderer.styles["AdmonitionTipBodyX"].quoteAccent,
                colors.HexColor("#112233"),
            )
            self.assertEqual(
                renderer.styles["AdmonitionWarningBodyX"].quoteAccent,
                colors.HexColor("#445566"),
            )

    def test_disabling_admonitions_preserves_marker_as_quote_text(self):
        typography = TypographySettings(admonitions_enabled=False)
        with TemporaryDirectory() as temp:
            root = Path(temp)
            renderer = TypographyPdfRenderer(
                self._source(root),
                root / "output.pdf",
                typography=typography,
            )
            flowables = renderer.blockquote_flowables(["[!NOTE]", "Body text."])
            self.assertEqual(len(flowables), 1)
            self.assertIn("[!NOTE]", flowables[0].getPlainText())
            self.assertEqual(flowables[0].style.name, "QuoteX")

    def test_admonition_settings_validate_color_and_indent(self):
        with self.assertRaises(ValueError):
            TypographySettings(admonition_colors={"NOTE": "blue"})
        with self.assertRaises(ValueError):
            TypographySettings(admonition_indents={"CAUTION": 145})

    def test_web_form_renders_custom_admonition(self):
        from app import app

        response = app.test_client().post(
            "/render",
            data={
                "markdown": "> [!WARNING]\n> Body text.",
                "admonitions_enabled": "1",
                "admonition_warning_header": "Attention",
                "admonition_warning_color": "#123456",
                "admonition_warning_indent": "36",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.startswith(b"%PDF-"))


if __name__ == "__main__":
    unittest.main()
