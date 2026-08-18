"""Tests for the shared CHANGELOG.md parser (used by the release workflow and the
in-app "What's new" dialog)."""

from unittest import TestCase

from ..changelog import extract_section, latest_version


def _semver(version: str) -> tuple:
    """``"0.3.1"`` / ``"0.3.1-latest.8"`` -> ``(0, 3, 1)`` for ordering."""
    return tuple(int(part) for part in version.split("-", 1)[0].split("."))


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
        self.assertEqual(
            extract_section("0.4.0", SAMPLE), "- New thing.\n- Another new thing."
        )

    def test_bracketed_heading(self):
        self.assertEqual(extract_section("0.3.0", SAMPLE), "- Native curves.")

    def test_v_prefixed_heading(self):
        self.assertEqual(extract_section("0.2.0", SAMPLE), "- Older release.")

    def test_prerelease_suffix_matches_base_version(self):
        self.assertEqual(
            extract_section("0.4.0-latest.8", SAMPLE),
            "- New thing.\n- Another new thing.",
        )

    def test_missing_version_returns_empty(self):
        self.assertEqual(extract_section("9.9.9", SAMPLE), "")

    def test_preamble_is_never_captured(self):
        self.assertNotIn("preamble", extract_section("0.4.0", SAMPLE))

    def test_bundled_changelog_has_current_manifest_entry(self):
        """The shipped CHANGELOG.md must have an entry for the current version,
        unless the manifest was just bumped ahead of it.

        After a release the auto bump-version job moves the manifest to the next
        patch immediately, so there is a normal development window where that
        version legitimately has no changelog section yet. The release flow and
        the in-app "What's new" dialog both tolerate that gap (they wait for the
        notes), so this test must too, rather than red-failing main and every PR
        until someone writes the entry. The guard still fires when an entry is
        missing for a version that is *not* ahead of the newest changelog entry
        (a genuinely malformed or out-of-order changelog).
        """
        from pathlib import Path

        from .. import get_addon_version

        root = Path(__file__).resolve().parent.parent
        text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
        version = get_addon_version()
        if extract_section(version, text):
            return  # entry present -- nothing to tolerate

        newest = latest_version(text)
        self.assertTrue(newest, "CHANGELOG.md has no version sections at all")
        self.assertGreater(
            _semver(version),
            _semver(newest),
            f"CHANGELOG.md has no section for {version}, and it is not ahead of "
            f"the newest changelog entry {newest} (so this is not the normal "
            f"post-bump window -- the changelog is missing an entry it should have)",
        )
