"""Regression tests for embedded Markdown image sizing and pagination."""

import tempfile
import unittest
from pathlib import Path

import fitz
from PIL import Image as PILImage
from reportlab.lib.units import inch
from reportlab.platypus import Image as PdfImage

from configured_renderer import ConfiguredPdfRenderer
from pdf_compiler import PdfRenderer


class MarkdownImageLayoutTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / "document.md"
        self.source.write_text("A sample document.", encoding="utf-8")
        self.output = self.root / "document.pdf"

    def make_image(self, name, size):
        image_path = self.root / name
        PILImage.new("RGB", size, "white").save(image_path)
        return image_path

    def test_portrait_uses_available_body_height(self):
        path = self.make_image("portrait.png", (1200, 1800))
        renderer = PdfRenderer(self.source, self.output)
        flowable = renderer.markdown_image(path)

        self.assertGreater(flowable.drawHeight, 5 * inch)
        self.assertLess(flowable.drawHeight, 6.5 * inch)
        self.assertAlmostEqual(flowable.drawWidth / flowable.drawHeight, 2 / 3)
        self.assertEqual(flowable.spaceAfter, 8)

    def test_landscape_keeps_width_limit_and_small_images_are_not_upscaled(self):
        wide = self.make_image("wide.png", (2400, 600))
        small = self.make_image("small.png", (30, 60))
        renderer = PdfRenderer(self.source, self.output)

        landscape = renderer.markdown_image(wide)
        tiny = renderer.markdown_image(small)
        self.assertAlmostEqual(landscape.drawWidth, 6.45 * inch)
        self.assertAlmostEqual(landscape.drawHeight, 6.45 * inch / 4)
        self.assertEqual((tiny.drawWidth, tiny.drawHeight), (30, 60))

    def test_custom_page_margins_reduce_image_height(self):
        portrait = self.make_image("portrait.png", (1200, 1800))
        renderer = ConfiguredPdfRenderer(self.source, self.output)
        renderer.top = 2 * inch
        renderer.bottom = 4 * inch

        image = renderer.markdown_image(portrait)
        usable_height = renderer.page_height - renderer.top - renderer.bottom - 21
        self.assertAlmostEqual(image.drawHeight, usable_height)

    def test_both_renderers_paginate_tall_images_inside_margins(self):
        self.make_image("portrait.png", (1200, 1800))
        self.source.write_text(
            "Opening text. " + "Extra content. " * 300 +
            "\n\n![Portrait](portrait.png)\n\n"
            "Text between images.\n\n"
            "![Portrait](portrait.png)\n\nClosing text.\n",
            encoding="utf-8",
        )

        for renderer_type in (PdfRenderer, ConfiguredPdfRenderer):
            with self.subTest(renderer=renderer_type.__name__):
                output = self.root / f"{renderer_type.__name__}.pdf"
                renderer = renderer_type(self.source, output)
                story_images = [
                    flowable for flowable in renderer.build_story()
                    if isinstance(flowable, PdfImage)
                ]
                self.assertEqual(len(story_images), 2)
                self.assertGreater(story_images[0].drawHeight, 5 * inch)
                pages, _, _ = renderer.build()
                self.assertGreaterEqual(pages, 2)

                found_images = 0
                with fitz.open(output) as document:
                    for page in document:
                        for embedded in page.get_images(full=True):
                            for bounds in page.get_image_rects(embedded[0]):
                                found_images += 1
                                self.assertGreaterEqual(
                                    bounds.x0, renderer.left - 0.1
                                )
                                self.assertLessEqual(
                                    bounds.x1, renderer.page_width - renderer.right + 0.1
                                )
                                self.assertGreaterEqual(
                                    bounds.y0, renderer.top - 0.1
                                )
                                self.assertLessEqual(
                                    bounds.y1, renderer.page_height - renderer.bottom + 0.1
                                )
                self.assertEqual(found_images, 2)


if __name__ == "__main__":
    unittest.main()
