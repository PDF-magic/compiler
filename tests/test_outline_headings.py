from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pymupdf

from configured_renderer import ConfiguredPdfRenderer
from first_page_layout import FirstPagePdfRenderer
from pdf_compiler import PdfRenderer


class OutlineHeadingTests(unittest.TestCase):
    def test_skipped_heading_levels_generate_valid_nested_bookmarks(self):
        headings = [
            ("###", "Starting without parent"),
            ("#####", "Deep child"),
            ("####", "Intermediate sibling"),
            ("##", "New root"),
            ("####", "Skipped child"),
            ("###", "Sibling of skipped child"),
            ("######", "Deeper child"),
            ("##", "Final root"),
            ("###", "Contiguous child"),
        ]
        expected_depths = [1, 2, 2, 1, 2, 2, 3, 1, 2]

        for renderer_class in (PdfRenderer, ConfiguredPdfRenderer, FirstPagePdfRenderer):
            with self.subTest(renderer=renderer_class.__name__), TemporaryDirectory() as temp:
                root = Path(temp)
                source = root / "document.md"
                source.write_text(
                    "\n\n".join(f"{marker} {title}" for marker, title in headings) + "\n",
                    encoding="utf-8",
                )
                output = root / "output.pdf"
                renderer_class(source, output).build()

                with pymupdf.open(output) as pdf:
                    outlines = pdf.get_toc()
                    self.assertEqual([entry[0] for entry in outlines], expected_depths)
                    self.assertEqual(len(outlines), len(headings))
                    for entry, (_, title) in zip(outlines, headings):
                        self.assertTrue(entry[1].endswith(title), entry)


if __name__ == "__main__":
    unittest.main()
