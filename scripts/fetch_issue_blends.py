#!/usr/bin/env python3
"""Harvest .blend files attached to CAD Sketcher issues and pull requests.

Users report bugs by attaching a .blend (sometimes zipped) to a GitHub issue.
Collecting those files gives migration and versioning code a corpus of real
user data to run against, which no hand-written fixture can imitate.

Run with system python (not Blender's) and an authenticated `gh` CLI:

    python3 scripts/fetch_issue_blends.py --out .bltest/corpus

Re-runs are cheap: files already present on disk are skipped.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

REPO = "hlorus/CAD_Sketcher"

# Attachment URL shapes GitHub has used over the years. The modern uploader
# writes /user-attachments/files/, older issues carry /<owner>/<repo>/files/
# links, and both can be served straight from objects.githubusercontent.com.
ATTACHMENT_RE = re.compile(
    r"https://(?:"
    r"github\.com/user-attachments/files/[^\s\"'<>)\]]+"
    r"|github\.com/[\w.-]+/[\w.-]+/files/[^\s\"'<>)\]]+"
    r"|objects\.githubusercontent\.com/[^\s\"'<>)\]]+"
    r")",
    re.IGNORECASE,
)

WANTED_SUFFIXES = (".blend", ".zip")
USER_AGENT = "CAD_Sketcher-corpus-fetcher/1.0"
# A courtesy pause between downloads so a few hundred files don't look like abuse.
DOWNLOAD_DELAY_S = 0.3


@dataclass
class Attachment:
    """One candidate attachment found in an issue body or comment."""

    issue_number: int
    issue_title: str
    issue_url: str
    issue_created_at: str
    url: str
    name: str

    @property
    def local_name(self) -> str:
        """Filename under the corpus directory, carrying the issue number."""
        return f"issue{self.issue_number:03d}_{self.name}"


def run_gh(args: list[str]) -> str:
    """Run a `gh` command and return its stdout, raising on failure."""
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def gh_api_paginated(endpoint: str) -> list[dict[str, Any]]:
    """Fetch every page of a list endpoint via `gh api --paginate`.

    `--slurp` wraps the pages into a single JSON array of arrays, which keeps
    the parsing honest without concatenating raw page bodies.
    """
    raw = run_gh(["api", "--paginate", "--slurp", endpoint])
    pages = json.loads(raw)
    items: list[dict[str, Any]] = []
    for page in pages:
        if isinstance(page, list):
            items.extend(page)
        elif isinstance(page, dict):
            items.append(page)
    return items


def attachment_name(url: str) -> str:
    """Best-effort original filename for an attachment URL."""
    path = url.split("?", 1)[0].rstrip("/")
    return urllib.parse.unquote(path.rsplit("/", 1)[-1])


def find_attachments(
    text: str | None,
    issue: dict[str, Any],
    seen: set[str],
) -> Iterator[Attachment]:
    """Yield .blend/.zip attachments mentioned in one body or comment."""
    if not text:
        return
    for url in ATTACHMENT_RE.findall(text):
        url = url.rstrip(".,);")
        name = attachment_name(url)
        if not name.lower().endswith(WANTED_SUFFIXES):
            continue
        if url in seen:
            continue
        seen.add(url)
        yield Attachment(
            issue_number=issue["number"],
            issue_title=issue.get("title") or "",
            issue_url=issue.get("html_url") or "",
            issue_created_at=issue.get("created_at") or "",
            url=url,
            name=name,
        )


def collect(limit: int | None) -> tuple[list[Attachment], int]:
    """Scan issues and pull requests, returning attachments and issues scanned."""
    issues = gh_api_paginated(
        f"repos/{REPO}/issues?state=all&per_page=100&sort=created&direction=desc"
    )
    if limit is not None:
        issues = issues[:limit]

    attachments: list[Attachment] = []
    seen: set[str] = set()
    for index, issue in enumerate(issues, start=1):
        found = list(find_attachments(issue.get("body"), issue, seen))
        # Fetching comments costs a request per issue, so only do it when the
        # issue actually has some.
        if issue.get("comments"):
            try:
                comments = gh_api_paginated(
                    f"repos/{REPO}/issues/{issue['number']}/comments?per_page=100"
                )
            except RuntimeError as exc:
                print(f"  ! comments for #{issue['number']}: {exc}", file=sys.stderr)
                comments = []
            for comment in comments:
                found.extend(find_attachments(comment.get("body"), issue, seen))
        if found:
            print(
                f"[{index}/{len(issues)}] #{issue['number']}: {len(found)} attachment(s)"
            )
        attachments.extend(found)
    return attachments, len(issues)


def download(url: str, dest: Path) -> int:
    """Download one URL to dest, returning the byte size written."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read()
    dest.write_bytes(data)
    return len(data)


def extract_blends(archive: Path, out_dir: Path, prefix: str) -> list[Path]:
    """Extract only the .blend members of a zip, dropping unrelated assets.

    Member names are flattened to a basename, which also neutralises any
    path-traversal ("../") or absolute-path entry in a hostile archive.
    """
    written: list[Path] = []
    try:
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                member = Path(info.filename.replace("\\", "/")).name
                if not member.lower().endswith(".blend") or not member:
                    continue
                # macOS zips carry an AppleDouble twin per file ("__MACOSX/._x.blend")
                # that is metadata, not a scene.
                if member.startswith("._"):
                    continue
                target = out_dir / f"{prefix}_{member}"
                if target.exists():
                    continue
                with zf.open(info) as src:
                    target.write_bytes(src.read())
                written.append(target)
    except (zipfile.BadZipFile, OSError) as exc:
        print(f"  ! bad zip {archive.name}: {exc}", file=sys.stderr)
    return written


def record_for(
    att: Attachment,
    local_name: str,
    size: int,
    archive: str | None = None,
) -> dict[str, Any]:
    """Build one manifest record for a file on disk."""
    record: dict[str, Any] = {
        "issue_number": att.issue_number,
        "issue_title": att.issue_title,
        "issue_url": att.issue_url,
        "issue_created_at": att.issue_created_at,
        "attachment_url": att.url,
        "local_name": local_name,
        "size": size,
    }
    if archive is not None:
        record["from_archive"] = archive
    return record


def records_for_archive(
    att: Attachment, out_dir: Path, stamp: Path
) -> list[dict[str, Any]]:
    """Rebuild manifest records for the .blend members of an already-harvested zip.

    The stamp lists the members that archive contributed, so two archives on the
    same issue each stay attributed to the right files.
    """
    try:
        members = json.loads(stamp.read_text()).get("members", [])
    except (OSError, ValueError):
        members = []
    records: list[dict[str, Any]] = []
    for member in members:
        path = out_dir / member
        if path.exists():
            records.append(
                record_for(att, member, path.stat().st_size, archive=att.local_name)
            )
    return records


def main() -> int:
    """Entry point: scan the repo, fetch attachments, write the manifest."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(".bltest/corpus"),
        help="target directory for the corpus (default: .bltest/corpus)",
    )
    parser.add_argument("--limit", type=int, help="stop after N issues")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="list what would be downloaded, download nothing",
    )
    args = parser.parse_args()

    attachments, scanned = collect(args.limit)
    print(f"\nscanned {scanned} issues, found {len(attachments)} attachment(s)")

    if args.dry_run:
        for att in attachments:
            print(f"  #{att.issue_number} {att.local_name}  <- {att.url}")
        return 0

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    downloaded = 0
    skipped = 0
    failed: list[str] = []

    for att in attachments:
        is_zip = att.name.lower().endswith(".zip")
        target = out_dir / att.local_name
        # A harvested zip leaves only a stamp behind (its .blend members are kept
        # separately), so the stamp is what makes a re-run skip it.
        stamp = out_dir / f"{att.local_name}.done"
        if target.exists() or (is_zip and stamp.exists()):
            skipped += 1
            if target.exists():
                records.append(record_for(att, att.local_name, target.stat().st_size))
            else:
                records.extend(records_for_archive(att, out_dir, stamp))
            continue
        try:
            size = download(att.url, target)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            # One dead link must not end the harvest.
            print(f"  ! {att.local_name}: {exc}", file=sys.stderr)
            failed.append(f"#{att.issue_number} {att.name} ({exc})")
            target.unlink(missing_ok=True)
            continue

        if is_zip:
            print(f"  + {att.local_name} ({size / 1024:.0f} KiB, archive)")
            members = extract_blends(target, out_dir, f"issue{att.issue_number:03d}")
            for blend in members:
                blend_size = blend.stat().st_size
                downloaded += 1
                print(f"    -> {blend.name} ({blend_size / 1024:.0f} KiB)")
                records.append(
                    record_for(att, blend.name, blend_size, archive=att.local_name)
                )
            target.unlink(missing_ok=True)
            stamp.write_text(
                json.dumps(
                    {"url": att.url, "members": [blend.name for blend in members]},
                    indent=2,
                )
                + "\n"
            )
        else:
            downloaded += 1
            print(f"  + {att.local_name} ({size / 1024:.0f} KiB)")
            records.append(record_for(att, att.local_name, size))

        time.sleep(DOWNLOAD_DELAY_S)

    total_bytes = sum(int(record["size"]) for record in records)
    manifest = out_dir / "manifest.json"
    manifest.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n")

    print(
        f"\nissues scanned: {scanned}\n"
        f"attachments found: {len(attachments)}\n"
        f"files downloaded: {downloaded}\n"
        f"files skipped (already present): {skipped}\n"
        f"failed: {len(failed)}\n"
        f"total size on disk: {total_bytes / 1024 / 1024:.1f} MiB\n"
        f"manifest: {manifest}"
    )
    for item in failed:
        print(f"  failed: {item}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
