"""Author a demo .blend holding every state of the part / feature list.

For documentation screenshots. The list changes shape with what is active (see
``ui/feature_list.py``), so one file has to carry a part rich enough to show each
kind of row plus enough parts around it to show the wider scopes.

Run it in a real GUI session, so the extrude tool's auto-boolean detection sees
evaluated geometry and the cutter becomes a genuine cutter::

    blender --factory-startup --python scripts/make_part_list_demo.py \\
        -- docs/demo/part_list.blend

Use the oldest Blender the manifest supports (see ``make_v031_fixture.py`` for
why) if the file is ever committed: Blender only reads backwards.

What the file holds, and what to select for each screenshot:

===========================  ==================================================
Select                       The list shows
===========================  ==================================================
nothing                      every part: Bracket, Plate, Imported Block, and the
                             bodyless Legacy Sketch. Each part row's button
                             opens the part rather than a sketch.
the Frame empty              the parts inside that assembly: Bracket, Plate
Bracket (or any of its       Bracket's features: its base feature first, then the
features)                    cutter (eye toggles the hidden solid) and the
                             hand-joined mesh (no sketch, so the button opens
                             Edit Mode)
Plate                        a part with nothing but its base feature
Imported Block               a part that was never drawn: no profile to show,
                             and the row opens Edit Mode
===========================  ==================================================

Toggle the eye in the row above the list to see the hidden-part state.
"""

import sys

import bmesh
import bpy

TARGET = "bl_ext.user_default.CAD_Sketcher"


def _enable_addon():
    import addon_utils

    for module in addon_utils.modules():
        if module.__name__.endswith(".CAD_Sketcher") and module.__name__ != TARGET:
            try:
                addon_utils.disable(module.__name__)
            except Exception:
                pass
    addon_utils.enable(TARGET, default_set=True)


_enable_addon()

import importlib  # noqa: E402  (the add-on has to be enabled first)

add_sketch = importlib.import_module(f"{TARGET}.operators.add_sketch")
body_mod = importlib.import_module(f"{TARGET}.utilities.body")
collections = importlib.import_module(f"{TARGET}.utilities.collections")
curve_data = importlib.import_module(f"{TARGET}.utilities.curve_data")
curve_ref = importlib.import_module(f"{TARGET}.model.curve_ref")
extrude_nodes = importlib.import_module(f"{TARGET}.utilities.extrude_nodes")
modifiers = importlib.import_module(f"{TARGET}.operators.modifiers")
part = importlib.import_module(f"{TARGET}.utilities.part")
sketch_ref = importlib.import_module(f"{TARGET}.model.sketch_ref")
solver = importlib.import_module(f"{TARGET}.curve_solver")
workplane = importlib.import_module(f"{TARGET}.utilities.workplane")


def _view3d_context():
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
                        "region_data": area.spaces.active.region_3d,
                    }
    return None


def rectangle(sketch, half, offset=(0.0, 0.0)):
    """A closed square profile, solved and pushed to the curve data."""
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
    solver.solve_system(bpy.context, sketch=sketch)
    curve_data.refresh_curve_geometry(sketch)


def cube(name, location, size=1.0):
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=size)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    return obj


def solid(context, half, offset, depth, name):
    """A sketched square made solid: the shape every feature here starts as."""
    sketch = add_sketch.build_sketch_on_workplane(context, context.scene.sketcher.wp_xy)
    rectangle(sketch, half, offset)
    context.view_layer.update()
    bpy.ops.view3d.slvs_node_extrude(
        target_name=sketch.target_object.name, offset=depth
    )
    body = body_mod.body_of(sketch.target_object)
    if body is not None:
        body.name = name
    return sketch, body


def main():
    context = bpy.context
    override = _view3d_context()
    if override is None:
        print("DEMO FAILED: no 3D viewport; run this with a GUI", file=sys.stderr)
        sys.exit(1)

    for obj in list(context.scene.objects):
        bpy.data.objects.remove(obj)

    with context.temp_override(**override):
        workplane.ensure_origin_workplane_empties(context)
        # The tool builds its node group on the modal invoke path only.
        extrude_nodes.build_extrude_node_group()
        extrude_nodes.ensure_extrude_edge_walls(
            bpy.data.node_groups.get(extrude_nodes.EXTRUDE_NODE_GROUP)
        )

        # --- Bracket: the part with one of every kind of row -----------------
        _base_sketch, bracket = solid(context, 1.0, (0.0, 0.0), 1.0, "Bracket")
        part.promote_to_root(bracket)
        part.mark_part_root(bracket)
        part.ensure_part_planes(context, bracket)

        # A second solid that cuts it: this is the hidden-cutter row. The boolean
        # is applied by hand rather than left to the tool's auto-detection, which
        # needs the solid evaluated and finds nothing in a scripted run.
        cut_sketch, cutter = solid(context, 0.35, (0.0, 0.0), 2.0, "Bracket Cut")
        modifiers.apply_boolean(bracket, cutter, "Difference")
        part.settle_membership(cut_sketch.target_object, [bracket], context)
        part.update_cutter_display(cutter, [bracket], True)

        # A mesh nobody drew, joined by hand: no sketch, so its row opens Edit Mode.
        shim = cube("Bracket Shim", (1.4, 0.0, 0.5), size=0.5)
        part.join_part(bracket, shim)

        # --- Plate: a part with nothing but its base feature -----------------
        _plate_sketch, plate = solid(context, 0.8, (4.0, 0.0), 0.3, "Plate")
        part.promote_to_root(plate)
        part.mark_part_root(plate)
        part.ensure_part_planes(context, plate)

        # --- An assembly holding both ---------------------------------------
        frame = part.create_assembly(context, "Frame")
        part.join_assembly(frame, bracket)
        part.join_assembly(frame, plate)

        # --- A part that was never drawn ------------------------------------
        block = cube("Imported Block", (-4.0, 0.0, 0.5), size=1.0)
        part.mark_part_root(block)
        part.ensure_part_planes(context, block)

        # --- A sketch from before bodies existed, belonging to no part -------
        entities = context.scene.sketcher.entities
        # The pre-split shape hangs off the origin *entities*, not the workplane
        # empties, and nothing else here needs them.
        entities.ensure_origin_elements(context)
        entity_sketch = entities.add_sketch(entities.origin_plane_XY)
        curve_data.create_sketch_curve_object(context, entity_sketch)
        sketch_ref.stamp_sketch_props(entity_sketch.target_object)
        entity_sketch.target_object.name = "Legacy Sketch"

        collections.sync_part_collections(context.scene)
        for obj in context.selected_objects:
            obj.select_set(False)
        context.view_layer.objects.active = None
        context.view_layer.update()

    feature_list = importlib.import_module(f"{TARGET}.ui.feature_list")
    rows = [o for o in bpy.context.scene.objects if feature_list.is_feature_row(o)]
    print("\n--- DEMO SCENE ---")
    print(f"parts:     {[o.name for o in rows]}")
    print(f"bracket:   {[o.name for o in bracket.children_recursive]}")
    print(f"cutter hidden: {cutter.hide_viewport}")
    print(f"cutting bodies: {sorted(feature_list.cutting_bodies(bpy.context.scene))}")
    print(f"scope with nothing active: {feature_list.list_scope(bpy.context)[0]}")

    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    path = args[0] if args else "part_list_demo.blend"
    bpy.ops.wm.save_as_mainfile(filepath=bpy.path.abspath(path))
    print(f"saved: {path}")
    print("--- END ---")


try:
    main()
finally:
    bpy.ops.wm.quit_blender()
