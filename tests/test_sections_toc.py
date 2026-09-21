from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph
from first_page_layout import FirstPagePdfRenderer

from configured_renderer import (
    ConfiguredPdfRenderer,
    LetterSettings,
    format_section_number,
)


class SectionAndTocTests(unittest.TestCase):
    @staticmethod
    def paragraph_texts(story):
        return [flowable.getPlainText() for flowable in story if isinstance(flowable, Paragraph)]

    def test_legal_numbering_reaches_fifth_level(self):
        counts = {2: 1, 3: 2, 4: 3, 5: 1, 6: 1}
        for level, expected in ((2, "I."), (3, "B."), (4, "3."), (5, "a)"), (6, "i)")):
            with self.subTest(level=level):
                self.assertEqual(format_section_number("legal", counts, level), expected)

    def test_decimal_and_unumbered_modes(self):
        counts = {2: 1, 3: 2, 4: 3, 5: 1, 6: 1}
        self.assertEqual(format_section_number("decimal", counts, 6), "1.")
        self.assertEqual(format_section_number("none", counts, 6), "")

    def test_defaults_preserve_existing_behavior(self):
        settings = LetterSettings()
        self.assertEqual(settings.section_numbering, "legal")
        self.assertFalse(settings.include_toc)

    def test_unknown_numbering_style_is_rejected(self):
        with self.assertRaises(ValueError):
            LetterSettings(section_numbering="outline-only")

    def test_outline_metadata_exists_without_visible_toc_or_numbers(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "document.md"
            source.write_text("## First\n\n### Second\n\nText", encoding="utf-8")
            renderer = ConfiguredPdfRenderer(
                source,
                root / "output.pdf",
                settings=LetterSettings(include_toc=False, section_numbering="none"),
            )
            outlines = [
                flowable.outline
                for flowable in renderer.build_story()
                if getattr(flowable, "outline", None)
            ]
            self.assertEqual(outlines, [("First", 0), ("Second", 1)])

    def test_toc_uses_same_numbered_section_labels(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "document.md"
            source.write_text(
                "## One\n### A\n### B\n#### Three\n##### Lower\n###### Roman\n",
                encoding="utf-8",
            )
            renderer = ConfiguredPdfRenderer(
                source,
                root / "output.pdf",
                settings=LetterSettings(include_toc=True, section_numbering="legal"),
            )
            labels = [label for _level, label in renderer._collect_section_entries()]
            self.assertEqual(labels, ["I. One", "A. A", "B. B", "1. Three", "a) Lower", "i) Roman"])
            outlines = [flowable.outline[0] for flowable in renderer.build_story() if getattr(flowable, "outline", None)]
            self.assertEqual(outlines, labels)
            self.assertTrue(renderer._toc_block([2, 2, 2, 3, 3, 3]))

    def test_heading_and_toc_indentation_increases_evenly(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "document.md"
            source.write_text(
                "## First\n### Second\n#### Third\n##### Fourth\n###### Fifth\n## Reset\n",
                encoding="utf-8",
            )
            for renderer_class in (ConfiguredPdfRenderer, FirstPagePdfRenderer):
                with self.subTest(renderer=renderer_class.__name__):
                    renderer = renderer_class(
                        source, root / "output.pdf",
                        settings=LetterSettings(include_toc=True),
                    )
                    headings = [
                        flowable for flowable in renderer.build_story()
                        if getattr(flowable, "outline", None)
                    ]
                    expected = [0, 12, 24, 36, 48, 0]
                    self.assertEqual([heading.style.leftIndent for heading in headings], expected)
                    toc_table = renderer._toc_block()[1]
                    self.assertEqual([row[0].style.leftIndent for row in toc_table._cellvalues], expected)

    def test_toc_marker_enables_toc_at_source_position(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "document.md"
            source.write_text(
                "Intro paragraph.\n\n[[TOC]]\n\n## First\n\nText\n",
                encoding="utf-8",
            )
            renderer = ConfiguredPdfRenderer(
                source,
                root / "output.pdf",
                settings=LetterSettings(include_toc=False, section_numbering="legal"),
            )
            texts = self.paragraph_texts(renderer.build_story(toc_page_numbers=[2]))

            self.assertLess(texts.index("Intro paragraph."), texts.index("Table of Contents"))
            self.assertLess(texts.index("Table of Contents"), texts.index("I. First"))
            self.assertNotIn("[[TOC]]", texts)

    def test_toc_heading_marker_supports_every_heading_level(self):
        expected_style = {
            1: "H1X",
            2: "H2X",
            3: "H3X",
            4: "H4X",
            5: "H4X",
            6: "H4X",
        }
        for level in range(1, 7):
            with self.subTest(level=level), TemporaryDirectory() as temp:
                root = Path(temp)
                source = root / "document.md"
                marker = f"{'#' * level} [TOC]"
                source.write_text(
                    f"Intro paragraph.\n\n{marker}\n\n## First\n\nText\n",
                    encoding="utf-8",
                )
                renderer = ConfiguredPdfRenderer(
                    source,
                    root / "output.pdf",
                    settings=LetterSettings(include_toc=False, section_numbering="legal"),
                )
                story = renderer.build_story(toc_page_numbers=[2])
                texts = self.paragraph_texts(story)
                toc_title = next(
                    flowable
                    for flowable in story
                    if isinstance(flowable, Paragraph)
                    and flowable.getPlainText() == "Table of Contents"
                )

                self.assertLess(texts.index("Intro paragraph."), texts.index("Table of Contents"))
                self.assertLess(texts.index("Table of Contents"), texts.index("I. First"))
                self.assertNotIn("[TOC]", texts)
                self.assertEqual(renderer._collect_section_entries(), [(2, "I. First")])
                self.assertEqual(
                    toc_title.style.fontSize,
                    renderer.styles[expected_style[level]].fontSize,
                )

    def test_toc_marker_overrides_default_toc_position(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "document.md"
            source.write_text(
                "Intro paragraph.\n\n[[TOC]]\n\n## First\n",
                encoding="utf-8",
            )
            renderer = ConfiguredPdfRenderer(
                source,
                root / "output.pdf",
                settings=LetterSettings(include_toc=True, section_numbering="legal"),
            )
            texts = self.paragraph_texts(renderer.build_story(toc_page_numbers=[2]))

            self.assertEqual(texts.count("Table of Contents"), 1)
            self.assertLess(texts.index("Intro paragraph."), texts.index("Table of Contents"))

    def test_toc_marker_inside_fenced_code_stays_literal(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "document.md"
            source.write_text(
                "```text\n[[TOC]]\n# [TOC]\n```\n\n## First\n",
                encoding="utf-8",
            )
            renderer = ConfiguredPdfRenderer(
                source,
                root / "output.pdf",
                settings=LetterSettings(include_toc=False, section_numbering="legal"),
            )
            texts = self.paragraph_texts(renderer.build_story())

            self.assertIn("[[TOC]]", texts)
            self.assertIn("# [TOC]", texts)
            self.assertNotIn("Table of Contents", texts)

    def test_rendered_toc_links_resolve_to_each_section(self):
        for renderer_class in (ConfiguredPdfRenderer, FirstPagePdfRenderer):
            for marker in (False, True):
                with self.subTest(renderer=renderer_class.__name__, marker=marker), TemporaryDirectory() as temp:
                    root = Path(temp)
                    source = root / "document.md"
                    source.write_text(
                        ("Intro.\n\n[[TOC]]\n\n" if marker else "")
                        + "## Repeated title\n\n"
                        + ("Body paragraph with enough text to span pages.\n\n" * 70)
                        + "## Repeated title\n\n"
                        + "### **Details** https://example.com\n\nEnd.\n",
                        encoding="utf-8",
                    )
                    output = root / "output.pdf"
                    renderer = renderer_class(
                        source, output,
                        settings=LetterSettings(include_toc=not marker, section_numbering="none"),
                    )
                    destinations = {}
                    links = []
                    original_bookmark = Canvas.bookmarkPage
                    original_link = Canvas.linkRect

                    def bookmark(canvas, key, *args, **kwargs):
                        destinations[key] = canvas.getPageNumber()
                        return original_bookmark(canvas, key, *args, **kwargs)

                    def link(canvas, contents, destinationname, *args, **kwargs):
                        links.append(destinationname)
                        return original_link(canvas, contents, destinationname, *args, **kwargs)

                    with patch.object(Canvas, "bookmarkPage", bookmark), patch.object(Canvas, "linkRect", link):
                        renderer.build()

                    self.assertGreater(destinations["section-1"], destinations["section-0"])
                    self.assertEqual(destinations["section-2"], destinations["section-1"])
                    for index in range(3):
                        # Each render pass links both the title and page number.
                        self.assertGreaterEqual(links.count(f"section-{index}"), 4)
                    self.assertGreaterEqual(output.read_bytes().count(b"/Subtype /Link"), 6)


if __name__ == "__main__":
    unittest.main()
