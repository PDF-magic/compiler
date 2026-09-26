from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from configured_renderer import ConfiguredPdfRenderer, LetterSettings


def story_text(renderer: ConfiguredPdfRenderer) -> str:
    parts = []
    for flowable in renderer.build_story():
        get_plain_text = getattr(flowable, "getPlainText", None)
        if callable(get_plain_text):
            parts.append(get_plain_text())
    return "\n".join(parts)


class LicensingTests(unittest.TestCase):
    def renderer(self, root: Path, settings: LetterSettings) -> ConfiguredPdfRenderer:
        source = root / "document.md"
        source.write_text("Body paragraph.", encoding="utf-8")
        return ConfiguredPdfRenderer(source, root / "document.pdf", settings=settings)

    def test_unknown_license_preset_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown license preset"):
            LetterSettings(license_preset="unknown")

    def test_cc_by_sa_adds_compact_reference_and_subtitle(self):
        with TemporaryDirectory() as temp:
            renderer = self.renderer(
                Path(temp),
                LetterSettings(
                    show_date=False,
                    license_preset="cc_by_sa_4_0",
                    license_subtitle="Attribution requested for archived copies.",
                ),
            )
            text = story_text(renderer)
            self.assertIn("Creative Commons Attribution-ShareAlike 4.0 International", text)
            self.assertIn("Attribution requested for archived copies.", text)
            self.assertNotIn("GNU Free Documentation License", text)

    def test_note_without_preset_still_renders_as_compact_end_note(self):
        with TemporaryDirectory() as temp:
            renderer = self.renderer(
                Path(temp),
                LetterSettings(show_date=False, license_subtitle="Custom licensing note."),
            )
            self.assertIn("Custom licensing note.", story_text(renderer))

    def test_gfdl_appends_full_license_without_compact_cc_reference(self):
        with TemporaryDirectory() as temp:
            renderer = self.renderer(
                Path(temp),
                LetterSettings(
                    show_date=False,
                    license_preset="gfdl_1_3",
                    license_subtitle="Document-specific GFDL context.",
                ),
            )
            text = story_text(renderer)
            self.assertIn("GNU Free Documentation License", text)
            self.assertIn("0. PREAMBLE", text)
            self.assertIn("11. RELICENSING", text)
            self.assertIn("Document-specific GFDL context.", text)
            self.assertNotIn("Creative Commons Attribution-ShareAlike 4.0 International license", text)

            renderer.build()
            self.assertTrue(renderer.output.read_bytes().startswith(b"%PDF-"))


if __name__ == "__main__":
    unittest.main()
