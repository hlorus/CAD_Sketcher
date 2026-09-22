"""GUI smoke test: exercise the paths that only exist with a real window.

Draw handlers, gizmos and view-layer operations do not run in ``--background``,
so the headless suite cannot see a whole class of failure: a missing entry in a
pick-id keyed map raising mid-draw, or ``hide_set`` refusing an object that is not
in the view layer yet. Both of those shipped as crashes before this existed.

Run it inside a private headless compositor so no window appears (see CLAUDE.md):

    dbus-run-session -- mutter --headless --wayland-display=smoke &
    WAYLAND_DISPLAY=smoke blender --factory-startup --python testing/gui_smoke.py

It prints SMOKE OK / SMOKE FAILED and exits non-zero on failure. Any Python
traceback printed by a draw handler is caught too: the harness greps stderr.
"""

import sys
import traceback

import bpy

TARGET = "bl_ext.user_default.CAD_Sketcher"


def _enable_addon():
    """Enable the installed extension: --factory-startup starts with none on."""
    import addon_utils

    for module in addon_utils.modules():
        if module.__name__.endswith(".CAD_Sketcher") and module.__name__ != TARGET:
            try:
                addon_utils.disable(module.__name__)
            except Exception:
                pass
    addon_utils.enable(TARGET, default_set=True)


_enable_addon()

_FAILURES = []


def _check(label):
    """Run a step, recording rather than raising so later steps still run."""

    def decorator(fn):
        try:
            fn()
            print(f"SMOKE step ok: {label}")
        except Exception:
            _FAILURES.append(label)
            print(f"SMOKE step FAILED: {label}", file=sys.stderr)
            traceback.print_exc()
        return fn

    return decorator


def _redraw():
    """Force a real draw so draw handlers and gizmos actually run."""
    bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)


def _view3d_context():
    """Override targeting the first 3D viewport, for operators that need one."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            for region in area.regions:
                if region.type == "WINDOW":
                    return {
                        "window": window,
                        "area": area,
                        "region": region,
                        "space_data": area.spaces.active,
                    }
    return None


def main():
    override = _view3d_context()
    if override is None:
        print("SMOKE FAILED: no 3D viewport", file=sys.stderr)
        sys.exit(1)

    # By the installed module path, never through an alias: importing the package
    # under a second name gives its submodules a different ``__package__``, and
    # the preferences lookup (keyed by package name) then fails.
    import importlib

    add_sketch = importlib.import_module(f"{TARGET}.operators.add_sketch")
    curve_ref = importlib.import_module(f"{TARGET}.model.curve_ref")
    curve_data = importlib.import_module(f"{TARGET}.utilities.curve_data")
    solver = importlib.import_module(f"{TARGET}.curve_solver")
    extrude_nodes = importlib.import_module(f"{TARGET}.utilities.extrude_nodes")
    part = importlib.import_module(f"{TARGET}.utilities.part")
    sketch_ref = importlib.import_module(f"{TARGET}.model.sketch_ref")
    workplane = importlib.import_module(f"{TARGET}.utilities.workplane")

    build_sketch_on_workplane = add_sketch.build_sketch_on_workplane
    create_assembly = part.create_assembly
    ensure_part_planes = part.ensure_part_planes
    join_assembly = part.join_assembly
    mark_part_root = part.mark_part_root
    settle_membership = part.settle_membership
    ensure_origin_workplane_empties = workplane.ensure_origin_workplane_empties

    with bpy.context.temp_override(**override):
        context = bpy.context

        @_check("origin planes + draw")
        def _():
            ensure_origin_workplane_empties(context)
            bpy.ops.wm.tool_set_by_id(name="sketcher.slvs_add_sketch")
            _redraw()

        @_check("sketch on a datum plane")
        def _():
            sketch = build_sketch_on_workplane(context, context.scene.sketcher.wp_xy)
            globals()["sketch_obj"] = sketch.target_object
            _redraw()

        @_check("part planes drawn and picked")
        def _():
            root = globals()["sketch_obj"]
            mark_part_root(root)
            root.select_set(True)
            context.view_layer.objects.active = root
            planes = ensure_part_planes(context, root)
            _redraw()
            # Sketching on the part's own plane: the pick path a click takes.
            build_sketch_on_workplane(context, planes[0])
            _redraw()

        @_check("assembly created and drawn")
        def _():
            root = globals()["sketch_obj"]
            assembly = create_assembly(context)
            join_assembly(assembly, root)
            _redraw()

        @_check("cutter membership settled")
        def _():
            cutter = build_sketch_on_workplane(context, context.scene.sketcher.wp_xz)
            settle_membership(cutter.target_object, [globals()["sketch_obj"]])
            _redraw()

        @_check("extrude settles membership end to end")
        def _():
            # The whole chain in one go: geometry, a real extrude through the
            # operator, auto-boolean target detection against evaluated geometry,
            # and the membership that follows from what it cut. Only reachable
            # with a window: detection needs the solid evaluated.
            def rectangle(sketch, half, offset=(0.0, 0.0)):
                ox, oy = offset
                corners = [
                    (ox - half, oy - half),
                    (ox + half, oy - half),
                    (ox + half, oy + half),
                    (ox - half, oy + half),
                ]
                points = [curve_ref.PointRef.create(sketch, c) for c in corners]
                for i in range(4):
                    curve_ref.LineRef.create(sketch, points[i], points[(i + 1) % 4])
                solver.solve_system(context, sketch=sketch)
                curve_data.refresh_curve_geometry(sketch)

            base = build_sketch_on_workplane(context, context.scene.sketcher.wp_xy)
            rectangle(base, 1.0)
            body = base.target_object
            context.view_layer.update()
            # The tool builds its node group in init(), which only the modal
            # invoke path runs; do it here so the operator can be executed
            # straight through instead of waiting for mouse input.
            extrude_nodes.build_extrude_node_group()
            extrude_nodes.ensure_extrude_edge_walls(
                bpy.data.node_groups.get(extrude_nodes.EXTRUDE_NODE_GROUP)
            )
            bpy.ops.view3d.slvs_node_extrude(target_name=body.name, offset=1.0)
            _redraw()
            assert part.is_part_root(body), "a standalone solid must root a part"

            # A second solid cutting it must become a feature of the first part
            # and hide itself. The target list is stubbed rather than detected:
            # a sketch's solid does not evaluate to geometry in this harness, so
            # the overlap test would find nothing. Everything after detection --
            # the booleans, the membership, the display, the collections -- is the
            # tool's real path.
            cutter_sketch = build_sketch_on_workplane(
                context, context.scene.sketcher.wp_xy
            )
            rectangle(cutter_sketch, 0.4)
            cutter = cutter_sketch.target_object
            context.view_layer.update()

            boolean_targets = importlib.import_module(
                f"{TARGET}.utilities.boolean_targets"
            )
            detect = boolean_targets.detect_targets
            boolean_targets.detect_targets = lambda *a, **k: [body]
            try:
                bpy.ops.view3d.slvs_node_extrude(target_name=cutter.name, offset=2.0)
            finally:
                boolean_targets.detect_targets = detect
            _redraw()
            assert part.part_root_of(cutter) == body, (
                f"cutter joined {part.part_root_of(cutter)}, expected {body.name}"
            )
            assert not cutter.visible_get(), "a cutter doing its job must be hidden"

        @_check("sketch activated and drawn")
        def _():
            set_active_sketch = sketch_ref.set_active_sketch

            set_active_sketch(context, globals()["sketch_obj"])
            _redraw()
            set_active_sketch(context, None)
            _redraw()

    if _FAILURES:
        print(f"SMOKE FAILED: {', '.join(_FAILURES)}", file=sys.stderr)
        sys.exit(1)
    print("SMOKE OK")


try:
    main()
finally:
    bpy.ops.wm.quit_blender()
