from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from configured_renderer import ConfiguredPdfRenderer, LetterSettings


class EndnotePlacementTests(unittest.TestCase):
    def renderer_for(self, markdown: str, placement: str):
        temp = TemporaryDirectory()
        root = Path(temp.name)
        source = root / "document.md"
        source.write_text(markdown, encoding="utf-8")
        renderer = ConfiguredPdfRenderer(
            source,
            root / "output.pdf",
            settings=LetterSettings(
                show_date=False,
                footnote_placement=placement,
            ),
        )
        self.addCleanup(temp.cleanup)
        return renderer

    def test_end_document_collects_all_notes_in_global_order(self):
        renderer = self.renderer_for(
            "Alpha.[^a]\n\nBeta.[^b]\n\n[^a]: First.\n[^b]: Second.\n",
            "end_document",
        )

        self.assertEqual(renderer._endnote_groups(), [(None, [1, 2])])
        self.assertLess(renderer.bottom, renderer.foot_top)

    def test_end_h1_groups_notes_by_first_citation_section(self):
        renderer = self.renderer_for(
            "# Alpha\nFirst.[^a]\n\n# Beta\nSecond.[^b] Again.[^a]\n\n"
            "[^a]: First note.\n[^b]: Second note.\n",
            "end_h1",
        )

        self.assertEqual(
            renderer._endnote_groups(),
            [("Alpha", [1]), ("Beta", [2])],
        )

    def test_endnotes_render_in_document_flow_without_continuation_pages(self):
        renderer = self.renderer_for(
            "Alpha.[^a]\n\n[^a]: First note.\n",
            "end_document",
        )

        pages, footnotes, continuations = renderer.build()

        self.assertGreaterEqual(pages, 2)
        self.assertEqual(footnotes, 1)
        self.assertEqual(continuations, 0)
        self.assertTrue(renderer.output.exists())
        self.assertGreater(renderer.output.stat().st_size, 0)

    def test_rejects_unknown_footnote_placement(self):
        with self.assertRaisesRegex(ValueError, "Unknown footnote placement"):
            LetterSettings(footnote_placement="somewhere")


if __name__ == "__main__":
    unittest.main()
