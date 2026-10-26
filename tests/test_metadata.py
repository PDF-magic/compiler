from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import os
import unittest

import pymupdf

from configured_renderer import ConfiguredPdfRenderer
from pdf_compiler import PdfRenderer, compiler_creator


class RecordingCanvas:
    def __init__(self):
        self.values = {}

    def setTitle(self, value):
        self.values["title"] = value

    def setAuthor(self, value):
        self.values["author"] = value

    def setCreator(self, value):
        self.values["creator"] = value

    def setSubject(self, value):
        self.values["subject"] = value

    def setKeywords(self, value):
        self.values["keywords"] = value


class MetadataTests(unittest.TestCase):
    def test_configured_metadata_is_applied(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "filing.md"
            source.write_text("## Body\n\nText", encoding="utf-8")
            renderer = ConfiguredPdfRenderer(
                source,
                root / "output.pdf",
                title="Transfer Agent Comment Letter",
                author="BlockTransfer",
                subject="SEC transfer agent rulemaking",
                keywords="transfer agents, SEC, comment letter",
            )
            canvas = RecordingCanvas()
            renderer.apply_metadata(canvas)

            self.assertEqual(canvas.values["title"], "Transfer Agent Comment Letter")
            self.assertEqual(canvas.values["author"], "BlockTransfer")
            self.assertTrue(canvas.values["creator"].startswith("PDF Magic Compiler"))
            self.assertEqual(canvas.values["subject"], "SEC transfer agent rulemaking")
            self.assertEqual(canvas.values["keywords"], "transfer agents, SEC, comment letter")


    def test_runtime_commit_is_used_for_software_attribution(self):
        with patch.dict(os.environ, {"PDF_MAGIC_COMPILER_COMMIT_SHA": "ABCDEF1234567890ABCDEF1234567890ABCDEF12"}):
            compiler_creator.cache_clear()
            try:
                self.assertEqual(compiler_creator(), "PDF Magic Compiler (abcdef1)")
            finally:
                compiler_creator.cache_clear()

    def test_both_renderers_write_running_commit_to_pdf_creator(self):
        sha = "1a2b3c4d5e6f78901234567890abcdef12345678"
        with TemporaryDirectory() as temp, patch.dict(os.environ, {"PDF_MAGIC_COMPILER_COMMIT_SHA": sha}):
            compiler_creator.cache_clear()
            try:
                root = Path(temp)
                source = root / "letter.md"
                source.write_text("## Heading\n\nTest paragraph.", encoding="utf-8")
                for renderer_type in (PdfRenderer, ConfiguredPdfRenderer):
                    with self.subTest(renderer=renderer_type.__name__):
                        output = root / f"{renderer_type.__name__}.pdf"
                        renderer_type(source, output, author="Document Author").build()
                        with pymupdf.open(output) as pdf:
                            self.assertEqual(pdf.metadata["author"], "Document Author")
                            self.assertEqual(pdf.metadata["creator"], "PDF Magic Compiler (1a2b3c4)")
            finally:
                compiler_creator.cache_clear()

    def test_title_defaults_to_source_stem(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "filing.md"
            source.write_text("## Body\n\nText", encoding="utf-8")
            renderer = ConfiguredPdfRenderer(source, root / "output.pdf")
            self.assertEqual(renderer.title, "filing")


if __name__ == "__main__":
    unittest.main()
