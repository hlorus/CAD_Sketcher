"""Tests for the shared CHANGELOG.md parser (used by the release workflow and the
in-app "What's new" dialog)."""

from unittest import TestCase

from ..changelog import extract_section

SAMPLE = """# Changelog

Some preamble text that must never be captured.

## 0.4.0
- New thing.
- Another new thing.

## [0.3.0]
- Native curves.

## v0.2.0
- Older release.
"""


class TestChangelogParser(TestCase):
    def test_extracts_matching_section_only(self):
        self.assertEqual(extract_section("0.4.0", SAMPLE), "- New thing.\n- Another new thing.")

    def test_bracketed_heading(self):
        self.assertEqual(extract_section("0.3.0", SAMPLE), "- Native curves.")

    def test_v_prefixed_heading(self):
        self.assertEqual(extract_section("0.2.0", SAMPLE), "- Older release.")

    def test_prerelease_suffix_matches_base_version(self):
        self.assertEqual(extract_section("0.4.0-latest.8", SAMPLE), "- New thing.\n- Another new thing.")

    def test_missing_version_returns_empty(self):
        self.assertEqual(extract_section("9.9.9", SAMPLE), "")

    def test_preamble_is_never_captured(self):
        self.assertNotIn("preamble", extract_section("0.4.0", SAMPLE))

    def test_bundled_changelog_has_current_manifest_entry(self):
        """The shipped CHANGELOG.md must have an entry for the current version."""
        from pathlib import Path
        from .. import get_addon_version

        root = Path(__file__).resolve().parent.parent
        text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
        version = get_addon_version()
        self.assertTrue(
            extract_section(version, text),
            f"CHANGELOG.md has no section for current version {version}",
        )
