"""Small, dependency-free regression fixtures for translation provenance checks."""

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.verification.check_doc_translations import check


class TranslationChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.original = self.root / "guide.md"
        self.translated = self.root / "guide.ja.md"
        self.original.write_text("# Guide\n[日本語](guide.ja.md)\n", encoding="utf-8")
        self.record = {
            "original": "guide.md",
            "source": {"sha256": hashlib.sha256(self.original.read_bytes()).hexdigest()},
            "state": "draft",
        }
        self.write_translation()

    def write_translation(self, link="[English](guide.md)"):
        self.translated.write_text(
            f"<!-- translation: {json.dumps(self.record)} -->\n{link}\n", encoding="utf-8"
        )

    def test_valid_pair(self):
        self.assertEqual(check(self.root)[0], [])

    def test_fenced_metadata_and_links_are_examples(self):
        with self.translated.open("a", encoding="utf-8") as stream:
            stream.write("\n```text\n<!-- translation: {} -->\n```\n")
        self.assertEqual(check(self.root)[0], [])
        self.original.write_text("```\n[日本語](guide.ja.md)\n```\n", encoding="utf-8")
        self.assertIn("reciprocal", check(self.root)[0][0])

    def test_missing_record(self):
        self.translated.write_text("# 日本語\n", encoding="utf-8")
        self.assertIn("metadata", check(self.root)[0][0])

    def test_invalid_state_and_identity(self):
        for key, value in (("state", "approved"), ("source", {"sha256": "wrong"})):
            with self.subTest(key=key):
                old = self.record[key]
                self.record[key] = value
                self.write_translation()
                self.assertTrue(check(self.root)[0])
                self.record[key] = old

    def test_missing_original_and_path_escape(self):
        for original in ("absent.md", "../outside.md"):
            with self.subTest(original=original):
                self.record["original"] = original
                self.write_translation()
                self.assertTrue(check(self.root)[0])

    def test_missing_links_in_either_direction(self):
        self.write_translation(link="No original link")
        self.assertIn("reciprocal", check(self.root)[0][0])
        self.write_translation()
        self.original.write_text("# No language link\n", encoding="utf-8")
        self.assertIn("reciprocal", check(self.root)[0][0])

    def test_same_pr_stale_digest(self):
        self.original.write_text(self.original.read_text() + "Changed\n", encoding="utf-8")
        self.assertIn("mismatch", check(self.root)[0][0])

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args], text=True).strip()

    def commit_source(self):
        self.git("init", "-q")
        self.git("add", "guide.md")
        self.git(
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "source",
        )
        self.record["source"] = {"commit": self.git("rev-parse", "HEAD")}
        self.write_translation()

    def test_unrelated_commit_does_not_invalidate_source(self):
        self.commit_source()
        (self.root / "other.txt").write_text("unrelated", encoding="utf-8")
        self.git("add", "other.txt")
        self.git(
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "unrelated",
        )
        errors, observations = check(self.root)
        self.assertFalse(errors)
        self.assertTrue(any("unchanged since" in line for line in observations))

    def test_changed_commit_source_requires_stale_marker(self):
        self.commit_source()
        self.original.write_text(self.original.read_text() + "Changed\n", encoding="utf-8")
        self.assertIn("update required", check(self.root)[0][0])
        self.record["state"] = "update required"
        self.write_translation()
        errors, observations = check(self.root)
        self.assertFalse(errors)
        self.assertTrue(any(line.startswith("STALE") for line in observations))

    def test_unavailable_commit_does_not_certify_sync(self):
        self.record["source"] = {"commit": "0" * 40}
        self.write_translation()
        errors, observations = check(self.root)
        self.assertFalse(errors)
        self.assertTrue(any(line.startswith("UNKNOWN") for line in observations))
        self.assertFalse(any("unchanged since" in line for line in observations))


if __name__ == "__main__":
    unittest.main()
