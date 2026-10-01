from io import BytesIO
import unittest

import pymupdf

from app import app


def pdf_with_metadata(**metadata) -> bytes:
    document = pymupdf.open()
    document.new_page()
    document.set_metadata(metadata)
    payload = document.tobytes()
    document.close()
    return payload


class PreviousPdfMetadataTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_previous_pdf_metadata_fills_blank_fields(self):
        previous = pdf_with_metadata(
            title="Earlier Comment Letter",
            author="Earlier Author",
            subject="Earlier Subject",
            keywords="earlier, metadata",
        )
        response = self.client.post(
            "/render",
            data={
                "markdown": "## Body\n\nText",
                "previous_pdf": (BytesIO(previous), "earlier.pdf"),
                "author": "Current Author",
            },
        )

        self.assertEqual(response.status_code, 200)
        with pymupdf.open(stream=response.data, filetype="pdf") as rendered:
            metadata = rendered.metadata

        self.assertEqual(metadata["title"], "Earlier Comment Letter")
        self.assertEqual(metadata["author"], "Current Author")
        self.assertEqual(metadata["subject"], "Earlier Subject")
        self.assertEqual(metadata["keywords"], "earlier, metadata")

    def test_explicit_metadata_overrides_previous_pdf(self):
        previous = pdf_with_metadata(
            title="Earlier Title",
            author="Earlier Author",
            subject="Earlier Subject",
            keywords="earlier",
        )
        response = self.client.post(
            "/render",
            data={
                "markdown": "## Body\n\nText",
                "previous_pdf": (BytesIO(previous), "earlier.pdf"),
                "title": "Current Title",
                "author": "Current Author",
                "subject": "Current Subject",
                "keywords": "current",
            },
        )

        self.assertEqual(response.status_code, 200)
        with pymupdf.open(stream=response.data, filetype="pdf") as rendered:
            metadata = rendered.metadata

        self.assertEqual(metadata["title"], "Current Title")
        self.assertEqual(metadata["author"], "Current Author")
        self.assertEqual(metadata["subject"], "Current Subject")
        self.assertEqual(metadata["keywords"], "current")

    def test_invalid_previous_pdf_is_rejected(self):
        response = self.client.post(
            "/render",
            data={
                "markdown": "## Body\n\nText",
                "previous_pdf": (BytesIO(b"not a pdf"), "broken.pdf"),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["error"],
            "Previous PDF must be a readable PDF.",
        )


if __name__ == "__main__":
    unittest.main()
