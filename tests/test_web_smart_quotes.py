import unittest

from app import app


class WebSmartQuotesTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_checkbox_is_off_by_default(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('name="smart_quotes"', html)
        self.assertNotIn('name="smart_quotes" checked', html)

    def test_link_controls_defaults_and_invalid_color(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('name="underline_links" checked', html)
        self.assertIn('name="link_color" value="#2E732E"', html)
        response = self.client.post("/render", data={"markdown": "Text", "link_color": "not-a-color"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("hex color", response.get_json()["error"])

    def test_custom_link_color_renders(self):
        response = self.client.post("/render", data={
            "markdown": "A link https://example.com",
            "link_color": "#7C3AED", "underline_links": "on",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")


if __name__ == "__main__":
    unittest.main()
