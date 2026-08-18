"""Tests for the 'What's new' update-detection state machine.

Exercises ``_process_update`` (the pure decision function) rather than the
timer/popup wrapper, which no-ops in Blender's ``--background`` test runs.
"""

from unittest import TestCase

from ..base import whats_new as wn


class TestWhatsNewStateMachine(TestCase):
    def setUp(self):
        self.current = wn._current_version()
        self._seen = wn._seen_file()
        self._reset()

    def tearDown(self):
        self._reset()

    def _reset(self, value=None):
        self._seen.unlink(missing_ok=True)
        if value is not None:
            self._seen.write_text(value, encoding="utf-8")

    def test_first_run_records_silently(self):
        self._reset(None)  # no marker yet
        self.assertIsNone(wn._process_update(show_enabled=True))
        self.assertEqual(
            wn._read_seen(), self.current, "first run must record the version"
        )

    def test_version_change_announces_and_advances(self):
        # Force notes to exist so this exercises the announce/advance path
        # independently of whether the shipped changelog has an entry for the
        # current version yet (see test_version_without_notes_waits for the
        # no-notes branch). Otherwise the test breaks in the normal post-bump
        # window where the manifest leads the changelog.
        self._reset("0.0.1")
        original = wn._notes_for
        wn._notes_for = lambda version: "- Example note."
        try:
            self.assertEqual(wn._process_update(show_enabled=True), self.current)
            self.assertEqual(wn._read_seen(), self.current)
        finally:
            wn._notes_for = original

    def test_toggle_off_skips_dialog_but_still_advances(self):
        self._reset("0.0.1")
        original = wn._notes_for
        wn._notes_for = lambda version: "- Example note."
        try:
            self.assertIsNone(wn._process_update(show_enabled=False))
            self.assertEqual(
                wn._read_seen(), self.current, "marker must advance even when disabled"
            )
        finally:
            wn._notes_for = original

    def test_same_version_does_nothing(self):
        self._reset(self.current)
        self.assertIsNone(wn._process_update(show_enabled=True))
        self.assertEqual(wn._read_seen(), self.current)

    def test_wrap_reflows_paragraph_and_bullets_within_width(self):
        notes = (
            "The data model has been fundamentally reworked for a closer "
            "integration into Blender, better stability and performance.\n"
            "\n"
            "- A fairly long bullet that certainly exceeds the wrap width and "
            "must be split across more than one display line.\n"
            "- Short one."
        )
        maxc = 40
        lines = wn._wrap_lines(notes, maxc)
        # nothing exceeds the wrap width
        self.assertTrue(all(len(l) <= maxc for l in lines), lines)
        # the long bullet actually wrapped (more than 4 non-blank lines total)
        self.assertGreater(len([l for l in lines if l]), 4)
        # the blank line between paragraph and bullets is preserved as a break
        self.assertIn("", lines)
        # a continuation line of the bullet is indented (hanging indent)
        self.assertTrue(any(l.startswith("  ") for l in lines), lines)

    def test_real_changelog_fits_the_dialog_width(self):
        """Every line of the shipped notes must fit the dialog once wrapped."""
        notes = wn._notes_for(self.current)
        maxc = wn._max_chars(wn._DIALOG_WIDTH)
        for line in wn._wrap_lines(notes, maxc):
            self.assertLessEqual(len(line), maxc, f"line too wide: {line!r}")

    def test_version_without_notes_waits(self):
        """A version with no changelog entry (e.g. an in-dev 'latest' build) is
        neither announced nor recorded, so the announcement still happens once
        the notes are written."""
        original = wn._notes_for
        wn._notes_for = lambda version: ""
        try:
            self._reset("0.0.1")
            self.assertIsNone(wn._process_update(show_enabled=True))
            self.assertEqual(
                wn._read_seen(), "0.0.1", "marker must not advance without notes"
            )
        finally:
            wn._notes_for = original
