"""Regression tests for the opt-in first-page drag-and-drop letterhead."""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pymupdf

from configured_renderer import LetterSettings
from first_page_layout import FirstPagePdfRenderer, parse_letterhead_layout


def item(kind, x, y, width=40, *, align="left", visible=True, **other):
    return dict(kind=kind, x=x, y=y, width=width, align=align,
                visible=visible, **other)


def layout(*fields):
    return json.dumps({"fields": list(fields)})


class LetterheadLayoutTests(unittest.TestCase):
    def test_opt_in_retains_legacy_fallback(self):
        self.assertIsNone(parse_letterhead_layout(None))
        self.assertIsNone(parse_letterhead_layout(""))
        self.assertEqual(parse_letterhead_layout(layout()), ())

    def test_coordinates_custom_data_and_visibility(self):
        source = layout(
            item("document_title", 5, 13, align="center", visible=False),
            item("custom", 40, 70, id="custom-1",
                 label="Tracking", text="SRC-123\nReceived"),
        )
        result = parse_letterhead_layout(source)
        self.assertEqual(result[0]["align"], "center")
        self.assertFalse(result[0]["visible"])
        self.assertEqual(result[1]["text"], "SRC-123\nReceived")

    def test_rejects_unsafe_or_inconsistent_layouts(self):
        samples = [
            "{",
            json.dumps([]),
            json.dumps({"fields": "no"}),
            layout(item("title", 0, 0)),
            layout(item("date", 90, 0, 20)),
            layout(item("date", 0, -1)),
            layout(item("date", True, 0)),
            layout(item("date", 0, 0, align="outside")),
            layout(item("date", 0, 0), item("date", 15, 50)),
            layout(item("custom", 0, 0, id="bad", label="X", text="Y")),
            layout(item("custom", 0, 0, id="custom-1", label="X", text="<" * 501)),
        ]
        for source in samples:
            with self.subTest(source=source[:70]):
                with self.assertRaises(ValueError):
                    parse_letterhead_layout(source)

    def test_render_moves_preset_and_custom_fields_into_page_one(self):
        fields = parse_letterhead_layout(layout(
            item("first_page_header", 0, 0, 100, align="center"),
            item("document_title", 5, 20, 50),
            item("custom", 55, 42, 40, id="custom-1",
                 label="Tracking", text="REF-2026-15"),
            item("addressee", 5, 75, 55),
            item("quote_number", 60, 17, 30, visible=False),
        ))
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.md"
            source.write_text("Dear Recipient,\n\nBody text follows.", encoding="utf-8")
            output = root / "result.pdf"
            renderer = FirstPagePdfRenderer(
                source, output,
                settings=LetterSettings(
                    show_date=False, first_page_header="My cover header",
                    addressee="Ms. Example\nSecretary",
                    quote_number="HIDDEN-REF",
                ),
                visible_document_title="Visible File Title",
                letterhead_layout=fields,
            )
            renderer.build()
            self.assertGreater(renderer.top, 2.8 * 72)
            with pymupdf.open(output) as pdf:
                page = pdf[0]
                header = page.search_for("My cover header")
                title = page.search_for("Visible File Title")
                tracking = page.search_for("REF-2026-15")
                recipient = page.search_for("Ms. Example")
                body = page.search_for("Body text follows")
                for matches in (header, title, tracking, recipient, body):
                    self.assertTrue(matches)
                self.assertLess(header[0].y0, title[0].y0)
                self.assertGreater(tracking[0].x0, page.rect.width / 2)
                self.assertGreater(recipient[0].y0, title[0].y0)
                self.assertGreater(body[0].y0, recipient[0].y1)
                self.assertFalse(page.search_for("HIDDEN-REF"))
                self.assertEqual(len(page.search_for("Ms. Example")), 1)

    def test_bad_layout_returns_http_400(self):
        from app import app
        with app.test_client() as client:
            response = client.post("/render", data={
                "markdown": "Test document",
                "letterhead_layout": layout(item("date", 95, 4, 50)),
            })
        self.assertEqual(response.status_code, 400)
        self.assertIn("letterhead", response.get_json()["error"].lower())

    def test_web_editor_has_keyboard_and_drag_controls(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / "static" / "letterhead-layout.js").read_text(encoding="utf-8")
        template = (root / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertIn("pointermove", script)
        self.assertIn("ArrowLeft", script)
        self.assertIn('name="letterhead_layout"', template)
        self.assertIn('id="letterhead-custom-text"', template)


if __name__ == "__main__":
    unittest.main()
