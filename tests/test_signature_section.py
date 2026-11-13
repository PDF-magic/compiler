from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image, ImageDraw
from reportlab.platypus import Image as FlowableImage

from configured_renderer import ConfiguredPdfRenderer
from pdf_compiler import PdfRenderer, SIGNATURE_SENTINEL, replace_signature_tags


class SignatureSectionTests(unittest.TestCase):
    def test_tag_replacement_skips_fenced_examples(self):
        markdown = "In good faith,\n\n[[signature]]\n\n```markdown\n[[signature]]\n```\n"
        processed, count = replace_signature_tags(markdown)

        self.assertEqual(count, 1)
        self.assertIn(SIGNATURE_SENTINEL, processed)
        self.assertIn("```markdown\n[[signature]]\n```", processed)

    def test_signature_image_is_available_to_both_renderers(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "letter.md"
            source.write_text(
                "In good faith,\n\n[[signature]]\n\nJohn Wooten\n\nChief Compliance Officer\n",
                encoding="utf-8",
            )
            signature = root / "signature.png"
            image = Image.new("RGBA", (240, 100), "white")
            ImageDraw.Draw(image).line((35, 65, 205, 35), fill="black", width=6)
            image.save(signature)

            for renderer_class in (PdfRenderer, ConfiguredPdfRenderer):
                renderer = renderer_class(
                    source,
                    root / f"{renderer_class.__name__}.pdf",
                    signature=signature,
                )
                try:
                    self.assertNotIn("[[signature]]", renderer.body_text)
                    self.assertIn("![signature](", renderer.body_text)
                    self.assertIsNotNone(renderer._signature_asset)
                    self.assertTrue(renderer._signature_asset.exists())
                    self.assertTrue(
                        any(isinstance(item, FlowableImage) for item in renderer.build_story())
                    )
                finally:
                    renderer._cleanup_signature_asset()

    def test_tag_without_upload_still_renders_a_signing_line(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "letter.md"
            source.write_text("Sincerely,\n\n[[signature]]\n\nSigner\n", encoding="utf-8")
            renderer = PdfRenderer(source, root / "letter.pdf")
            try:
                self.assertIsNotNone(renderer._signature_asset)
                with Image.open(renderer._signature_asset) as generated:
                    self.assertEqual(generated.size, (132, 50))
                    alpha = generated.getchannel("A")
                    self.assertIsNotNone(alpha.getbbox())
                self.assertTrue(
                    any(isinstance(item, FlowableImage) for item in renderer.build_story())
                )
            finally:
                renderer._cleanup_signature_asset()


if __name__ == "__main__":
    unittest.main()
