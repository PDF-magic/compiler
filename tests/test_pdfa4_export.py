"""Regression tests for opt-in, fail-closed PDF/A-4 export."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from unittest import mock
import shutil
import sys
import unittest

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from pdfa4_export import _embedded_fonts, _validate_pdfa4, render_pdf


class StubRenderer:
    def __init__(self, path):
        self.output = path

    def build(self):
        self.output.write_bytes(b"ordinary-output")
        return 1, 0, 0


class Pdfa4ExportTests(unittest.TestCase):
    def test_embedded_fonts_restore_process_globals(self):
        old = {name: pdfmetrics.getFont(name) for name in
               ("Helvetica", "Times-Roman", "Times-Bold", "Times-Italic")}
        with _embedded_fonts():
            for name in old:
                self.assertIsInstance(pdfmetrics.getFont(name), TTFont)
        for name, previous in old.items():
            self.assertIs(pdfmetrics.getFont(name), previous)

    def test_standard_pdf_does_not_require_archival_dependencies(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "document.pdf"
            renderer = StubRenderer(output)
            with mock.patch("pdfa4_export.shutil.which", return_value=None):
                self.assertEqual(render_pdf(renderer), (1, 0, 0))
            self.assertEqual(output.read_bytes(), b"ordinary-output")

    def test_missing_verapdf_does_not_write_output(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "document.pdf"
            renderer = StubRenderer(output)
            with mock.patch("pdfa4_export.shutil.which", return_value=None):
                with self.assertRaisesRegex(RuntimeError, "veraPDF"):
                    render_pdf(renderer, pdfa4=True)
            self.assertFalse(output.exists())
            self.assertEqual(renderer.output, output)

    def test_validation_failure_retains_existing_pdf_and_path(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "document.pdf"
            output.write_bytes(b"previous-good-file")
            renderer = StubRenderer(output)
            fake_pikepdf = ModuleType("pikepdf")
            with mock.patch.dict(sys.modules, {"pikepdf": fake_pikepdf}), \
                 mock.patch("pdfa4_export._to_pdfa4",
                            side_effect=lambda source, target: shutil.copyfile(source, target)), \
                 mock.patch("pdfa4_export._validate_pdfa4", side_effect=RuntimeError("not compliant")):
                with self.assertRaisesRegex(RuntimeError, "not compliant"):
                    render_pdf(renderer, pdfa4=True, validator="verapdf")
            self.assertEqual(output.read_bytes(), b"previous-good-file")
            self.assertEqual(renderer.output, output)
            self.assertFalse(list(Path(directory).glob(".pdfa4-*")))

    def test_validated_export_atomically_installed(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "document.pdf"
            renderer = StubRenderer(output)
            fake_pikepdf = ModuleType("pikepdf")
            with mock.patch.dict(sys.modules, {"pikepdf": fake_pikepdf}), \
                 mock.patch("pdfa4_export._to_pdfa4",
                            side_effect=lambda source, target: target.write_bytes(b"validated-archival")), \
                 mock.patch("pdfa4_export._validate_pdfa4") as validate:
                self.assertEqual(render_pdf(renderer, pdfa4=True, validator="verapdf"), (1, 0, 0))
            validate.assert_called_once()
            self.assertEqual(output.read_bytes(), b"validated-archival")
            self.assertEqual(renderer.output, output)

    def test_verapdf_requires_explicit_compliant_report(self):
        compliant = '<report><validationReport isCompliant="true"/></report>'
        noncompliant = '<report><validationReport isCompliant="false"/></report>'
        with mock.patch("pdfa4_export.subprocess.run",
                        return_value=SimpleNamespace(returncode=0, stdout=compliant, stderr="")):
            _validate_pdfa4(Path("file.pdf"), "verapdf")
        with mock.patch("pdfa4_export.subprocess.run",
                        return_value=SimpleNamespace(returncode=0, stdout=noncompliant, stderr="")):
            with self.assertRaisesRegex(RuntimeError, "validation failed"):
                _validate_pdfa4(Path("file.pdf"), "verapdf")
        with mock.patch("pdfa4_export.subprocess.run",
                        return_value=SimpleNamespace(returncode=1, stdout="nonsense", stderr="bad")):
            with self.assertRaisesRegex(RuntimeError, "parseable"):
                _validate_pdfa4(Path("file.pdf"), "verapdf")

    def test_web_form_exposes_optional_pdfa4(self):
        from app import app
        response = app.test_client().get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'value="standard" selected', response.data)
        self.assertIn(b'value="pdfa4"', response.data)

    def test_default_web_render_remains_standard_pdf(self):
        from app import app
        response = app.test_client().post("/render", data={
            "markdown": "## Filing\n\nOrdinary content.",
            "pdf_format": "standard",
        })
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:500])
        self.assertIn("application/pdf", response.content_type)
        self.assertTrue(response.data.startswith(b"%PDF-1."))

    @unittest.skipUnless(shutil.which("verapdf"), "Requires locally installed veraPDF")
    def test_web_pdfa4_export_is_independently_validated(self):
        from app import app
        response = app.test_client().post("/render", data={
            "markdown": "## Filing\n\nA [link](https://example.org) and section § 7502.",
            "pdf_format": "pdfa4",
        })
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:500])
        self.assertIn("application/pdf", response.content_type)
        self.assertTrue(response.data.startswith(b"%PDF-2.0"))

    @unittest.skipUnless(shutil.which("verapdf"), "Requires locally installed veraPDF")
    def test_real_markdown_export_passes_verapdf_4(self):
        try:
            import pikepdf
        except ImportError:
            self.skipTest("pikepdf is unavailable")
        from pdf_compiler import PdfRenderer
        with TemporaryDirectory() as directory:
            source = Path(directory) / "filing.md"
            output = Path(directory) / "filing.pdf"
            source.write_text(
                "# Filing\n\nA legal § symbol, **bold text**, and a "
                "[hyperlink](https://example.org).\n\n## Argument\n\nMore text.",
                encoding="utf-8")
            renderer = PdfRenderer(source, output)
            render_pdf(renderer, pdfa4=True)
            self.assertTrue(output.read_bytes().startswith(b"%PDF-2.0"))
            with pikepdf.open(output) as pdf:
                self.assertEqual(pdf.open_metadata()["pdfaid:part"], "4")
                self.assertEqual(pdf.open_metadata()["pdfaid:rev"], "2020")


if __name__ == "__main__":
    unittest.main()
