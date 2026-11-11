"""Web image embedding and upload security regression tests."""

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pymupdf
from PIL import Image

from app import app
from document_assets import resolve_document_image, safe_upload_path


def png_bytes():
    buffer = BytesIO()
    Image.new("RGB", (12, 12), "red").save(buffer, format="PNG")
    return buffer.getvalue()


class DocumentImageTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def render(self, **fields):
        return self.client.post("/render", data=fields, content_type="multipart/form-data")

    def assert_embeds_image(self, response):
        self.assertEqual(response.status_code, 200, response.get_json(silent=True))
        self.assertEqual(response.mimetype, "application/pdf")
        with pymupdf.open(stream=response.data, filetype="pdf") as pdf:
            self.assertGreater(len(pdf[0].get_images(full=True)), 0)

    def test_single_markdown_file_with_image(self):
        response = self.render(
            source=(BytesIO(b"# Evidence\n\n![Photo](photo.png)\n"), "letter.md"),
            inline_images=(BytesIO(png_bytes()), "photo.png"),
        )
        self.assert_embeds_image(response)

    def test_folder_upload_with_nested_images(self):
        response = self.render(document_files=[
            (BytesIO(b"# Evidence\n\n![Photo](images/photo.png)\n"), "packet/letter.md"),
            (BytesIO(png_bytes()), "packet/images/photo.png"),
        ])
        self.assert_embeds_image(response)

    def test_folder_markdown_preflight(self):
        response = self.client.post("/validate", data={
            "document_files": [
                (BytesIO(b"# Letter\n\nSome text.\n"), "packet/letter.md"),
                (BytesIO(png_bytes()), "packet/images/photo.png"),
            ],
        }, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["valid"])

    def test_pasted_markdown_with_attached_image(self):
        response = self.render(
            markdown="# Evidence\n\n![Photo](photo.png)\n",
            inline_images=(BytesIO(png_bytes()), "photo.png"),
        )
        self.assert_embeds_image(response)

    def test_existing_single_file_upload(self):
        response = self.render(source=(BytesIO(b"# Letter\n\nText\n"), "letter.md"))
        self.assertEqual(response.status_code, 200)

    def test_reject_script_svg_html_and_fake_png(self):
        for filename, payload in (
            ("malware.js", b"alert(1)"),
            ("active.svg", b'<svg onload="alert(1)"/>'),
            ("page.html", b'<script>alert(1)</script>'),
            ("fake.png", b'<script>alert(1)</script>'),
        ):
            with self.subTest(filename=filename):
                response = self.render(markdown="# Test", inline_images=(BytesIO(payload), filename))
                self.assertEqual(response.status_code, 400)

    def test_reject_traversal_and_markup_filenames(self):
        for filename in ("../photo.png", "/tmp/photo.png", "photo<script>.png", "C:\\temp\\photo.png"):
            with self.subTest(filename=filename):
                with self.assertRaises(ValueError):
                    safe_upload_path(filename)
        response = self.render(
            markdown="# Test",
            document_files=[(BytesIO(png_bytes()), "../photo.png")],
        )
        self.assertEqual(response.status_code, 400)

    def test_reject_multiple_markdown_and_duplicate_images(self):
        response = self.render(document_files=[
            (BytesIO(b"# One"), "packet/one.md"),
            (BytesIO(b"# Two"), "packet/two.md"),
        ])
        self.assertEqual(response.status_code, 400)
        response = self.render(
            markdown="# Test",
            inline_images=[
                (BytesIO(png_bytes()), "photo.png"),
                (BytesIO(png_bytes()), "PHOTO.png"),
            ],
        )
        self.assertEqual(response.status_code, 400)

    def test_reject_escaping_image_references(self):
        with TemporaryDirectory() as folder:
            source = Path(folder) / "document.md"
            source.write_text("# Test")
            for reference in ("../outside.png", "/etc/passwd.png", "data:image/png;base64,foo"):
                with self.subTest(reference=reference):
                    with self.assertRaises(ValueError):
                        resolve_document_image(source, reference)

    def test_reject_traversal_in_render(self):
        response = self.render(markdown="# Test\n\n![Outside](../outside.png)\n")
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
