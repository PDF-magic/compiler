from io import BytesIO
import unittest

from app import app


class WebPreflightTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_preflight_issues_do_not_block_rendering(self):
        markdown = "See the [reference](http://localhost/example)."
        validation = self.client.post("/validate", data={"markdown": markdown})
        self.assertEqual(validation.status_code, 200)
        result = validation.get_json()
        self.assertFalse(result["valid"])
        self.assertEqual(
            {issue["category"] for issue in result["issues"]},
            {"legal_style", "url"},
        )

        for upload in (False, True):
            with self.subTest(upload=upload):
                data = (
                    {"source": (BytesIO(markdown.encode("utf-8")), "source.md")}
                    if upload else {"markdown": markdown}
                )
                response = self.client.post("/render", data=data)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.mimetype, "application/pdf")
                self.assertTrue(response.data.startswith(b"%PDF-"))

    def test_render_still_requires_source(self):
        response = self.client.post("/render", data={"markdown": " "})
        self.assertEqual(response.status_code, 400)

    def test_render_still_requires_utf8_upload(self):
        response = self.client.post(
            "/render", data={"source": (BytesIO(b"\xff"), "source.md")}
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
