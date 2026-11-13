from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pymupdf

from app import app
from configured_renderer import LetterSettings
from first_page_layout import FirstPagePdfRenderer
from typography_renderer import TypographySettings


class RenderStyleTests(unittest.TestCase):
    def test_unknown_style_is_rejected(self):
        response = app.test_client().post('/render', data={
            'markdown': 'A short letter.', 'render_style': 'unknown',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('Unknown render style', response.json['error'])

    def test_professional_defaults_and_explicit_override_reach_pdf(self):
        for extra, expected in (({}, 12), ({'body_font_size': '13'}, 13)):
            with self.subTest(extra=extra):
                response = app.test_client().post('/render', data={
                    'markdown': 'A distinctive body paragraph.',
                    'render_style': 'professional', **extra,
                })
                self.assertEqual(response.status_code, 200)
                with pymupdf.open(stream=response.data, filetype='pdf') as pdf:
                    spans = [s for b in pdf[0].get_text('dict')['blocks'] if 'lines' in b
                             for line in b['lines'] for s in line['spans']]
                    body = next(s for s in spans if 'distinctive' in s['text'])
                    self.assertAlmostEqual(body['size'], expected)

    def test_note_continuations_preserve_text_and_page_counts(self):
        note = ('A detailed source explanation. ' * 250) + 'FINAL NOTE SENTINEL.'
        response = app.test_client().post('/render', data={
            'markdown': 'The proposition.[^source]\n\n[^source]: ' + note,
            'render_style': 'professional', 'page_number_style': 'page_number_of_total',
        })
        self.assertEqual(response.status_code, 200)
        with pymupdf.open(stream=response.data, filetype='pdf') as pdf:
            self.assertGreater(len(pdf), 1)
            self.assertIn('FINAL NOTE SENTINEL.', ''.join(p.get_text() for p in pdf))
            for index, page in enumerate(pdf):
                self.assertIn(f'Page {index + 1} of {len(pdf)}', page.get_text())

    def test_professional_address_and_full_height_without_notes(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'letter.md'
            source.write_text('A paragraph.\n\n> A quotation.\n')
            renderer = FirstPagePdfRenderer(
                source, root / 'out.pdf',
                settings=LetterSettings(show_date=False, addressee='First line\nSecond line'),
                typography=TypographySettings.for_style('professional'),
            )
            self.assertLess(renderer.bottom, 72)
            self.assertEqual(renderer._addressee_block()[0].style.firstLineIndent, 0)
            renderer.build()
            with pymupdf.open(renderer.output) as pdf:
                self.assertFalse(pdf[0].get_drawings(), 'Plain quotes should have no decorative box or stripe')
                lines = pdf[0].search_for('First line') + pdf[0].search_for('Second line')
                self.assertAlmostEqual(lines[0].x0, lines[1].x0)

    def test_style_control_is_available(self):
        response = app.test_client().get('/')
        self.assertIn(b'Professional filing', response.data)
        self.assertIn(b'/static/render-styles.js', response.data)

    def test_split_paragraph_keeps_note_on_page_with_its_citation(self):
        response = app.test_client().post('/render', data={
            'markdown': ('A long paragraph that crosses a page boundary. ' * 180)
                        + '[^end]\n\n[^end]: NOTE DESTINATION SENTINEL.',
            'render_style': 'professional',
        })
        self.assertEqual(response.status_code, 200)
        with pymupdf.open(stream=response.data, filetype='pdf') as pdf:
            links = [(index, link) for index, page in enumerate(pdf) for link in page.get_links()]
            self.assertEqual(len(links), 1)
            index, link = links[0]
            self.assertEqual(link['page'], index)
            self.assertIn('NOTE DESTINATION SENTINEL.', pdf[index].get_text())

    def test_preset_has_no_hidden_effect_when_explicit_settings_match(self):
        values = asdict(TypographySettings.for_style('professional'))
        values.pop('render_style')
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'letter.md'
            source.write_text('## Heading\n\nParagraph.[^a]\n\n> Quotation.\n\n[^a]: Source text.')
            renderers = [FirstPagePdfRenderer(
                source, root / f'{name}.pdf',
                settings=LetterSettings(show_date=False),
                typography=TypographySettings(render_style=name, **values),
            ) for name in ('classic', 'professional')]
            for renderer in renderers:
                renderer.build()
            with pymupdf.open(renderers[0].output) as first, pymupdf.open(renderers[1].output) as second:
                self.assertEqual(len(first), len(second))
                for a, b in zip(first, second):
                    self.assertEqual(a.get_text('dict'), b.get_text('dict'))
                    self.assertEqual(a.get_drawings(), b.get_drawings())

    def test_professional_layout_overrides_and_unchecked_toggles(self):
        from unittest.mock import patch
        with patch('app.FirstPagePdfRenderer', wraps=FirstPagePdfRenderer) as renderer:
            response = app.test_client().post('/render', data={
                'markdown': 'Text.', 'render_style': 'professional',
                'left_margin': '1.2', 'body_alignment': 'left',
                'body_first_line_indent': '0', 'plain_quotations': '0',
                'full_page_without_notes': '0', 'keep_headings_with_text': '0',
            })
        self.assertEqual(response.status_code, 200)
        typography = renderer.call_args.kwargs['typography']
        self.assertEqual(typography.left_margin, 1.2)
        self.assertEqual(typography.body_alignment, 'left')
        self.assertEqual(typography.body_first_line_indent, 0)
        self.assertFalse(typography.plain_quotations)
        self.assertFalse(typography.full_page_without_notes)
        self.assertFalse(typography.keep_headings_with_text)

    def test_invalid_presentation_controls_return_400(self):
        for data in ({'left_margin': 'nan'}, {'quote_left_indent': '-1'},
                     {'body_alignment': 'unknown'}, {'footnote_line_spacing': '4'}):
            with self.subTest(data=data):
                response = app.test_client().post('/render', data={'markdown': 'Text.', **data})
                self.assertEqual(response.status_code, 400)


if __name__ == '__main__':
    unittest.main()
