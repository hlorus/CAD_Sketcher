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
                        # Screen-space picking (workplane and axis hit tests)
                        # reads it; without it they find nothing at all.
                        "region_data": area.spaces.active.region_3d,
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
    body_mod = importlib.import_module(f"{TARGET}.utilities.body")
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

        @_check("revolve axes drawn and picked")
        def _():
            from mathutils import Vector

            workplane_mod = importlib.import_module(f"{TARGET}.utilities.workplane")
            global_data = importlib.import_module(f"{TARGET}.global_data")
            root = globals()["sketch_obj"]
            ensure_part_planes(context, root)
            root.select_set(True)
            context.view_layer.objects.active = root

            # What the Axis state switches on: the pass runs for real.
            global_data.axis_picker = True
            _redraw()
            plane, index, pick_id = next(
                iter(workplane_mod.iter_axis_candidates(context))
            )
            # What the hover gizmo publishes on a mouse-move over an axis: the
            # cursor lands on the frame's origin, where all three cross.
            from mathutils import Vector as _V

            object_hover = importlib.import_module(f"{TARGET}.gizmos.object_hover")
            from bpy_extras.view3d_utils import location_3d_to_region_2d

            view = _view3d_context()
            region = view["region"]
            rv3d = view["space_data"].region_3d
            start, _end = workplane_mod.axis_endpoints(plane, index, context)
            on_screen = location_3d_to_region_2d(region, rv3d, start)
            assert on_screen is not None, "the frame origin must be in view"
            # The hover gizmo runs with a full view context (region included),
            # which the steps here do not otherwise have.
            with bpy.context.temp_override(**view):
                # The same path the re-pick modal uses, so both are covered.
                object_hover.publish_hover(bpy.context, _V(on_screen), None)
                hovered = global_data.hover_axis
            assert hovered is not None, "an axis under the cursor must publish"
            global_data.hover_axis = hovered
            _redraw()
            start, end = workplane_mod.axis_endpoints(plane, index, context)
            assert (end - start).length > 0.0, "an axis needs a direction"
            assert isinstance(start, Vector)
            global_data.axis_picker = False
            global_data.hover_axis = None
            _redraw()

        @_check("circular array around a picked axis")
        def _():
            # The tool draws the axes to pick from and hovers whole objects, both
            # of which only run with a window. The operator is then executed
            # straight through with the axis a pick would have stored.
            circular_nodes = importlib.import_module(
                f"{TARGET}.utilities.circular_array_nodes"
            )
            root = globals()["sketch_obj"]
            root.select_set(True)
            context.view_layer.objects.active = root

            bpy.ops.wm.tool_set_by_id(name="sketcher.slvs_node_array_circular")
            _redraw()

            body = body_mod.body_of(root) or root
            circular_nodes.build_circular_array_node_group()
            bpy.ops.view3d.slvs_node_array_circular(
                target_name=body.name,
                axis_origin=(0.0, 0.0, 0.0),
                axis_direction=(0.0, 0.0, 1.0),
                count=6,
            )
            _redraw()
            assert body.modifiers.get("CAD_Sketcher Circular Array") is not None, (
                "the circular array must leave its modifier on the body"
            )
            bpy.ops.wm.tool_set_by_id(name="builtin.select_box")
            _redraw()

        @_check("linear array follows the axis under the cursor")
        def _():
            # The drag snap needs a real region (screen-space hit tests and a
            # raycast), so it can only be exercised here.
            from bpy_extras.view3d_utils import location_3d_to_region_2d
            from mathutils import Vector as _V

            modifiers = importlib.import_module(f"{TARGET}.operators.modifiers")
            workplane_mod = importlib.import_module(f"{TARGET}.utilities.workplane")
            global_data = importlib.import_module(f"{TARGET}.global_data")

            root = globals()["sketch_obj"]
            root.select_set(True)
            context.view_layer.objects.active = root

            global_data.axis_picker = True
            _redraw()  # the axes have to be drawn to be followed
            plane, index, _pick_id = next(
                iter(workplane_mod.iter_axis_candidates(context))
            )
            start, end = workplane_mod.axis_endpoints(plane, index, context)

            view = _view3d_context()
            region = view["region"]
            rv3d = view["space_data"].region_3d
            # A point along the axis, away from its middle where all three cross.
            on_axis = start + (end - start) * 0.75
            coords = location_3d_to_region_2d(region, rv3d, on_axis)
            assert coords is not None, "the axis must be in view"

            probe = type("_Probe", (modifiers.AxisOverlayMixin,), {})()
            with bpy.context.temp_override(**view):
                ends = probe.axis_under_cursor(bpy.context, _V(coords))
            global_data.axis_picker = False
            global_data.hover_axis = None
            _redraw()

            assert ends is not None, "the axis under the cursor must be found"
            followed = (ends[1] - ends[0]).normalized()
            wanted = (end - start).normalized()
            assert abs(followed.dot(wanted)) > 0.99, (
                f"followed {followed[:]}, expected {wanted[:]}"
            )
            offset = modifiers.offset_along_axis(
                root.matrix_world.inverted(), ends, on_axis
            )
            assert offset is not None and offset.length > 0.0, (
                "a drag along the axis must give an offset"
            )

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
            # The part is rooted in the mesh the sketch is realised on.
            base_body = body_mod.body_of(body)
            assert base_body is not None, "a sketch must have a body"
            assert part.is_part_root(base_body), "a standalone solid must root a part"

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
            boolean_targets.detect_targets = lambda *a, **k: [base_body]
            try:
                bpy.ops.view3d.slvs_node_extrude(target_name=cutter.name, offset=2.0)
            finally:
                boolean_targets.detect_targets = detect
            _redraw()
            assert part.part_root_of(cutter) == base_body, (
                f"cutter joined {part.part_root_of(cutter)}, expected {base_body.name}"
            )
            cutter_body = body_mod.body_of(cutter)
            assert not cutter_body.visible_get(), (
                "a cutter doing its job must be hidden"
            )

        @_check("sketch activated and drawn")
        def _():
            set_active_sketch = sketch_ref.set_active_sketch

            set_active_sketch(context, globals()["sketch_obj"])
            _redraw()
            set_active_sketch(context, None)
            _redraw()

        @_check("snapping looks past the sketch being drawn in")
        def _():
            # Needs the real ray_cast, which only has geometry to hit with a
            # window: the sketch's own body is a visible mesh sitting exactly
            # where the cursor is drawing, so without skipping it every move
            # lands on a snap target of its own shape (#591).
            from bpy_extras.view3d_utils import location_3d_to_region_2d
            from mathutils import Vector as _V

            view_utils = importlib.import_module(f"{TARGET}.utilities.view")

            # A filled square, so the body is a surface the ray can actually hit.
            sketch = build_sketch_on_workplane(context, context.scene.sketcher.wp_xy)
            corners = ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0))
            points = [curve_ref.PointRef.create(sketch, co) for co in corners]
            for i in range(4):
                curve_ref.LineRef.create(sketch, points[i], points[(i + 1) % 4])
            solver.solve_system(context, sketch=sketch)
            curve_data.refresh_curve_geometry(sketch)
            sketch_obj = sketch.target_object
            sketch_ref.set_active_sketch(context, sketch_obj)
            body = body_mod.body_of(sketch_obj)
            assert body is not None, "a sketch is realised on a body"
            context.view_layer.update()
            _redraw()

            skipped = view_utils.snap_skipped_objects(context)
            assert sketch_obj in skipped and body in skipped, (
                f"snapping must look past the sketch and its body: {skipped}"
            )

            # Aim at the body's own surface and ask for a snap: there must be none.
            evaluated = body.evaluated_get(context.evaluated_depsgraph_get())
            mesh = evaluated.to_mesh()
            assert len(mesh.polygons), "the body must have a surface to aim at"
            target = body.matrix_world @ mesh.polygons[0].center.copy()
            evaluated.to_mesh_clear()

            context.scene.tool_settings.use_snap = True
            view = _view3d_context()
            coords = location_3d_to_region_2d(
                view["region"], view["space_data"].region_3d, target
            )
            assert coords is not None, "the body must be in view"
            with bpy.context.temp_override(**view):
                snap = view_utils.get_blender_snap_info(bpy.context, _V(coords))
            context.scene.tool_settings.use_snap = False
            sketch_ref.set_active_sketch(context, None)
            _redraw()

            assert snap is None, f"snapped to the sketch being drawn: {snap}"

        @_check("a chain carries on into the tool that is switched to")
        def _():
            # The handover goes through the keymap: the running tool offers its
            # last point and the tool the key starts picks it up while invoking.
            # Only an invoke with a real window gets that far.
            from unittest import mock

            add_arc = importlib.import_module(f"{TARGET}.operators.add_arc")
            continuation = importlib.import_module(
                f"{TARGET}.stateful_operator.utilities.continuation"
            )
            declarations = importlib.import_module(f"{TARGET}.declarations")
            arc_cls = add_arc.View3D_OT_slvs_add_arc3pt2d

            sketch_ref.set_active_sketch(context, globals()["sketch_obj"])
            sketch = sketch_ref.get_active_sketch(context)
            end = curve_ref.PointRef.create(sketch, (2.0, 2.0))
            curve_data.refresh_curve_geometry(sketch)
            continuation.publish(
                [end.curve_id], curve_ref.PointRef, sketch.target_object.name
            )

            seeded = []
            original = arc_cls._seed_from_chain

            def recording(op, ctx):
                took = original(op, ctx)
                seeded.append(took)
                return took

            with mock.patch.object(arc_cls, "_seed_from_chain", recording):
                with bpy.context.temp_override(**_view3d_context()):
                    bpy.ops.view3d.invoke_tool(
                        tool_name=declarations.WorkSpaceTools.AddArc3Point2D.value,
                        operator=declarations.Operators.AddArc3Point2D.value,
                    )
                    bpy.ops.wm.tool_set_by_id(name="builtin.select_box")
            _redraw()

            assert seeded == [True], f"the arc did not carry on: {seeded}"
            assert not continuation.pending(), "the offer must not outlive the switch"
            sketch_ref.set_active_sketch(context, None)
            _redraw()

    if _FAILURES:
        print(f"SMOKE FAILED: {', '.join(_FAILURES)}", file=sys.stderr)
        sys.exit(1)
    print("SMOKE OK")


try:
    main()
finally:
    bpy.ops.wm.quit_blender()
