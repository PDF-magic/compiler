from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import json

import pymupdf
from reportlab.pdfgen.canvas import Canvas

from configured_renderer import ConfiguredPdfRenderer, LetterSettings, format_page_number


class HeaderFooterSettingsTests(unittest.TestCase):
    def test_page_number_formats(self):
        self.assertEqual(format_page_number("none", 2, 5), "")
        self.assertEqual(format_page_number("number", 2, 5), "2")
        self.assertEqual(format_page_number("page_number", 2, 5), "Page 2")
        self.assertEqual(format_page_number("number_of_total", 2, 5), "2 of 5")
        self.assertEqual(format_page_number("page_number_of_total", 2, 5), "Page 2 of 5")

    def test_page_numbers_default_off(self):
        self.assertEqual(LetterSettings().page_number_style, "none")

    def test_draft_footer_is_opt_in_and_checks_commit(self):
        self.assertFalse(LetterSettings().draft_footer)
        with self.assertRaisesRegex(ValueError, "Git commit SHA"):
            LetterSettings(draft_footer=True, draft_reference="rev 2")
        with self.assertRaisesRegex(ValueError, "64 characters"):
            LetterSettings(draft_footer=True, draft_reference="x" * 65, latest_commit="a" * 40)

    def test_draft_watermark_renders_on_every_page_with_page_numbers(self):
        from app import app
        response = app.test_client().post("/render", data={
            "markdown": "## Filing\n\n" + ("Paragraph text. " * 50 + "\n\n") * 35,
            "draft_footer": "on",
            "draft_reference": "SEC-2026 / rev 2",
            "latest_commit": "a" * 40,
            "page_number_style": "page_number_of_total",
            "show_date": "on",
        })
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:400])
        with pymupdf.open(stream=response.data, filetype="pdf") as document:
            self.assertGreater(len(document), 1)
            for index, page in enumerate(document):
                text = page.get_text()
                self.assertIn("DRAFT", text)
                self.assertIn("SEC-2026 / rev 2", text)
                self.assertIn("a" * 40, text)
                self.assertIn(f"Page {index + 1} of {len(document)}", text)

    def test_unchecked_watermark_ignores_fields_and_does_not_render(self):
        from app import app
        response = app.test_client().post("/render", data={
            "markdown": "Only a final body paragraph.",
            "draft_reference": "Unused",
            "latest_commit": "invalid-hash",
        })
        self.assertEqual(response.status_code, 200)
        with pymupdf.open(stream=response.data, filetype="pdf") as document:
            self.assertNotIn("DRAFT", document[0].get_text())

    def test_public_github_lookup_fills_commit_and_respects_source_path(self):
        from app import app
        sha = "b" * 40
        from io import BytesIO as MemoryResponse
        with patch("app.urlopen") as mocked_open:
            mocked_open.return_value.__enter__.return_value = MemoryResponse(
                json.dumps([{"sha": sha}]).encode("utf-8")
            )
            response = app.test_client().post("/render", data={
                "markdown": "Short draft.",
                "draft_footer": "on",
                "draft_reference": "test draft",
                "source_repository": "PDF-magic/compiler",
                "source_path": "docs/letter.md",
            })
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:400])
        self.assertIn("path=docs%2Fletter.md", mocked_open.call_args.args[0].full_url)
        with pymupdf.open(stream=response.data, filetype="pdf") as document:
            self.assertIn(sha, document[0].get_text())

    def test_draft_footer_rejects_invalid_hash_or_missing_revision(self):
        from app import app
        client = app.test_client()
        for payload in (
            {"latest_commit": "not-a-commit"},
            {"draft_reference": "revision 1"},
            {"source_repository": "https://bad.example/internal"},
        ):
            response = client.post("/render", data={
                "markdown": "Body text.",
                "draft_footer": "on",
                **payload,
            })
            self.assertEqual(response.status_code, 400)
            self.assertIn("error", response.get_json())

    def test_headers_are_separate_settings(self):
        settings = LetterSettings(
            first_page_header="First-page header",
            remaining_page_header="Running header",
        )
        self.assertEqual(settings.first_page_header, "First-page header")
        self.assertEqual(settings.remaining_page_header, "Running header")

    def test_unknown_page_number_style_is_rejected(self):
        with self.assertRaises(ValueError):
            LetterSettings(page_number_style="roman")

    def test_both_headers_render_link_labels_and_pdf_uri_annotations(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "letter.md"
            source.write_text("Body text", encoding="utf-8")
            renderer = ConfiguredPdfRenderer(
                source, root / "letter.pdf", smart_quotes=True,
                settings=LetterSettings(
                    show_date=False,
                    first_page_header='[First & **bold**](https://example.com/first?a=1&b=2)',
                    remaining_page_header="[Later](https://example.com/later?q='value') / [Other](https://example.org)",
                ),
            )
            payload = BytesIO()
            canvas = Canvas(payload, pageCompression=0)
            doc = renderer.document(root / "letter.pdf")
            renderer.draw_branding(canvas, doc)
            canvas.showPage()
            renderer.draw_remaining_header(canvas, doc)
            canvas.save()
            pdf = payload.getvalue()
            self.assertIn(b'/URI (https://example.com/first?a=1&b=2)', pdf)
            self.assertIn(b"/URI (https://example.com/later?q='value')", pdf)
            self.assertIn(b'/URI (https://example.org)', pdf)
            for label in (b'First & ', b'bold', b'Later', b'Other'):
                self.assertIn(label, pdf)
            self.assertNotIn(b'[First', pdf)

    def test_web_renderer_preserves_header_links_with_custom_typography(self):
        from app import app
        response = app.test_client().post("/render", data={
            "markdown": "Body paragraph.\n\n" * 150,
            "first_page_header": "[First](https://example.com/first)",
            "remaining_page_header": "[Later](https://example.com/later)",
            "document_title": "Visible title",
            "header_font_size": "12",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"/URI (https://example.com/first)", response.data)
        self.assertIn(b"/URI (https://example.com/later)", response.data)

    def test_long_linked_header_fits_and_plain_text_is_escaped(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "letter.md"
            source.write_text("Body text", encoding="utf-8")
            renderer = ConfiguredPdfRenderer(
                source, root / "letter.pdf",
                settings=LetterSettings(
                    first_page_header='A & B <review> ' + '[Long header text](https://example.com) ' * 30,
                ),
            )
            renderer.build()
            self.assertTrue(renderer.output.read_bytes().startswith(b'%PDF-'))


if __name__ == "__main__":
    unittest.main()
