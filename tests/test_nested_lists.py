from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from configured_renderer import ConfiguredPdfRenderer
from pdf_compiler import PdfRenderer, RefParagraph


class NestedListRendererTests(unittest.TestCase):
    def list_items(self, renderer_class, markdown: str):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.md"
            source.write_text(markdown, encoding="utf-8")
            renderer = renderer_class(source, root / "output.pdf")
            return [
                item
                for item in renderer.build_story()
                if isinstance(item, RefParagraph) and item.bulletText
            ]

    def test_source_indentation_progressively_offsets_nested_lists(self):
        markdown = (
            "2. Parent\n"
            "   - Child\n"
            "       - Grandchild\n"
            "3. Sibling\n"
        )

        for renderer_class in (PdfRenderer, ConfiguredPdfRenderer):
            with self.subTest(renderer=renderer_class.__name__):
                items = self.list_items(renderer_class, markdown)
                self.assertEqual(
                    [item.bulletText for item in items],
                    ["2.", "-", "-", "3."],
                )
                self.assertEqual(items[0].style.leftIndent, items[3].style.leftIndent)
                self.assertEqual(items[0].style.bulletIndent, items[3].style.bulletIndent)
                self.assertGreater(items[1].style.leftIndent, items[0].style.leftIndent)
                self.assertGreater(items[2].style.leftIndent, items[1].style.leftIndent)
                self.assertGreater(items[1].style.bulletIndent, items[0].style.bulletIndent)
                self.assertGreater(items[2].style.bulletIndent, items[1].style.bulletIndent)
                self.assertAlmostEqual(
                    items[1].style.leftIndent - items[0].style.leftIndent,
                    items[1].style.bulletIndent - items[0].style.bulletIndent,
                )
                self.assertAlmostEqual(
                    items[2].style.leftIndent - items[0].style.leftIndent,
                    items[2].style.bulletIndent - items[0].style.bulletIndent,
                )

    def test_tab_indentation_expands_to_markdown_columns(self):
        markdown = "- Parent\n\t- Child\n\t\t1. Grandchild\n"

        for renderer_class in (PdfRenderer, ConfiguredPdfRenderer):
            with self.subTest(renderer=renderer_class.__name__):
                items = self.list_items(renderer_class, markdown)
                self.assertEqual(
                    [item.bulletText for item in items],
                    ["-", "-", "1."],
                )
                first_step = items[1].style.leftIndent - items[0].style.leftIndent
                second_step = items[2].style.leftIndent - items[0].style.leftIndent
                self.assertGreater(first_step, 0)
                self.assertAlmostEqual(second_step, first_step * 2)


if __name__ == "__main__":
    unittest.main()
