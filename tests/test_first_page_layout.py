import unittest
from pathlib import Path

import pymupdf
from tempfile import TemporaryDirectory

from reportlab.lib.units import inch

from configured_renderer import LetterSettings
from first_page_layout import FirstPagePdfRenderer


class FirstPageLayoutTests(unittest.TestCase):
    def renderer(self, *, settings: LetterSettings, visible_document_title: str = "", title: str = ""):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        source = root / "letter.md"
        source.write_text("Dear Commission,\n\nBody text.", encoding="utf-8")
        return FirstPagePdfRenderer(
            source,
            root / "letter.pdf",
            settings=settings,
            visible_document_title=visible_document_title,
            title=title or None,
        )

    def test_visible_title_is_separate_from_pdf_metadata_title(self):
        renderer = self.renderer(
            settings=LetterSettings(show_date=False),
            visible_document_title="IN RE FILE NO. SR-OCC-2025-801",
            title="Metadata-only title",
        )
        self.assertEqual(renderer.visible_document_title, "IN RE FILE NO. SR-OCC-2025-801")
        self.assertEqual(renderer.title, "Metadata-only title")

    def test_first_page_header_reserves_space_above_letterhead_row(self):
        renderer = self.renderer(
            settings=LetterSettings(first_page_header="Prior comments incorporated by reference."),
            visible_document_title="IN RE FILE NO. SR-OCC-2025-801",
        )
        self.assertGreaterEqual(renderer.top, 1.95 * inch)

    def test_quote_number_renders_in_top_right(self):
        renderer = self.renderer(
            settings=LetterSettings(show_date=False, quote_number="Q-1042"),
        )
        renderer.build()

        with pymupdf.open(renderer.output) as pdf:
            matches = pdf[0].search_for("Quote # Q-1042")
            self.assertTrue(matches)
            self.assertGreater(matches[0].x0, pdf[0].rect.width / 2)

        self.assertGreaterEqual(renderer.top, 1.55 * inch)


if __name__ == "__main__":
    unittest.main()
