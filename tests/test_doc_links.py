"""Dependency-free regression fixtures for the Markdown link checker."""

import tempfile
import unittest
from pathlib import Path

from tools.verification.check_doc_links import check, slugify


class DocLinkChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "target.md").write_text(
            "# Target guide\n## Browser `workflow`\n## Repeat\n## Repeat\n"
            '<a id="explicit-anchor"></a>\n### ブラウザ検証\n',
            encoding="utf-8",
        )

    def run_check(self, body):
        source = self.root / "source.md"
        source.write_text(body, encoding="utf-8")
        return check(self.root, [source])

    def test_valid_links_and_fragments(self):
        body = (
            "[a](target.md) [b](target.md#target-guide) [c](target.md#browser-workflow)\n"
            "[d](target.md#repeat-1) [e](target.md#explicit-anchor) [f](#local)\n"
            "[g](target.md#ブラウザ検証) [h](https://example.invalid/x) [i](./)\n# Local\n"
        )
        self.assertEqual(self.run_check(body), [])

    def test_missing_target_and_fragment_are_reported(self):
        errors = self.run_check("[a](missing.md) [b](target.md#absent)\n")
        self.assertEqual(
            errors,
            [
                "missing target: source.md: missing.md",
                "missing fragment: source.md: target.md#absent",
            ],
        )

    def test_code_examples_are_ignored(self):
        body = "`[a](missing.md)`\n```text\n[b](missing.md)\n```\n"
        self.assertEqual(self.run_check(body), [])

    def test_percent_encoded_target(self):
        (self.root / "main().md").write_text("# Main\n", encoding="utf-8")
        self.assertEqual(self.run_check("[m](main%28%29.md)\n"), [])

    def test_slugify_keeps_unicode_and_drops_punctuation(self):
        self.assertEqual(slugify("Phase A: staff, measures (v1)"), "phase-a-staff-measures-v1")
        self.assertEqual(slugify("ワークツリーとマウントの規約"), "ワークツリーとマウントの規約")


if __name__ == "__main__":
    unittest.main()
