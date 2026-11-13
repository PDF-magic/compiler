import tempfile
import unittest
from pathlib import Path

from reportlab.platypus import HRFlowable

from configured_renderer import ConfiguredPdfRenderer
from pdf_compiler import PdfRenderer


class HorizontalRuleTests(unittest.TestCase):
    def story(self, renderer_class, markdown):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "document.md"
            source.write_text(markdown, encoding="utf-8")
            return renderer_class(source, source.with_suffix(".pdf")).build_story()

    def test_rule_variants_separate_paragraphs(self):
        for renderer_class in (PdfRenderer, ConfiguredPdfRenderer):
            for marker in ("***", "****", "* * *", "---", "- - -", "___", "_ _ _", "  *\t*\t*  "):
                with self.subTest(renderer=renderer_class.__name__, marker=marker):
                    story = self.story(renderer_class, f"Before\n{marker}\nAfter")
                    rules = [i for i, item in enumerate(story) if isinstance(item, HRFlowable)]
                    self.assertEqual(len(rules), 1)
                    before = [getattr(item, "text", "") for item in story[:rules[0]]]
                    after = [getattr(item, "text", "") for item in story[rules[0] + 1:]]
                    self.assertIn("Before", before)
                    self.assertIn("After", after)

    def test_non_rules_and_fenced_code_remain_content(self):
        for renderer_class in (PdfRenderer, ConfiguredPdfRenderer):
            for content in ("**", "--", "__", "*-*", "* item", "Text *** text", "```\n***\n---\n___\n```", r"\*\*\*"):
                with self.subTest(renderer=renderer_class.__name__, content=content):
                    story = self.story(renderer_class, content)
                    self.assertFalse(any(isinstance(item, HRFlowable) for item in story))


if __name__ == "__main__":
    unittest.main()
