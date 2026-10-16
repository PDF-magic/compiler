from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pymupdf
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT

from pdf_compiler import PdfRenderer
from typography_renderer import TypographyPdfRenderer, TypographySettings


class QuotationTests(unittest.TestCase):
    def _renderer(self, root: Path, text: str, *, typography=None,
                  quote_inline_number_footnotes=False):
        source = root / "source.md"
        source.write_text(text, encoding="utf-8")
        renderer_class = TypographyPdfRenderer if typography else PdfRenderer
        kwargs = {"quote_inline_number_footnotes": quote_inline_number_footnotes}
        if typography:
            kwargs["typography"] = typography
        return renderer_class(source, root / "output.pdf", **kwargs)

    def test_quote_and_source_markers_render_as_joined_quotation(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            renderer = self._renderer(
                root,
                "> [!QUOTE]\n> Stay curious.\n> [!SOURCE] Ada Lovelace",
            )
            flowables = renderer.blockquote_flowables(
                ["[!QUOTE]", "Stay curious.", "[!SOURCE] Ada Lovelace"]
            )

            self.assertEqual(len(flowables), 2)
            body, source = flowables
            self.assertEqual(body.getPlainText(), "Stay curious.")
            self.assertEqual(source.getPlainText(), "— Ada Lovelace")
            self.assertEqual(source.style.alignment, TA_RIGHT)
            self.assertFalse(body.style.quoteRoundBottom)
            self.assertFalse(source.style.quoteRoundTop)

    def test_source_supports_inline_markdown_and_footnote_references(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            renderer = self._renderer(
                root,
                "> [!QUOTE]\n> Words.\n> [!SOURCE] *Author*[^bio]\n\n[^bio]: Biography.",
            )
            flowables = renderer.blockquote_flowables(
                ["[!QUOTE]", "Words.", "[!SOURCE] *Author*[^bio]"]
            )

            source = flowables[-1]
            self.assertEqual(source.getPlainText(), "— Author1")
            self.assertEqual(source.footnote_refs, [1])

    def test_src_is_a_case_insensitive_source_alias(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            renderer = self._renderer(
                root,
                "> [!QUOTE]\n> Stay curious.\n> [!src] Ada Lovelace",
            )
            flowables = renderer.blockquote_flowables(
                ["[!QUOTE]", "Stay curious.", "[!src] Ada Lovelace"]
            )

            self.assertEqual(flowables[-1].getPlainText(), "— Ada Lovelace")
            self.assertEqual(flowables[-1].style.alignment, TA_RIGHT)

    def test_source_footnotes_keep_original_discontinuous_numbers(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            renderer = self._renderer(
                root,
                (
                    "> [!QUOTE]\n"
                    "> First passage.[4] Later passage.[17]\n"
                    "> [4]: Original fourth note.\n"
                    "> [17]: Original seventeenth note.\n"
                    "> [!SOURCE] Author[17]\n\n"
                    "Document text.[^main]\n\n"
                    "[^main]: Document footnote."
                ),
                quote_inline_number_footnotes=True,
            )
            flowables = renderer.blockquote_flowables(
                [
                    "[!QUOTE]",
                    "First passage.[4] Later passage.[17]",
                    "[4]: Original fourth note.",
                    "[17]: Original seventeenth note.",
                    "[!SOURCE] Author[17]",
                ]
            )

            self.assertEqual(renderer.order, ["main"])
            self.assertEqual(len(flowables), 4)
            body, note_four, note_seventeen, source = flowables
            self.assertEqual(body.getPlainText(), "First passage.4 Later passage.17")
            self.assertEqual(note_four.getPlainText(), "4. Original fourth note.")
            self.assertEqual(
                note_seventeen.getPlainText(),
                "17. Original seventeenth note.",
            )
            self.assertEqual(source.getPlainText(), "— Author17")
            self.assertEqual(body.footnote_refs, [])
            self.assertEqual(source.footnote_refs, [])
            self.assertFalse(body.style.quoteRoundBottom)
            self.assertFalse(note_four.style.quoteRoundTop)
            self.assertFalse(note_four.style.quoteRoundBottom)
            self.assertFalse(note_seventeen.style.quoteRoundTop)
            self.assertFalse(note_seventeen.style.quoteRoundBottom)
            self.assertFalse(source.style.quoteRoundTop)

    def test_source_footnotes_render_inside_quote_before_attribution(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            renderer = self._renderer(
                root,
                (
                    "> [!QUOTE]\n"
                    "> First passage.[4] Later passage.[17]\n"
                    "> [4]: Original fourth note.\n"
                    "> [17]: Original seventeenth note.\n"
                    "> [!SOURCE] Ada\n\n"
                    "Document text.[^main]\n\n"
                    "[^main]: Document footnote."
                ),
                quote_inline_number_footnotes=True,
            )
            _pages, footnotes, _continuations = renderer.build()

            self.assertEqual(footnotes, 1)
            with pymupdf.open(renderer.output) as pdf:
                page = pdf[0]
                body = page.search_for("First passage.")[0]
                note_four = page.search_for("4. Original fourth note.")[0]
                note_seventeen = page.search_for("17. Original seventeenth note.")[0]
                source = page.search_for("— Ada")[0]
                self.assertLess(body.y0, note_four.y0)
                self.assertLess(note_four.y0, note_seventeen.y0)
                self.assertLess(note_seventeen.y0, source.y0)


    def test_quote_local_numbers_can_repeat_in_separate_quotes(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            renderer = self._renderer(
                root,
                (
                    "> [!QUOTE]\n"
                    "> First passage.[17]\n"
                    "> [17]: First source footnote.\n"
                    "> [!SOURCE] First Author\n\n"
                    "Document paragraph.[^main]\n\n"
                    "> [!QUOTE]\n"
                    "> Second passage.[17]\n"
                    "> [17]: Second source footnote.\n"
                    "> [!SOURCE] Second Author\n\n"
                    "[^main]: Document footnote."
                ),
                quote_inline_number_footnotes=True,
            )
            self.assertEqual(renderer.order, ["main"])
            story = renderer.build_story()
            rendered = [
                item.getPlainText() for item in story
                if hasattr(item, "getPlainText")
            ]
            self.assertIn("First passage.17", rendered)
            self.assertIn("17. First source footnote.", rendered)
            self.assertIn("Second passage.17", rendered)
            self.assertIn("17. Second source footnote.", rendered)
            self.assertEqual(renderer.order, ["main"])

    def test_quote_local_reference_only_replaces_defined_labels(self):
        with TemporaryDirectory() as temp:
            renderer = self._renderer(
                Path(temp), "> [!QUOTE]\n> Example.",
                quote_inline_number_footnotes=True,
            )
            rendered, refs = renderer.quotation_inline(
                "Local [17], unknown [99], link [17](https://example.org), "
                "and image ![17](https://example.org/image.png).",
                {"17": "Source note."},
            )
            self.assertEqual(rendered.count("<super>17</super>"), 1)
            self.assertIn("[99]", rendered)
            self.assertEqual(refs, [])

    def test_legacy_caret_quote_markers_remain_supported(self):
        with TemporaryDirectory() as temp:
            renderer = self._renderer(
                Path(temp),
                "> [!QUOTE]\n> Legacy citation.[^17]\n"
                "> [^17]: Original footnote.\n> [!SOURCE] Author",
            )
            flowables = renderer.blockquote_flowables(
                ["[!QUOTE]", "Legacy citation.[^17]",
                 "[^17]: Original footnote.", "[!SOURCE] Author"]
            )
            self.assertEqual(flowables[0].getPlainText(), "Legacy citation.17")
            self.assertEqual(flowables[1].getPlainText(), "17. Original footnote.")
            self.assertEqual(renderer.order, [])


    def test_bracket_numbers_are_literal_until_explicitly_enabled(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            text = (
                "> [!QUOTE]\n"
                "> A literal [11] could mean something else.\n"
                "> [11]: Original source note.\n"
                "> [!SOURCE] Writer"
            )
            renderer = self._renderer(root, text)
            self.assertFalse(renderer.quote_inline_number_footnotes)
            quote = renderer.blockquote_flowables([
                "[!QUOTE]", "A literal [11] could mean something else.",
                "[11]: Original source note.", "[!SOURCE] Writer",
            ])
            self.assertEqual(len(quote), 2)
            self.assertIn("[11]", quote[0].getPlainText())
            self.assertIn("[11]: Original source note.", quote[0].getPlainText())
            self.assertEqual(renderer.order, [])

            enabled = self._renderer(root, text, quote_inline_number_footnotes=True)
            quote = enabled.blockquote_flowables([
                "[!QUOTE]", "A literal [11] could mean something else.",
                "[11]: Original source note.", "[!SOURCE] Writer",
            ])
            self.assertEqual([item.getPlainText() for item in quote], [
                "A literal 11 could mean something else.",
                "11. Original source note.", "— Writer",
            ])
            self.assertEqual(enabled.order, [])

    def test_opt_in_accepts_only_defined_numeric_brackets_inside_sourced_quotes(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            renderer = self._renderer(
                root,
                "> [!QUOTE]\n> Example.\n> [11]: Source note.",
                quote_inline_number_footnotes=True,
            )
            body, refs = renderer.quotation_inline(
                "Citation [11], unknown [99], named [source], "
                "link [11](https://example.org), image ![11](x.png), "
                "and legacy [^11].",
                {"11": "Source note."},
            )
            self.assertEqual(body.count("<super>11</super>"), 2)
            self.assertIn("[99]", body)
            self.assertIn("[source]", body)
            self.assertIn("https://example.org", body)
            self.assertIn("x.png", body)
            self.assertEqual(refs, [])
            outside, _ = renderer.markdown_inline("Elsewhere [11]")
            self.assertEqual(outside, "Elsewhere [11]")

    def test_web_can_enable_inline_quote_numbers(self):
        from app import app

        markdown = (
            "> [!QUOTE]\n> Original statement.[11]\n"
            "> [11]: Original source note.\n> [!SOURCE] Writer"
        )
        for enabled in (False, True):
            data = {"markdown": markdown}
            if enabled:
                data["quote_inline_number_footnotes"] = "1"
            response = app.test_client().post("/render", data=data)
            self.assertEqual(response.status_code, 200, response.data[:500])
            with pymupdf.open(stream=response.data, filetype="pdf") as pdf:
                text = pdf[0].get_text()
                if enabled:
                    self.assertIn("11. Original source note.", text)
                else:
                    self.assertIn("[11]: Original source note.", text)

    def test_source_marker_is_literal_in_an_ordinary_blockquote(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            renderer = self._renderer(
                root,
                "> Ordinary.\n> [!SOURCE] Still ordinary.",
            )
            flowables = renderer.blockquote_flowables(
                ["Ordinary.", "[!SOURCE] Still ordinary."]
            )

            self.assertEqual(len(flowables), 1)
            self.assertIn("[!SOURCE] Still ordinary.", flowables[0].getPlainText())

    def test_quotation_uses_configured_blockquote_styling(self):
        typography = TypographySettings(
            body_font_size=14,
            blockquote_color="#123456",
            blockquote_corner_radius=7,
        )
        with TemporaryDirectory() as temp:
            root = Path(temp)
            renderer = self._renderer(
                root,
                "> [!QUOTE]\n> Words.\n> [!SOURCE] Author",
                typography=typography,
            )

            source_style = renderer.styles["QuotationSourceX"]
            self.assertEqual(source_style.fontSize, 12.6)
            self.assertEqual(source_style.quoteCornerRadius, 7)
            self.assertEqual(source_style.quoteAccent.hexval(), "0x123456")

    def test_blockquote_color_directive_overrides_accent_and_is_hidden(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            renderer = self._renderer(
                root,
                "> [!COLOR #A1B2C3]\n> Colored quote.",
            )
            flowables = renderer.blockquote_flowables(
                ["[!COLOR #A1B2C3]", "Colored quote."]
            )

            self.assertEqual(len(flowables), 1)
            self.assertEqual(flowables[0].getPlainText(), "Colored quote.")
            self.assertEqual(flowables[0].style.quoteAccent, colors.HexColor("#A1B2C3"))
            self.assertEqual(flowables[0].style.quoteBackground, colors.HexColor("#A1B2C3"))

    def test_sourced_quotation_color_applies_to_body_and_source(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            renderer = self._renderer(
                root,
                (
                    "> [!QUOTE]\n"
                    "> [!COLOR #123456]\n"
                    "> Stay curious.\n"
                    "> [!SOURCE] Ada Lovelace"
                ),
            )
            flowables = renderer.blockquote_flowables(
                [
                    "[!QUOTE]",
                    "[!COLOR #123456]",
                    "Stay curious.",
                    "[!SOURCE] Ada Lovelace",
                ]
            )

            self.assertEqual(len(flowables), 2)
            self.assertTrue(
                all(
                    item.style.quoteAccent == colors.HexColor("#123456")
                    for item in flowables
                )
            )
            self.assertNotIn("[!COLOR", "\n".join(item.getPlainText() for item in flowables))

    def test_invalid_blockquote_color_directive_remains_literal(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            renderer = self._renderer(
                root,
                "> [!COLOR #ABC]\n> Still ordinary.",
            )
            flowables = renderer.blockquote_flowables(
                ["[!COLOR #ABC]", "Still ordinary."]
            )

            self.assertIn("[!COLOR #ABC]", flowables[0].getPlainText())

    def test_web_renderer_supports_sourced_quotations(self):
        from app import app

        response = app.test_client().post(
            "/render",
            data={
                "markdown": "> [!QUOTE]\n> Stay curious.\n> [!SOURCE] Ada",
                "admonitions_enabled": "0",
            },
        )

        self.assertEqual(response.status_code, 200)
        with pymupdf.open(stream=response.data, filetype="pdf") as pdf:
            text = "".join(item[4] for item in pdf[0].get_text("blocks"))
            self.assertIn("— Ada", text)
            self.assertNotIn("[!QUOTE]", text)
            self.assertNotIn("[!SOURCE]", text)

    def test_rendered_source_is_right_aligned_and_markers_are_hidden(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            renderer = self._renderer(
                root,
                "> [!QUOTE]\n> Stay curious.\n> [!SOURCE] Ada",
            )
            renderer.build()

            with pymupdf.open(renderer.output) as pdf:
                page = pdf[0]
                source_matches = page.search_for("— Ada")
                self.assertTrue(source_matches)
                self.assertGreater(source_matches[0].x0, page.rect.width / 2)
                text = "".join(item[4] for item in page.get_text("blocks"))
                self.assertNotIn("[!QUOTE]", text)
                self.assertNotIn("[!SOURCE]", text)


if __name__ == "__main__":
    unittest.main()
