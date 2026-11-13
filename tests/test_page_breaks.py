import tempfile
import unittest
from pathlib import Path

from reportlab.platypus import PageBreak

from configured_renderer import ConfiguredPdfRenderer
from pdf_compiler import PdfRenderer


class PageBreakTests(unittest.TestCase):
    def story(self, renderer_class, markdown):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "document.md"
            source.write_text(markdown, encoding="utf-8")
            return renderer_class(source, source.with_suffix(".pdf")).build_story()

    def test_explicit_page_break_variants_are_rendered(self):
        markers = (
            "[[pagebreak]]",
            "[[page break]]",
            "[[page-break]]",
            r"\pagebreak",
            r"\newpage",
            "<!-- pagebreak -->",
            "<!-- page break -->",
            '<div class="page-break"></div>',
            '<div style="page-break-after: always;"></div>',
            '<p style="page-break-before: always"></p>',
            '<div style="break-after: page"></div>',
            '<div style="break-before: page"></div>',
        )

        for renderer_class in (PdfRenderer, ConfiguredPdfRenderer):
            for marker in markers:
                with self.subTest(renderer=renderer_class.__name__, marker=marker):
                    story = self.story(renderer_class, f"Before\n{marker}\nAfter")
                    breaks = [index for index, item in enumerate(story) if isinstance(item, PageBreak)]
                    self.assertEqual(len(breaks), 1)
                    before = [getattr(item, "text", "") for item in story[: breaks[0]]]
                    after = [getattr(item, "text", "") for item in story[breaks[0] + 1 :]]
                    self.assertIn("Before", before)
                    self.assertIn("After", after)

    def test_page_break_directives_inside_fenced_code_remain_literal(self):
        markdown = "```\n[[pagebreak]]\n\\newpage\n<!-- pagebreak -->\n```"
        for renderer_class in (PdfRenderer, ConfiguredPdfRenderer):
            with self.subTest(renderer=renderer_class.__name__):
                story = self.story(renderer_class, markdown)
                self.assertFalse(any(isinstance(item, PageBreak) for item in story))

    def test_inline_page_break_text_does_not_force_a_new_page(self):
        markdown = "This sentence mentions [[pagebreak]] without making it a directive."
        for renderer_class in (PdfRenderer, ConfiguredPdfRenderer):
            with self.subTest(renderer=renderer_class.__name__):
                story = self.story(renderer_class, markdown)
                self.assertFalse(any(isinstance(item, PageBreak) for item in story))


if __name__ == "__main__":
    unittest.main()
