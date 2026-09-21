from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from reportlab.pdfgen.canvas import Canvas

from configured_renderer import LetterSettings
from first_page_layout import FirstPagePdfRenderer


class SectionCrossReferenceTests(unittest.TestCase):
    def make_renderer(self, root: Path, markdown: str, *, underline_links: bool = True):
        source = root / "document.md"
        source.write_text(markdown, encoding="utf-8")
        return FirstPagePdfRenderer(
            source,
            root / "output.pdf",
            settings=LetterSettings(show_date=False),
            underline_links=underline_links,
        )

    def test_infra_and_supra_link_full_and_unique_short_references(self):
        markdown = (
            "## First\n"
            "### Alpha\n"
            "#### Point\n\n"
            "Body.\n\n"
            "## Second\n\n"
            "References.\n"
        )
        with TemporaryDirectory() as temp:
            renderer = self.make_renderer(Path(temp), markdown)
            rendered, _ = renderer.markdown_inline(
                "See *supra* § I.A.1., _supra_ § 1., and infra § II."
            )

            self.assertEqual(
                rendered.count('<i>supra</i> <link href="#section-2"'), 2
            )
            self.assertIn('infra <link href="#section-3"', rendered)
            self.assertEqual(rendered.count("<link "), 3)
            self.assertIn("<u>§ I.A.1.</u>", rendered)

    def test_plain_section_reference_without_prefix_stays_unlinked(self):
        with TemporaryDirectory() as temp:
            renderer = self.make_renderer(Path(temp), "## First\n\nBody.\n")
            rendered, _ = renderer.markdown_inline("See § I. directly.")
            self.assertNotIn('href="#section-', rendered)

    def test_ambiguous_short_reference_stays_unlinked(self):
        markdown = (
            "## First\n"
            "### Alpha\n\n"
            "## Second\n"
            "### Alpha\n\n"
            "Body.\n"
        )
        with TemporaryDirectory() as temp:
            renderer = self.make_renderer(Path(temp), markdown)
            rendered, _ = renderer.markdown_inline(
                "See supra § A., supra § I.A., and supra § II.A."
            )

            self.assertEqual(rendered.count("<link "), 2)
            self.assertIn("supra § A.", rendered)
            self.assertIn('href="#section-1"', rendered)
            self.assertIn('href="#section-3"', rendered)

    def test_section_links_respect_underlining_setting(self):
        with TemporaryDirectory() as temp:
            renderer = self.make_renderer(
                Path(temp), "## First\n\nBody.\n", underline_links=False
            )
            rendered, _ = renderer.markdown_inline("*infra* § I.")
            self.assertIn('<i>infra</i> <link href="#section-0"', rendered)
            self.assertNotIn("<u>§ I.</u>", rendered)

    def test_rendered_pdf_cross_reference_resolves_to_section_anchor(self):
        markdown = (
            "## First\n\n"
            "Body.\n\n"
            "## Second\n\n"
            "See *supra* § I.\n"
        )
        with TemporaryDirectory() as temp:
            root = Path(temp)
            renderer = self.make_renderer(root, markdown)
            links = []
            original_link = Canvas.linkRect

            def link(canvas, contents, destinationname, *args, **kwargs):
                links.append(destinationname)
                return original_link(canvas, contents, destinationname, *args, **kwargs)

            with patch.object(Canvas, "linkRect", link):
                renderer.build()

            self.assertIn("section-0", links)
            self.assertIn(b"/Subtype /Link", renderer.output.read_bytes())


if __name__ == "__main__":
    unittest.main()
