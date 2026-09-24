"""Run ``Update File`` over a pile of real .blend files and check what came back.

The fixtures in ``testing/fixtures`` are small and deliberate; real user files
are neither, and every migration bug so far turned up in one of them. This runs
the update on each file in a corpus and asserts the things a user would notice:

- it finishes at all (a crash in a depsgraph handler takes Blender with it),
- every sketch ends up on a body,
- nothing changed visibility, in particular nothing hidden came back visible,
- the geometry each sketch produced is still there, in the same place,
- running the update a second time does nothing.

Files are not committed: point it at a directory of your own (see
``scripts/fetch_issue_blends.py`` for one that fills ``.bltest/corpus`` from the
files users attached to issues).

Each file is opened in its own Blender process, so one bad file reports as a
crash instead of ending the run::

    python3 scripts/migration_smoke.py .bltest/corpus \\
        --blender "flatpak run --filesystem=$PWD org.blender.Blender" \\
        --resources .bltest/res

The add-on under test is whatever ``bl_ext.user_default.CAD_Sketcher`` resolves
to in that resources directory, so build and install your worktree there first
(see CLAUDE.md).
"""

from __future__ import annotations

import json
import os
import sys

WORKER_FLAG = "--run-one"
RESULT_PREFIX = "SMOKE "
# Bounds are compared in the file's own units, which run to hundreds of
# millimetres, so the tolerance is relative with a small absolute floor.
BOUNDS_TOLERANCE = 1e-3
VERTEX_TOLERANCE = 0.0


# --------------------------------------------------------------------------
# worker: runs inside Blender, one file per process
# --------------------------------------------------------------------------


def _visibility(obj) -> list:
    """Whether the object shows in the viewport and in a render.

    Not the raw flags: which of ``hide_viewport`` and the eye is used is an
    implementation detail the update is allowed to change, but whether the user
    can see the thing is not.
    """
    try:
        eye = bool(obj.hide_get())
    except RuntimeError:
        eye = False  # not in this view layer
    return [not (bool(obj.hide_viewport) or eye), not bool(obj.hide_render)]


def _show(visibility: list) -> str:
    """A visibility pair as something readable in a report line."""
    viewport, render = visibility
    return (
        f"{'viewport' if viewport else 'hidden'}/{'render' if render else 'no-render'}"
    )


def _measure(context) -> dict:
    """Evaluated vertex count and world bounds per object, keyed by pointer.

    Read through the depsgraph instances: a sketch that still carries its own
    modifiers is a Curves object whose mesh output ``to_mesh`` refuses to hand
    over, and the instance geometry is the only way to see it.
    """
    from mathutils import Vector

    depsgraph = context.evaluated_depsgraph_get()
    depsgraph.update()
    out: dict[int, dict] = {}
    for instance in depsgraph.object_instances:
        origin = instance.parent if instance.is_instance else instance.object
        if origin is None:
            continue
        try:
            key = origin.original.as_pointer()
        except (AttributeError, ReferenceError):
            continue
        try:
            mesh = instance.object.to_mesh()
        except RuntimeError:
            continue  # curves, empties, anything with no mesh to give
        if mesh is None:
            continue
        record = out.setdefault(key, {"verts": 0, "lo": [1e18] * 3, "hi": [-1e18] * 3})
        record["verts"] += len(mesh.vertices)
        for vertex in mesh.vertices:
            world = instance.matrix_world @ Vector(vertex.co)
            for i in range(3):
                record["lo"][i] = min(record["lo"][i], world[i])
                record["hi"][i] = max(record["hi"][i], world[i])
        instance.object.to_mesh_clear()
    return out


def _union(records) -> dict:
    """One box around everything measured, for files with nothing to pair up."""
    total = {"verts": 0, "lo": [1e18] * 3, "hi": [-1e18] * 3}
    for record in records:
        total["verts"] += record["verts"]
        for i in range(3):
            total["lo"][i] = min(total["lo"][i], record["lo"][i])
            total["hi"][i] = max(total["hi"][i], record["hi"][i])
    return total if total["verts"] else {}


def _dims(record) -> list:
    return [record["hi"][i] - record["lo"][i] for i in range(3)]


def _close(before, after) -> bool:
    """Same geometry, allowing for float drift in the transform chain."""
    if before["verts"] != after["verts"]:
        return abs(before["verts"] - after["verts"]) <= VERTEX_TOLERANCE
    for a, b in zip(_dims(before), _dims(after)):
        if abs(a - b) > max(BOUNDS_TOLERANCE, abs(a) * BOUNDS_TOLERANCE):
            return False
    return True


def _enable_addon() -> str:
    import addon_utils

    target = "bl_ext.user_default.CAD_Sketcher"
    for module in addon_utils.modules():
        if module.__name__.endswith(".CAD_Sketcher") and module.__name__ != target:
            addon_utils.disable(module.__name__)
    addon_utils.enable(target, default_set=True)
    module = next(m for m in addon_utils.modules() if m.__name__ == target)
    return module.__file__


def run_one(path: str) -> dict:
    """Update one file and report what the update did to it."""
    import bpy

    addon_path = _enable_addon()
    from bl_ext.user_default.CAD_Sketcher.model.sketch_ref import get_sketches
    from bl_ext.user_default.CAD_Sketcher.utilities.body import body_of, sketch_of
    from bl_ext.user_default.CAD_Sketcher.utilities.collections import is_editable
    from bl_ext.user_default.CAD_Sketcher.utilities.migrate import scene_needs_migration

    result = {"file": os.path.basename(path), "addon": addon_path, "problems": []}
    bpy.ops.wm.open_mainfile(filepath=path)
    context = bpy.context

    sketches_before = list(get_sketches(context))
    legacy = scene_needs_migration(context)
    result["sketches"] = len(sketches_before)
    result["legacy"] = bool(legacy)
    result["objects_before"] = len(bpy.data.objects)
    if not sketches_before and not legacy:
        result["skipped"] = "nothing of ours in it"
        return result

    # Keyed by pointer: migration renames objects, so names identify nothing.
    was = {
        o.as_pointer(): {"name": o.name, "vis": _visibility(o)}
        for o in bpy.data.objects
    }
    geometry_before = _measure(context)
    editable = {
        s.target_object.as_pointer(): s.target_object
        for s in sketches_before
        if is_editable(s.target_object)
    }

    bpy.ops.view3d.slvs_migrate_legacy()

    geometry_after = _measure(context)
    result["objects_after"] = len(bpy.data.objects)

    bodies = {}
    for sketch in get_sketches(context):
        obj = sketch.target_object
        key = obj.as_pointer()
        if key not in editable:
            continue
        body = body_of(obj)
        if body is None:
            result["problems"].append(f"no body: {obj.name}")
            continue
        bodies[key] = body
    result["bodies"] = len(bodies)

    # Visibility: a sketch hands its own visibility to its body (the body is
    # what the user now sees), and everything else keeps what it had.
    for obj in bpy.data.objects:
        key = obj.as_pointer()
        if key not in was or key in bodies:
            continue  # created by the update, or a sketch the body speaks for
        now = _visibility(obj)
        if now != was[key]["vis"] and sketch_of(obj) is None:
            result["problems"].append(
                f"visibility changed: {was[key]['name']} "
                f"{_show(was[key]['vis'])} -> {_show(now)}"
            )
    for key, body in bodies.items():
        wanted = was[key]["vis"]
        got = _visibility(body)
        if got != wanted:
            result["problems"].append(
                f"body visibility: {body.name} is {_show(got)}, "
                f"sketch was {_show(wanted)}"
            )

    # An entity-era file has no sketches yet to compare one by one, so the check
    # there is that the part as a whole still occupies the same space.
    before_all = _union(geometry_before.values())
    after_all = _union(geometry_after.values())
    if before_all and after_all:
        result["scene_verts"] = [before_all["verts"], after_all["verts"]]
        for axis, (a, b) in enumerate(zip(_dims(before_all), _dims(after_all))):
            if abs(a - b) > max(0.5, abs(a) * 0.01):
                result["problems"].append(
                    f"scene bounds moved on {'xyz'[axis]}: {a:.1f} -> {b:.1f}"
                )
        if after_all["verts"] < before_all["verts"] / 2:
            result["problems"].append(
                f"geometry mostly gone: {before_all['verts']} -> {after_all['verts']} verts"
            )
    elif before_all and not after_all:
        result["problems"].append("all geometry gone")

    # Geometry: what the sketch used to evaluate to is what its body must.
    for key, body in bodies.items():
        before = geometry_before.get(key)
        after = geometry_after.get(body.as_pointer())
        if before is None and after is None:
            continue
        if before is None or after is None:
            state = "gained" if before is None else "lost"
            result["problems"].append(f"geometry {state}: {body.name}")
            continue
        if not _close(before, after):
            result["problems"].append(
                f"geometry changed: {body.name} "
                f"{before['verts']}v {[round(d, 2) for d in _dims(before)]} -> "
                f"{after['verts']}v {[round(d, 2) for d in _dims(after)]}"
            )

    # A second update is meant to find nothing left to do.
    names = sorted(o.name for o in bpy.data.objects)
    bpy.ops.view3d.slvs_migrate_legacy()
    again = sorted(o.name for o in bpy.data.objects)
    if again != names:
        added = sorted(set(again) - set(names))
        result["problems"].append(
            f"not idempotent: {len(again) - len(names)} objects, {added[:5]}"
        )

    return result


def worker_main() -> int:
    import bpy

    path = sys.argv[sys.argv.index(WORKER_FLAG) + 1]
    try:
        result = run_one(path)
    except Exception as error:  # a failure here is a result, not a traceback
        result = {
            "file": os.path.basename(path),
            "problems": [f"{type(error).__name__}: {error}"],
        }
    print(RESULT_PREFIX + json.dumps(result))
    sys.stdout.flush()
    bpy.ops.wm.quit_blender()
    return 0


# --------------------------------------------------------------------------
# driver: runs under system python, one Blender per file
# --------------------------------------------------------------------------


def collect_files(paths: list) -> list:
    """Every .blend under the given files and directories, sorted by name."""
    found = []
    for path in paths:
        if os.path.isdir(path):
            for root, _, names in os.walk(path):
                found += [os.path.join(root, n) for n in names if n.endswith(".blend")]
        elif path.endswith(".blend"):
            found.append(path)
    return sorted(set(found))


def driver_main() -> int:
    import argparse
    import shlex
    import subprocess

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", default=[".bltest/corpus"])
    parser.add_argument(
        "--blender",
        default=os.environ.get("CAD_SKETCHER_BLENDER", "blender"),
        help="command that starts Blender, quoted if it has arguments",
    )
    parser.add_argument(
        "--resources",
        default=os.environ.get("BLENDER_USER_RESOURCES"),
        help="BLENDER_USER_RESOURCES holding the build under test",
    )
    parser.add_argument("--timeout", type=int, default=300, help="seconds per file")
    parser.add_argument("--limit", type=int, help="stop after this many files")
    args = parser.parse_args()

    files = collect_files(args.paths or [".bltest/corpus"])[: args.limit]
    if not files:
        print("no .blend files found")
        return 1

    env = dict(os.environ)
    if args.resources:
        env["BLENDER_USER_RESOURCES"] = args.resources

    passed = failed = crashed = skipped = 0
    for path in files:
        command = shlex.split(args.blender) + [
            "--background",
            "--factory-startup",
            "--python",
            os.path.abspath(__file__),
            "--",
            WORKER_FLAG,
            os.path.abspath(path),
        ]
        name = os.path.basename(path)
        try:
            done = subprocess.run(
                command, env=env, capture_output=True, text=True, timeout=args.timeout
            )
        except subprocess.TimeoutExpired:
            crashed += 1
            print(f"TIMEOUT  {name}")
            continue

        line = next(
            (ln for ln in done.stdout.splitlines() if ln.startswith(RESULT_PREFIX)),
            None,
        )
        if line is None:
            crashed += 1
            tail = (done.stderr or done.stdout).strip().splitlines()[-1:] or [""]
            print(f"CRASH    {name} (exit {done.returncode}) {tail[0][:120]}")
            continue

        result = json.loads(line[len(RESULT_PREFIX) :])
        if result.get("skipped"):
            skipped += 1
            print(f"SKIP     {name}: {result['skipped']}")
        elif result["problems"]:
            failed += 1
            era = "entity-era" if result.get("legacy") else "curves-era"
            print(f"FAIL     {name}: {era}, {result['sketches']} sketches before")
            for problem in result["problems"]:
                print(f"           {problem}")
        else:
            passed += 1
            era = "entity-era" if result.get("legacy") else "curves-era"
            print(
                f"ok       {name}: {era}, {result.get('bodies', 0)} bodies, "
                f"{result['objects_before']} -> {result['objects_after']} objects"
            )

    print(
        f"\n{len(files)} files: {passed} ok, {failed} failed, "
        f"{crashed} crashed, {skipped} skipped"
    )
    return 1 if (failed or crashed) else 0


if WORKER_FLAG in sys.argv:
    sys.exit(worker_main())
elif __name__ == "__main__":
    sys.exit(driver_main())
