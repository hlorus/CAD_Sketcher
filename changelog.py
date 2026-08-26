"""Parse ``CHANGELOG.md`` — the single source of change notes.

Shared, on purpose, by two consumers:

- the add-on's in-app "What's new" dialog, which imports :func:`extract_section`;
- the release workflow, via ``scripts/changelog_notes.py`` (excluded from the
  built extension), which imports the same function to prepend the matching
  section to the auto-generated GitHub release notes.

Kept dependency-free (standard library only) so it can be imported at runtime
without installing anything. This module is import-only — it has no
run-as-main entry point (extensions may not ship standalone-runnable files).
"""

import re

# Matches "## 0.3.0", "## [0.3.0]", "## v0.3.0", optionally followed by a date.
_HEADING = re.compile(r"^##\s+\[?v?([0-9]+\.[0-9]+\.[0-9]+)\]?")


def extract_section(version: str, text: str) -> str:
    """Return the notes under the ``## <version>`` heading (heading stripped).

    Matching is on the base ``X.Y.Z`` — any pre-release suffix on *version*
    (e.g. ``0.3.0-latest.8``) is ignored, so rolling builds resolve to their
    base version's entry. Returns ``""`` when there is no matching section.
    """
    base = version.split("-", 1)[0].strip()
    out = []
    capturing = False
    for line in text.splitlines():
        m = _HEADING.match(line)
        if m:
            if capturing:
                break  # reached the next version's heading
            capturing = m.group(1) == base
            continue
        if capturing:
            out.append(line)
    return "\n".join(out).strip()


def latest_version(text: str) -> str:
    """Return the newest ``X.Y.Z`` version heading, or ``""`` if there are none.

    The changelog lists releases newest-first (the release process guarantees
    this), so the first heading in document order is the newest. Used to tell a
    genuinely missing entry from the normal post-bump window where the manifest
    version leads the changelog.
    """
    for line in text.splitlines():
        m = _HEADING.match(line)
        if m:
            return m.group(1)
    return ""
