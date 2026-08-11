"""Headless performance harness for the interaction hot paths.

Builds sketches of increasing size and times the work that runs *per user
interaction* -- the paths behind the slowdown reported in issue #342 ("every
operation takes seconds, worse over time, fine when the sketch is hidden"):

    render_data.build   the core of both picking (per mouse-move) and the
                        overlay draw (per redraw); runs twice per frame
    solve_system        fires on every edit
    refresh_curve_geometry  rebuilds the generated mesh after a solve
    validate_all_sketches   the depsgraph self-heal pass

Run:  blender --background --python scripts/perf_harness.py
  --profile   also cProfile render_data.build at the largest size
  --json      emit machine-readable metrics (for the perf-delta CI comment)
              instead of the human table

Two kinds of metric are reported:
  * wall-clock ms  -- machine-dependent; a useful trend, not a hard gate.
  * op-counts      -- deterministic (identical on every machine): how many times
                      a hot function runs in a fixed scenario. These are the real
                      regression signal -- e.g. a warm build should do ZERO hex
                      conversions, and 20 hover picks should trigger ONE build.
"""

import cProfile
import io
import json
import pstats
import sys
import time

import addon_utils
import bpy

SIZES = (10, 25, 50, 100, 200)
# Size used for the single-number JSON metrics (a mid-size sketch: big enough to
# be meaningful, small enough to keep the CI job fast).
JSON_SIZE = 100
PROFILE = "--profile" in sys.argv
JSON = "--json" in sys.argv


def _enable():
    for mod in addon_utils.modules():
        if mod.__name__.split(".")[-1] == "CAD_Sketcher":
            addon_utils.enable(mod.__name__, default_set=True)
            return mod.__name__
    raise SystemExit("CAD_Sketcher not found -- is it installed?")


PKG = _enable()
M = sys.modules[PKG]
sr = M.model.sketch_ref
cr = M.model.curve_ref
cd = M.utilities.curve_data
rd = M.drawing.render_data
picking = M.drawing.picking
solve = M.curve_solver.solve_system

import importlib  # noqa: E402

validate = importlib.import_module(PKG + ".utilities.validate")


class _StubTheme:
    """Colours build() reads; values are irrelevant to timing."""

    default = selected = selected_highlight = highlight = (1, 1, 1, 1)
    fixed = inactive = inactive_selected = (1, 1, 1, 1)


def _clear():
    for o in list(bpy.data.objects):
        if o.type in ("CURVES", "EMPTY"):
            bpy.data.objects.remove(o, do_unlink=True)


def _new_sketch():
    ctx = bpy.context
    ents = ctx.scene.sketcher.entities
    ents.ensure_origin_elements(ctx)
    esk = ents.add_sketch(ents.origin_plane_XY)
    cd.ensure_sketch_curve_object(esk)
    sr.stamp_sketch_props(esk.target_object)
    return sr.Sketch(esk.target_object)


def _build_chain(sketch, n):
    """A connected chain of n distance-constrained segments (real solver work,
    real shared junctions)."""
    import math

    sc = sketch.constraints
    with cd.batch_update(sketch):
        pts = [cr.PointRef.create(sketch, (0, 0), fixed=True)]
        for i in range(1, n + 1):
            pts.append(
                cr.PointRef.create(
                    sketch, (math.cos(i) * i * 0.1, math.sin(i) * i * 0.1)
                )
            )
        lines = [cr.LineRef.create(sketch, pts[i], pts[i + 1]) for i in range(n)]
    for ln in lines:
        sc.add_distance(init=True, curve_id_1=ln.curve_id)
    return len(sketch.target_object.data.curves)


def _timeit(fn, iters):
    fn()  # warm
    t = time.perf_counter()
    for _ in range(iters):
        fn()
    return (time.perf_counter() - t) / iters * 1000  # ms/call


def _call_count(fn, iters, func_name):
    """How many times ``func_name`` runs while calling ``fn`` ``iters`` times.

    Deterministic and machine-independent -- the metric the CI guard relies on.
    Assumes the relevant caches are already warm (call fn once before this).
    """
    pr = cProfile.Profile()
    pr.enable()
    for _ in range(iters):
        fn()
    pr.disable()
    total = 0
    for (_f, _l, name), (_cc, nc, *_rest) in pstats.Stats(pr).stats.items():
        if name == func_name:
            total += nc
    return total


def _safe(metrics, key, thunk):
    """Record ``metrics[key] = thunk()``, but skip the metric if the code path
    it probes doesn't exist yet.

    The CI benches both the PR head *and* its base with this harness. A base
    commit may predate the optimization a given metric guards (e.g. the picking
    cache), so probing it would raise -- we omit the metric there rather than
    crash, and ``perf_compare.py`` shows it as new on the head side.
    """
    try:
        metrics[key] = thunk()
    except Exception as exc:  # pragma: no cover - version-robustness only
        print(f"skip metric {key!r}: {exc}", file=sys.stderr)


def _table():
    ts = _StubTheme()
    header = f"{'N_seg':>6} {'curves':>7} {'build':>8} {'solve':>8} {'refresh':>8} {'validate':>9}"
    print(header + "   (ms/call)")
    last_sketch = None
    for n in SIZES:
        _clear()
        sk = _new_sketch()
        ncur = _build_chain(sk, n)
        solve(bpy.context, sketch=sk)
        scene = bpy.context.scene
        b = _timeit(lambda: rd.build(sk, ts, True), 30)
        s = _timeit(lambda: solve(bpy.context, sketch=sk), 10)
        r = _timeit(lambda: cd.refresh_curve_geometry(sk), 10)
        v = _timeit(lambda: validate.validate_all_sketches(scene), 10)
        print(f"{n:>6} {ncur:>7} {b:>8.2f} {s:>8.2f} {r:>8.2f} {v:>9.2f}")
        last_sketch = sk

    if PROFILE and last_sketch is not None:
        print(f"\n=== cProfile: render_data.build (N={SIZES[-1]}) ===")
        pr = cProfile.Profile()
        pr.enable()
        for _ in range(50):
            rd.build(last_sketch, ts, True)
        pr.disable()
        buf = io.StringIO()
        pstats.Stats(pr, stream=buf).sort_stats("tottime").print_stats(12)
        print("\n".join(buf.getvalue().splitlines()[:20]))


def _metrics():
    """Collect the JSON metrics at a single representative size."""
    ts = _StubTheme()
    _clear()
    sk = _new_sketch()
    _build_chain(sk, JSON_SIZE)
    solve(bpy.context, sketch=sk)
    sr.set_active_sketch(bpy.context, sk.target_object)

    metrics = {}

    # -- wall-clock (informational trend; machine-dependent) --
    metrics["build_ms"] = round(_timeit(lambda: rd.build(sk, ts, True), 30), 4)
    metrics["solve_ms"] = round(_timeit(lambda: solve(bpy.context, sketch=sk), 10), 4)
    metrics["refresh_ms"] = round(_timeit(lambda: cd.refresh_curve_geometry(sk), 10), 4)

    # -- op-counts (deterministic; the real regression signal) --
    # Each is measured from a warm cache (refresh above invalidated it), so it
    # reflects steady-state interaction. A warm build/solve must do ZERO hex
    # conversions -- read_uuid_list caches them; if that breaks, the count jumps
    # to ~one-per-curve-per-call.
    rd.build(sk, ts, True)  # warm
    _safe(
        metrics,
        "build_hex_calls",
        lambda: _call_count(lambda: rd.build(sk, ts, True), 10, "_pairs_to_hex"),
    )
    solve(bpy.context, sketch=sk)  # warm
    _safe(
        metrics,
        "solve_hex_calls",
        lambda: _call_count(lambda: solve(bpy.context, sketch=sk), 5, "_pairs_to_hex"),
    )

    # 20 hovers on unchanged geometry must trigger ONE extraction (the first),
    # not 20 -- the picking cache. If it breaks, this jumps to 20. (No cache on a
    # pre-optimization base: _active_data rebuilds each hover, so it reads ~20.)
    def _hover20():
        if hasattr(picking, "_pick_cache"):
            picking._pick_cache.clear()
        return _call_count(lambda: picking._active_data(bpy.context), 20, "build")

    _safe(metrics, "hover20_build_calls", _hover20)

    # A solve resolves segment endpoints from a position map, not a PointRef
    # (double curve-data resolve) each. If rebuild_segments reverts to per-
    # endpoint PointRefs, get_curve_data calls jump ~2x the segment count.
    solve(bpy.context, sketch=sk)  # warm
    _safe(
        metrics,
        "solve_curve_lookups",
        lambda: _call_count(lambda: solve(bpy.context, sketch=sk), 3, "get_curve_data"),
    )

    # A 2D draw operator's per-mouse-move undo snapshot is scoped to the active
    # sketch and must NOT re-serialize the whole scene. Add a second sketch so a
    # regression to the full-scene snapshot is visible, then count scene_to_dict
    # calls in one snapshot -- 0 when scoped, 1+ if it reverts.
    def _draw_snapshot_scene_calls():
        sk2 = _new_sketch()
        _build_chain(sk2, 20)
        sr.set_active_sketch(bpy.context, sk.target_object)
        op2d = importlib.import_module(PKG + ".operators.base_2d")
        probe = op2d.Operator2d.__new__(op2d.Operator2d)
        probe.create_snapshot(bpy.context)  # warm
        return _call_count(
            lambda: probe.create_snapshot(bpy.context), 5, "scene_to_dict"
        )

    _safe(metrics, "draw_snapshot_scene_calls", _draw_snapshot_scene_calls)

    return {"size": JSON_SIZE, "metrics": metrics}


def _json_out_path():
    """Optional file path after ``--json`` (Blender/addon logging pollutes
    stdout, so CI captures the JSON from a file instead)."""
    args = sys.argv[sys.argv.index("--json") + 1 :]
    for a in args:
        if not a.startswith("-"):
            return a
    return None


def main():
    if JSON:
        result = _metrics()
        out = _json_out_path()
        if out:
            with open(out, "w") as f:
                json.dump(result, f, indent=2)
            print(f"perf metrics written to {out}")
        else:
            json.dump(result, sys.stdout, indent=2)
            sys.stdout.write("\n")
    else:
        _table()


if __name__ == "__main__":
    main()
