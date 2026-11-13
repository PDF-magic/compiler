from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from configured_renderer import LetterSettings
from emoji_renderer import emoji_markup, EmojiParagraph
from first_page_layout import FirstPagePdfRenderer
from reportlab.lib.styles import getSampleStyleSheet


class EmojiRendererTests(unittest.TestCase):
    def test_sequences_render_as_single_images(self):
        for emoji in ("😀", "👍🏽", "🇺🇸", "👨‍👩‍👧‍👦", "❤️", "1️⃣", "🏳️‍🌈"):
            with self.subTest(emoji=emoji):
                markup = emoji_markup(emoji, 14)
                self.assertEqual(markup.count("<img "), 1)
                self.assertTrue(markup.endswith('/>'))
                self.assertNotIn(emoji, markup)
                paragraph = EmojiParagraph(emoji, getSampleStyleSheet()["Normal"])
                images = [frag for frag in paragraph.frags if hasattr(frag, "cbDefn")]
                self.assertEqual(len(images), 1)
                self.assertEqual(images[0].cbDefn.width, 10)
                paragraph.wrap(300, 100)

    def test_preserves_link_attributes_and_plain_text(self):
        self.assertEqual(emoji_markup("Plain 123 &amp; text", 12), "Plain 123 &amp; text")
        markup = emoji_markup('<link href="https://example.com/😀">😀</link>', 12)
        self.assertIn('href="https://example.com/😀"', markup)
        self.assertEqual(markup.count("<img "), 1)

    def test_unicode_dashes_render_without_missing_glyphs(self):
        from reportlab.pdfbase import pdfmetrics

        paragraph = EmojiParagraph(
            "on‐chain on‑chain 1‒2 en–dash em—dash",
            getSampleStyleSheet()["Normal"],
        )
        self.assertEqual(paragraph.getPlainText(), "on-chain on-chain 1–2 en–dash em—dash")
        for fragment in paragraph.frags:
            font = pdfmetrics.getFont(fragment.fontName)
            for used_font, _ in pdfmetrics.unicode2T1(fragment.text, [font]):
                self.assertNotEqual(used_font.fontName, "ZapfDingbats")
        self.assertIn("<nobr>on-chain</nobr>", emoji_markup("on‑chain", 12))
        self.assertIn(
            'href="https://example.com/on‑chain"',
            emoji_markup('<link href="https://example.com/on‑chain">on‑chain</link>', 12),
        )

    def test_builds_pdf_with_emoji_in_headings_toc_and_wrapped_body(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "emoji.md"
            source.write_text(
                "## Discussion 😀\n\n" + "Body 👍🏽 🇺🇸 👨‍👩‍👧‍👦 ❤️. " * 350,
                encoding="utf-8",
            )
            output = root / "emoji.pdf"
            renderer = FirstPagePdfRenderer(
                source, output, visible_document_title="Emoji 😀",
                settings=LetterSettings(include_toc=True, show_date=False),
            )
            pages, _, _ = renderer.build()
            self.assertGreater(pages, 2)
            self.assertIn(b"/Subtype /Image", output.read_bytes())

    def test_selected_pack_does_not_fall_back(self):
        from zipfile import ZipFile
        from emoji_renderer import emoji_style_scope, validate_emoji_style
        with TemporaryDirectory() as temp:
            path = Path(temp) / "noto.zip"
            bundled = Path(__file__).resolve().parents[1] / "assets" / "twemoji" / "72x72.zip"
            with ZipFile(bundled) as source, ZipFile(path, "w") as target:
                name = next(name for name in source.namelist() if name.endswith("1f600.png"))
                target.writestr("1f600.png", source.read(name))
            validate_emoji_style("noto", path)
            with emoji_style_scope("noto", path):
                self.assertEqual(emoji_markup("😀", 14).count("<img "), 1)
                with self.assertRaisesRegex(ValueError, "does not include emoji"):
                    emoji_markup("👍🏽", 14)
            with self.assertRaisesRegex(ValueError, "unavailable"):
                validate_emoji_style("noto")

    def test_preview_and_invalid_style_web_handling(self):
        from app import app
        with app.test_client() as client:
            page = client.get("/")
            self.assertIn(b'name="emoji_style"', page.data)
            self.assertIn(b'name="emoji_pack"', page.data)
            response = client.post("/emoji-preview", data={"emoji_style": "twemoji"})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.data.startswith(b"\x89PNG\r\n\x1a\n"))
            response = client.post("/render", data={"markdown": "# Emoji 😀",
                                                   "emoji_style": "noto"})
            self.assertEqual(response.status_code, 400)
            self.assertIn(b"unavailable", response.data)


if __name__ == "__main__":
    unittest.main()
