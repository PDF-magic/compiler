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
                       b'/static/configuration.js'):
            self.assertIn(marker, response.data)
        with app.test_client().get('/static/configuration.js') as script:
            self.assertEqual(script.status_code, 200)

    @unittest.skipUnless(shutil.which('node'), 'Node is required for configuration browser logic tests')
    def test_configuration_round_trip_and_validation(self):
        result = subprocess.run(
            [shutil.which('node'), str(Path(__file__).with_name('configuration.test.cjs'))],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
