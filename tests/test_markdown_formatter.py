"""Regression tests for explicitly requested Markdown normalization."""

from io import BytesIO
import unittest
from unittest.mock import patch

from app import app
from markdown_formatter import format_markdown


class MarkdownFormatterTests(unittest.TestCase):
    def test_formats_unordered_lists_and_italics(self):
        source = (
            "* first\n"
            "+ second\n"
            "    * nested\n"
            "\n"
            "Use *italics*, **bold**, and ***both***.\n"
        )
        self.assertEqual(
            format_markdown(source),
            "- first\n- second\n    - nested\n\n"
            "Use _italics_, **bold**, and **_both_**.\n",
        )

    def test_preserves_code_and_thematic_breaks(self):
        source = (
            "```md\n"
            "* untouched list\n"
            "*untouched italics*\n"
            "```\n"
            "\n"
            "* * *\n"
            "Use `*literal*` and *real*.\n"
        )
        self.assertEqual(
            format_markdown(source),
            "```md\n* untouched list\n*untouched italics*\n```\n\n"
            "* * *\nUse `*literal*` and _real_.\n",
        )

    def test_preserves_existing_canonical_markup(self):
        source = "- item\nAlready _italic_ and **bold**.\n"
        self.assertEqual(format_markdown(source), source)

    def test_formatter_is_idempotent(self):
        source = "* item\nUse *italics*, **bold**, and `*code*`.\n"
        formatted = format_markdown(source)
        self.assertEqual(format_markdown(formatted), formatted)


class MarkdownFormattingOptInTests(unittest.TestCase):
    source = "* first\nUse *italics* and **bold**.\n"
    formatted = "- first\nUse _italics_ and **bold**.\n"

    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_web_ui_has_separate_explicit_format_action(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('type="submit" formaction="/format"', html)
        self.assertIn('>Format Markdown</button>', html)
        self.assertIn('id="render-button"', html)
        self.assertIn('rendering still uses the original submitted source', html)

    def test_format_requires_explicit_post(self):
        with patch("app.format_markdown", side_effect=AssertionError("unexpected format")) as formatter:
            response = self.client.get("/format")
        self.assertEqual(response.status_code, 405)
        formatter.assert_not_called()

    def test_explicit_format_downloads_a_copy_of_pasted_markdown(self):
        with patch("app.format_markdown", wraps=format_markdown) as formatter:
            response = self.client.post("/format", data={"markdown": self.source})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/markdown")
        self.assertEqual(response.get_data(as_text=True), self.formatted)
        self.assertIn("attachment", response.headers["Content-Disposition"])
        self.assertIn("document-formatted.md", response.headers["Content-Disposition"])
        formatter.assert_called_once_with(self.source)

    def test_explicit_format_preserves_uploaded_filename_extension(self):
        response = self.client.post(
            "/format",
            data={"source": (BytesIO(self.source.encode("utf-8")), "Draft.MARKDOWN")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(as_text=True), self.formatted)
        self.assertIn("Draft-formatted.markdown", response.headers["Content-Disposition"])

    def test_format_rejects_missing_and_invalid_sources(self):
        with patch("app.format_markdown", side_effect=AssertionError("unexpected format")) as formatter:
            missing = self.client.post("/format", data={"markdown": " "})
            invalid = self.client.post(
                "/format", data={"source": (BytesIO(b"\xff"), "invalid.md")}
            )
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(invalid.status_code, 400)
        formatter.assert_not_called()

    def test_validation_never_formats_submitted_markdown(self):
        with patch("app.format_markdown", side_effect=AssertionError("unexpected format")) as formatter:
            with patch("app.preflight_issues", return_value=[]) as validate:
                response = self.client.post("/validate", data={"markdown": self.source})
        self.assertEqual(response.status_code, 200)
        validate.assert_called_once_with(self.source)
        formatter.assert_not_called()

    def test_word_exports_never_format_submitted_markdown(self):
        with patch("app.format_markdown", side_effect=AssertionError("unexpected format")) as formatter:
            with patch("app.build_word_document", return_value=b"DOCX") as export:
                for profile in ("court_docx", "federal_register_docx"):
                    with self.subTest(profile=profile):
                        response = self.client.post(
                            "/render",
                            data={"markdown": self.source, "output_format": profile},
                        )
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.data, b"DOCX")
        self.assertEqual(export.call_count, 2)
        for call in export.call_args_list:
            self.assertEqual(call.args[0], self.source)
        formatter.assert_not_called()

    def test_pdf_export_never_formats_uploaded_markdown(self):
        with patch("app.format_markdown", side_effect=AssertionError("unexpected format")) as formatter:
            with patch("app.FirstPagePdfRenderer") as renderer:
                def render_without_modification():
                    source_path, output_path = renderer.call_args.args[:2]
                    self.assertEqual(source_path.read_text(encoding="utf-8"), self.source)
                    output_path.write_bytes(b"%PDF-test")

                renderer.return_value.build.side_effect = render_without_modification
                response = self.client.post(
                    "/render",
                    data={"source": (BytesIO(self.source.encode("utf-8")), "source.md")},
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"%PDF-test")
        formatter.assert_not_called()


if __name__ == "__main__":
    unittest.main()
