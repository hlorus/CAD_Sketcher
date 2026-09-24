"""Author ``testing/fixtures/v0_31_part.blend`` with the v0.31.1 add-on.

Files saved by 0.30/0.31 are the shape migration has the most trouble with: the
sketch object itself carries the modifier stack, there are no bodies and no
parts. Every recent migration bug lived there, so the fixture has to be written
by that version rather than faked by this one, and this script is how it gets
regenerated when the file needs to change.

Run it against an isolated Blender config holding a v0.31.1 build::

    git worktree add ../v031-build --detach v0.31.1
    blender --background --factory-startup --command extension build \\
        --source-dir ../v031-build --output-dir .bltest/dist031
    blender --background --factory-startup --command extension install-file \\
        --repo user_default --enable .bltest/dist031/CAD_Sketcher-0.31.1.zip
    blender --background --factory-startup --python scripts/make_v031_fixture.py \\
        -- testing/fixtures/v0_31_part.blend

with ``BLENDER_USER_RESOURCES`` pointing at a throwaway directory for all three
(see CLAUDE.md), so the real config never sees the old version.

What the part exercises, and why each piece is in it:

- an extruded rectangle, the ordinary case: stack on the sketch object,
- a second extruded sketch booleaned into it, so cutter pointers have to be
  repointed at the bodies migration creates,
- that cutter hidden, both eye and viewport: a part the user put away must not
  come back visible (issue behind PR #743),
- a linear array stacked after that extrude, so the order of the stack has to
  survive the move onto the body,
- a sketch with no modifiers at all, which still has to end up with a body.
"""

import sys

import addon_utils
import bpy

ADDON = "bl_ext.user_default.CAD_Sketcher"


def enable_addon() -> None:
    """Enable the installed 0.31 build, and only it."""
    for module in addon_utils.modules():
        if module.__name__.endswith(".CAD_Sketcher") and module.__name__ != ADDON:
            addon_utils.disable(module.__name__)
    addon_utils.enable(ADDON, default_set=True)
    module = next(m for m in addon_utils.modules() if m.__name__ == ADDON)
    print("FIXTURE addon:", module.__file__)


def new_sketch(context):
    """A sketch shaped the way 0.31 made one: a Curves object on origin XY."""
    from bl_ext.user_default.CAD_Sketcher.model.sketch_ref import (
        Sketch,
        stamp_sketch_props,
    )
    from bl_ext.user_default.CAD_Sketcher.utilities.curve_data import (
        ensure_sketch_curve_object,
    )

    entities = context.scene.sketcher.entities
    entities.ensure_origin_elements(context)
    entity_sketch = entities.add_sketch(entities.origin_plane_XY)
    ensure_sketch_curve_object(entity_sketch)
    stamp_sketch_props(entity_sketch.target_object)
    return Sketch(entity_sketch.target_object)


def rectangle(sketch, half_x: float, half_y: float) -> None:
    """Four lines round the origin, a profile the extrude can fill."""
    from bl_ext.user_default.CAD_Sketcher.model.curve_ref import LineRef, PointRef

    corners = [
        PointRef.create(sketch, co)
        for co in (
            (-half_x, -half_y),
            (half_x, -half_y),
            (half_x, half_y),
            (-half_x, half_y),
        )
    ]
    for start, end in zip(corners, corners[1:] + corners[:1]):
        LineRef.create(sketch, start, end)


def circle(sketch, radius: float, center=(0.0, 0.0)) -> None:
    from bl_ext.user_default.CAD_Sketcher.model.curve_ref import CircleRef, PointRef

    CircleRef.create(sketch, PointRef.create(sketch, center), radius)


def build_node_groups() -> None:
    """Build the tool node groups up front.

    The operators build them in ``init``, which only runs on invoke; driven with
    ``EXEC_DEFAULT`` they would find no group and bail.
    """
    from bl_ext.user_default.CAD_Sketcher.utilities.array_nodes import (
        build_array_node_group,
    )
    from bl_ext.user_default.CAD_Sketcher.utilities.boolean_nodes import (
        build_boolean_node_group,
    )
    from bl_ext.user_default.CAD_Sketcher.utilities.extrude_nodes import (
        EXTRUDE_NODE_GROUP,
        build_extrude_node_group,
        ensure_extrude_edge_walls,
    )

    build_extrude_node_group()
    ensure_extrude_edge_walls(bpy.data.node_groups.get(EXTRUDE_NODE_GROUP))
    build_boolean_node_group()
    build_array_node_group()


def main() -> None:
    enable_addon()
    build_node_groups()
    context = bpy.context

    # The startup scene's cube would collect booleans of its own: the tools pick
    # up overlapping bodies automatically, and that noise is not what is tested.
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    base = new_sketch(context)
    base.target_object.name = "Plate"
    rectangle(base, 20.0, 12.0)

    cutter = new_sketch(context)
    cutter.target_object.name = "Hole"
    circle(cutter, 5.0)

    for name, offset in (("Plate", 8.0), ("Hole", 20.0)):
        bpy.ops.view3d.slvs_node_extrude(
            "EXEC_DEFAULT", target_name=name, offset=offset
        )

    plate = bpy.data.objects["Plate"]
    hole = bpy.data.objects["Hole"]
    bpy.ops.view3d.slvs_node_boolean(
        "EXEC_DEFAULT", target_name=plate.name, cutter_name=hole.name
    )

    # A second tool on the same object, so the stack order has to survive too.
    bpy.ops.view3d.slvs_node_array_linear(
        "EXEC_DEFAULT", target_name=plate.name, count=3, offset=(50.0, 0.0, 0.0)
    )

    # The cutter is scaffolding: the user has it out of the way, both ways.
    hole.hide_set(True)
    hole.hide_viewport = True

    # Last, and well clear of the part: a sketch the tools never touched, so it
    # keeps an empty stack rather than collecting a boolean of its own.
    bare = new_sketch(context)
    bare.target_object.name = "Outline"
    bare.target_object.location = (0.0, 0.0, 200.0)
    rectangle(bare, 4.0, 4.0)

    context.view_layer.update()
    path = sys.argv[-1]
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)
    print("FIXTURE saved:", path)
    for obj in bpy.data.objects:
        print(
            f"FIXTURE object: {obj.name} ({obj.type}) "
            f"mods={[m.name for m in obj.modifiers]} "
            f"hidden={int(obj.hide_viewport)}{int(obj.hide_get())}"
        )


main()
bpy.ops.wm.quit_blender()
