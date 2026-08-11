"""Render a Markdown perf-delta table from two ``perf_harness.py --json`` runs.

Used by the perf CI workflow to comment head-vs-base on a PR. Plain Python (no
Blender), reads two JSON files and writes Markdown to stdout:

    python3 scripts/perf_compare.py base.json head.json

``base.json`` is optional -- if it's missing or unparseable (e.g. the base
commit predates the harness), only the head numbers are shown.

Two metric kinds, distinguished by the ``_ms`` suffix:
  * ``*_ms``  wall-clock, machine-dependent -- shown as an informational trend.
  * others    op-counts, deterministic -- an increase is a real regression and
              is flagged.
"""

import json
import sys


def _load(path):
    try:
        with open(path) as f:
            return json.load(f).get("metrics", {})
    except (OSError, ValueError):
        return None


def _fmt(v):
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def main():
    base_path, head_path = sys.argv[1], sys.argv[2]
    base = _load(base_path)
    head = _load(head_path)

    if not head:
        print("Perf harness produced no head metrics.")
        return 0

    lines = ["### ⏱️ Performance", ""]
    if base is None:
        lines += [
            "_No comparable base metrics (the base commit predates the perf "
            "harness); showing head values only._",
            "",
            "| metric | head |",
            "| --- | ---: |",
        ]
        for k in sorted(head):
            lines.append(f"| `{k}` | {_fmt(head[k])} |")
        print("\n".join(lines))
        return 0

    lines += [
        "| metric | base | head | Δ | |",
        "| --- | ---: | ---: | ---: | :-- |",
    ]
    regressed = []
    for k in sorted(set(base) | set(head)):
        b = base.get(k)
        h = head.get(k)
        if b is None or h is None:
            lines.append(
                f"| `{k}` | {_fmt(b) if b is not None else '—'} "
                f"| {_fmt(h) if h is not None else '—'} | new/removed | |"
            )
            continue
        is_count = not k.endswith("_ms")
        if is_count:
            # Deterministic: any increase is a real regression.
            delta = h - b
            flag = "🔴" if delta > 0 else ("🟢" if delta < 0 else "")
            if delta > 0:
                regressed.append(k)
            lines.append(f"| `{k}` | {b} | {h} | {delta:+d} | {flag} |")
        else:
            # Wall-clock: informational; big swings are runner noise.
            pct = (h - b) / b * 100 if b else 0.0
            flag = "≈ (noisy)"
            lines.append(f"| `{k}` | {_fmt(b)} | {_fmt(h)} | {pct:+.0f}% | {flag} |")

    lines.append("")
    if regressed:
        lines.append(
            "🔴 **Op-count regression** in "
            + ", ".join(f"`{k}`" for k in regressed)
            + " — a cache/fast-path is being bypassed. `_ms` deltas are runner "
            "noise; the op-counts are the signal."
        )
    else:
        lines.append(
            "🟢 No op-count regressions. (`_ms` deltas are runner noise — the "
            "op-counts are the deterministic signal.)"
        )
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
