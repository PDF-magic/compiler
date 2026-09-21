from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pdf_compiler import PdfRenderer


class FootnoteNumberReferenceTests(unittest.TestCase):
    def renderer_for(self, markdown: str):
        temp = TemporaryDirectory()
        root = Path(temp.name)
        source = root / "document.md"
        source.write_text(markdown, encoding="utf-8")
        renderer = PdfRenderer(source, root / "output.pdf")
        return temp, renderer

    def test_interpolates_assigned_note_number(self):
        temp, renderer = self.renderer_for(
            """First point.[^ref-a]\n\nLater, see note {{ref-a}}.\n\n[^ref-a]: First note.\n"""
        )
        self.addCleanup(temp.cleanup)

        rendered, refs = renderer.markdown_inline("Later, see note {{ref-a}}.")
        self.assertEqual(
            rendered,
            'Later, see note <link href="#footnote-1">1</link>.',
        )
        self.assertEqual(refs, [])

    def test_uses_final_number_after_other_notes(self):
        temp, renderer = self.renderer_for(
            """Alpha.[^ref-a]\nBeta.[^ref-b]\nGamma.[^ref-c]\n\nSee notes {{ref-a}} and {{ref-c}}.\n\n[^ref-a]: A.\n[^ref-b]: B.\n[^ref-c]: C.\n"""
        )
        self.addCleanup(temp.cleanup)

        self.assertEqual(renderer.nums, {"ref-a": 1, "ref-b": 2, "ref-c": 3})
        rendered, _ = renderer.markdown_inline("See notes {{ref-a}} and {{ref-c}}.")
        self.assertEqual(
            rendered,
            'See notes <link href="#footnote-1">1</link> and '
            '<link href="#footnote-3">3</link>.',
        )

    def test_placeholder_can_appear_before_citation(self):
        temp, renderer = self.renderer_for(
            """Later note number: {{ref-b}}.\n\nAlpha.[^ref-a]\nBeta.[^ref-b]\n\n[^ref-a]: A.\n[^ref-b]: B.\n"""
        )
        self.addCleanup(temp.cleanup)

        rendered, _ = renderer.markdown_inline("Later note number: {{ref-b}}.")
        self.assertEqual(
            rendered,
            'Later note number: <link href="#footnote-2">2</link>.',
        )

    def test_repeated_citation_keeps_one_number(self):
        temp, renderer = self.renderer_for(
            """Alpha.[^ref-a]\nAgain.[^ref-a]\n\nSee note {{ref-a}}.\n\n[^ref-a]: A.\n"""
        )
        self.addCleanup(temp.cleanup)

        self.assertEqual(renderer.order, ["ref-a"])
        self.assertEqual(renderer.nums["ref-a"], 1)

    def test_footnote_citation_is_clickable(self):
        temp, renderer = self.renderer_for(
            """Alpha.[^ref-a]\n\n[^ref-a]: A.\n"""
        )
        self.addCleanup(temp.cleanup)

        rendered, refs = renderer.markdown_inline("Alpha.[^ref-a]")
        self.assertEqual(
            rendered,
            'Alpha.<link href="#footnote-1"><super>1</super></link>',
        )
        self.assertEqual(refs, [1])

    def test_builds_pdf_with_internal_note_destinations(self):
        temp, renderer = self.renderer_for(
            """Alpha.[^ref-a]\n\n_See supra note_ {{ref-a}}.\n\n[^ref-a]: A.\n"""
        )
        self.addCleanup(temp.cleanup)

        pages, footnotes, continuations = renderer.build()

        self.assertGreaterEqual(pages, 1)
        self.assertEqual(footnotes, 1)
        self.assertEqual(continuations, 0)
        self.assertTrue(renderer.output.exists())
        self.assertGreater(renderer.output.stat().st_size, 0)

    def test_unresolved_placeholder_is_left_visible(self):
        temp, renderer = self.renderer_for("No footnotes.\n")
        self.addCleanup(temp.cleanup)

        rendered, _ = renderer.markdown_inline("See note {{missing}}.")
        self.assertEqual(rendered, "See note {{missing}}.")


if __name__ == "__main__":
    unittest.main()
