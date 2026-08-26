#!/usr/bin/env python3
"""Print the CHANGELOG.md section for a version (release-workflow helper).

Lives under scripts/ (excluded from the built extension) so the shipped
``changelog`` module stays a pure importable library with no run-as-main
segment. Run from the repository root with it on the path, e.g.:

    PYTHONPATH=. python3 scripts/changelog_notes.py <version> [changelog_path]

Exits 1 when there is no matching section (so the caller can distinguish a
missing entry from a successful extraction).
"""

import sys

from changelog import extract_section

if len(sys.argv) < 2:
    sys.stderr.write("usage: changelog_notes.py <version> [changelog_path]\n")
    raise SystemExit(2)

version = sys.argv[1]
path = sys.argv[2] if len(sys.argv) > 2 else "CHANGELOG.md"
with open(path, encoding="utf-8") as f:
    section = extract_section(version, f.read())

if not section:
    sys.stderr.write(f"No CHANGELOG entry for version '{version}' in {path}\n")
    raise SystemExit(1)

sys.stdout.write(section + "\n")
