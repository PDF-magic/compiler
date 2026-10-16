"""Regression coverage for literal Markdown inline code, including footnotes."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pymupdf
from reportlab.platypus import Paragraph

from pdf_compiler import PdfRenderer


class InlineCodeTests(unittest.TestCase):
    def renderer_for(self, markdown: str, **kwargs):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source = root / "source.md"
        source.write_text(markdown, encoding="utf-8")
        return PdfRenderer(source, root / "output.pdf", **kwargs)

    def test_inline_code_is_monospace_and_preserves_special_characters(self):
        renderer = self.renderer_for("Ordinary text.")
        markup, refs = renderer.markdown_inline(
            "Read `records_2026**final**.[^draft]<&>.csv` and **important**."
        )
        self.assertEqual(refs, [])
        self.assertIn(
            '<font name="Courier">records_2026**final**.[^draft]&lt;&amp;&gt;.csv</font>',
            markup,
        )
        self.assertIn("<b>important</b>", markup)
        paragraph = Paragraph(markup, renderer.styles["BodyX"])
        self.assertIn("records_2026**final**.[^draft]<&>.csv", paragraph.getPlainText())
        code_fragments = [f for f in paragraph.frags if "records_2026" in f.text]
        self.assertEqual(len(code_fragments), 1)
        self.assertEqual(code_fragments[0].fontName, "Courier")

    def test_delimiters_escaping_and_unmatched_backticks(self):
        renderer = self.renderer_for("Text.")
        markup, _ = renderer.markdown_inline(
            r"Double " + "`` `file` ``" + r" and \`literal\` and `unmatched"
        )
        self.assertIn('<font name="Courier">`file`</font>', markup)
        self.assertIn("and `literal` and `unmatched", markup)
        self.assertEqual(markup.count('<font name="Courier">'), 1)
        markup, _ = renderer.markdown_inline("` a ` and `   `")
        self.assertIn('<font name="Courier">a</font>', markup)
        self.assertIn('<font name="Courier">   </font>', markup)

    def test_inline_code_does_not_autolink_or_change_smart_quotes(self):
        renderer = self.renderer_for("Text.", smart_quotes=True)
        markup, _ = renderer.markdown_inline(
            'Quoted "words" and `"https://example.com/file?a=1&b=2"` '
            'beside https://example.org.'
        )
        self.assertIn("“words”", markup)
        self.assertIn(
            '<font name="Courier">"https://example.com/file?a=1&amp;b=2"</font>',
            markup,
        )
        self.assertNotIn('href="https://example.com/', markup)
        self.assertIn('href="https://example.org"', markup)

    def test_code_spans_do_not_create_or_interpolate_footnotes(self):
        renderer = self.renderer_for(
            "Use `file_[^ghost]_{{real}}.md` and cite.[^real]\n\n"
            "[^real]: See `file_[^ghost]_{{real}}.md` on disk.\n"
        )
        self.assertEqual(renderer.order, ["real"])
        markup, refs = renderer.markdown_inline(
            "Use `file_[^ghost]_{{real}}.md`.[^real]"
        )
        self.assertEqual(refs, [1])
        self.assertIn(
            '<font name="Courier">file_[^ghost]_{{real}}.md</font>',
            markup,
        )
        self.assertIn('<link href="#footnote-1"><super>1</super></link>', markup)
        footnote = renderer.footnote_paragraph(1)
        self.assertIn("file_[^ghost]_{{real}}.md", footnote.getPlainText())
        self.assertIn("Courier", {frag.fontName for frag in footnote.frags})

    def test_quotation_local_notes_protect_inline_code(self):
        renderer = self.renderer_for(
            "> [!QUOTE]\n"
            "> Literal `[^ghost]` but actual[^a].\n"
            "> [^a]: See `record_[^ghost].md`.\n"
            "> [!SOURCE] Author with `notes_2026.md`\n\n"
            "Document citation.[^main]\n\n"
            "[^main]: The main note."
        )
        self.assertEqual(renderer.order, ["main"])
        body, local_note, source = renderer.quotation_flowables(
            [
                "[!QUOTE]",
                "Literal `[^ghost]` but actual[^a].",
                "[^a]: See `record_[^ghost].md`.",
                "[!SOURCE] Author with `notes_2026.md`",
            ]
        )
        self.assertEqual(body.getPlainText(), "Literal [^ghost] but actuala.")
        self.assertEqual(local_note.getPlainText(), "a. See record_[^ghost].md.")
        self.assertEqual(source.getPlainText(), "— Author with notes_2026.md")
        self.assertIn("Courier", {frag.fontName for frag in local_note.frags})
        self.assertEqual(renderer.order, ["main"])

    def test_pdf_contains_monospace_filename_in_footnote(self):
        renderer = self.renderer_for(
            "Attached record.[^file]\n\n"
            "[^file]: The filename is `reports_2026_[final].csv` (literal).\n"
        )
        pages, notes, _ = renderer.build()
        self.assertGreaterEqual(pages, 1)
        self.assertEqual(notes, 1)
        with pymupdf.open(renderer.output) as document:
            text = "\n".join(page.get_text() for page in document)
            self.assertIn("reports_2026_[final].csv", text)
            font_spans = [
                span
                for page in document
                for block in page.get_text("dict")["blocks"]
                if "lines" in block
                for line in block["lines"]
                for span in line["spans"]
                if "reports_2026" in span["text"]
            ]
            self.assertTrue(font_spans)
            self.assertTrue(all("Courier" in span["font"] for span in font_spans))


if __name__ == "__main__":
    unittest.main()
