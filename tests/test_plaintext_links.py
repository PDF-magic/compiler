from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from reportlab.platypus import Paragraph

from pdf_compiler import PdfRenderer


class PlaintextLinkTests(unittest.TestCase):
    def make_renderer(self, root: Path) -> PdfRenderer:
        source = root / "source.md"
        source.write_text("## Body\n\nText", encoding="utf-8")
        return PdfRenderer(source, root / "output.pdf")

    @staticmethod
    def link_targets(rendered: str, renderer: PdfRenderer) -> list[str]:
        paragraph = Paragraph(rendered, renderer.styles["BodyX"])
        return [
            target
            for fragment in paragraph.frags
            for _, target in getattr(fragment, "link", [])
        ]

    def test_plaintext_url_becomes_clickable(self):
        with TemporaryDirectory() as temp:
            renderer = self.make_renderer(Path(temp))
            rendered, _ = renderer.markdown_inline("See https://example.com/docs.")

            self.assertEqual(self.link_targets(rendered, renderer), ["https://example.com/docs"])
            self.assertTrue(rendered.endswith("</link>."))

    def test_custom_color_applies_to_web_links(self):
        from reportlab.lib.colors import HexColor
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.md"
            source.write_text("Text", encoding="utf-8")
            renderer = PdfRenderer(source, root / "output.pdf", link_color="#7c3aed")
            rendered, _ = renderer.markdown_inline("https://example.com")
            paragraph = Paragraph(rendered, renderer.styles["BodyX"])
            self.assertTrue(all(f.textColor == HexColor("#7C3AED") for f in paragraph.frags))
            with self.assertRaises(ValueError):
                PdfRenderer(source, root / "output.pdf", link_color="invalid")

    def test_url_keeps_balanced_parentheses(self):
        with TemporaryDirectory() as temp:
            renderer = self.make_renderer(Path(temp))
            url = "https://en.wikipedia.org/wiki/Test_(law)"
            rendered, _ = renderer.markdown_inline(f"See {url}.")

            self.assertEqual(self.link_targets(rendered, renderer), [url])

    def test_underlining_defaults_on_and_can_be_disabled(self):
        with TemporaryDirectory() as temp:
            renderer = self.make_renderer(Path(temp))
            self.assertTrue(renderer.underline_links)
            for enabled in (True, False):
                renderer.underline_links = enabled
                rendered, _ = renderer.markdown_inline("https://example.com")
                paragraph = Paragraph(rendered, renderer.styles["BodyX"])
                self.assertEqual(any(f.us_lines for f in paragraph.frags), enabled)
                self.assertEqual(self.link_targets(rendered, renderer), ["https://example.com"])

    def test_markdown_link_preserves_visible_format_and_clicks_url(self):
        with TemporaryDirectory() as temp:
            renderer = self.make_renderer(Path(temp))
            rendered, _ = renderer.markdown_inline("[SEC rules](https://www.sec.gov/rules).")

            self.assertTrue(rendered.startswith("SEC rules ("))
            self.assertEqual(
                self.link_targets(rendered, renderer),
                ["https://www.sec.gov/rules"],
            )

    def test_query_string_is_preserved_in_link_target(self):
        with TemporaryDirectory() as temp:
            renderer = self.make_renderer(Path(temp))
            url = "https://example.com/search?a=1&b=2"
            rendered, _ = renderer.markdown_inline(f"See {url}!")

            targets = self.link_targets(rendered, renderer)
            self.assertTrue(targets)
            self.assertTrue(all(target == url for target in targets))
            self.assertTrue(rendered.endswith("</link>!"))


if __name__ == "__main__":
    unittest.main()
