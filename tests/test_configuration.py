from pathlib import Path
import shutil
import subprocess
import unittest

from app import app


class ConfigurationTests(unittest.TestCase):
    def test_config_controls_and_script_are_served(self):
        response = app.test_client().get('/')
        self.assertEqual(response.status_code, 200)
        for marker in (b'id="export-config"', b'id="import-config"', b'id="config-file"',
                       b'/static/configuration.js', b'name="quote_inline_number_footnotes"'):
            self.assertIn(marker, response.data)
        with app.test_client().get('/static/configuration.js') as script:
            self.assertEqual(script.status_code, 200)

    def test_metadata_appears_beneath_letterhead_not_as_a_separate_step(self):
        response = app.test_client().get('/')
        self.assertEqual(response.status_code, 200)
        page = response.data.decode('utf-8')
        self.assertIn('Step 1 of 10', page)
        self.assertNotIn('data-step-title="Output metadata"', page)
        self.assertNotIn('>Metadata</button>', page)
        letterhead = page.split('data-step-title="Letterhead"', 1)[1].split(
            'data-step-title="Running header', 1
        )[0]
        self.assertLess(letterhead.index('name="document_title"'),
                        letterhead.index('name="title"'))
        self.assertLess(letterhead.index('name="title"'),
                        letterhead.index('name="keywords"'))
        self.assertIn('/static/metadata-inheritance.js', page)
        document = page.split('data-step-title="Document"', 1)[1].split(
            'data-step-title="Typography"', 1
        )[0]
        self.assertIn('name="pdf_format"', document)

    def test_logo_is_served_as_svg_favicon(self):
        with app.test_client() as client:
            page = client.get("/")
            self.assertEqual(page.status_code, 200)
            self.assertIn(
                b'<link rel="icon" type="image/svg+xml" href="/static/logo.svg">',
                page.data,
            )

            icon = client.get("/static/logo.svg")
            self.assertEqual(icon.status_code, 200)
            self.assertEqual(icon.mimetype, "image/svg+xml")
            self.assertIn(b'<svg ', icon.data)
            self.assertIn(b'viewBox="0 0 64 64"', icon.data)

    @unittest.skipUnless(shutil.which('node'), 'Node is required for configuration browser logic tests')
    def test_configuration_round_trip_and_validation(self):
        result = subprocess.run(
            [shutil.which('node'), str(Path(__file__).with_name('configuration.test.cjs'))],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
