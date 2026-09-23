"""Bodies: the mesh object a sketch's geometry becomes.

A sketch is a Curves object and stays pure source: no modifiers, nothing that
changes its type. Its geometry is pulled into a *mesh* object, the body, whose
stack starts by reading the sketch and then converts, extrudes and booleans it.

That split is what makes the result a normal Blender mesh: it can be applied
(Blender refuses to apply a modifier that changes an object's type, issue #723),
exported, read with ``to_mesh``, and edited with mesh tools. It also matches how
parts are structured, since the body is the thing a user grabs and moves: the
body anchors the part, its workplane hangs under it, and the sketch sits on that
workplane.
"""

from typing import Optional

import bpy
from mathutils import Matrix

# The body's link back to the sketch it reads, so each can find the other without
# searching every modifier in the file.
BODY_SKETCH_KEY = "slvs:body_of"


def is_body(obj: Optional[bpy.types.Object]) -> bool:
    """Whether ``obj`` is the mesh a sketch's geometry is realised on."""
    return bool(obj is not None and obj.type == "MESH" and BODY_SKETCH_KEY in obj)


def body_of(sketch_obj: Optional[bpy.types.Object]) -> Optional[bpy.types.Object]:
    """The body that realises ``sketch_obj``, or None if it has none yet."""
    if sketch_obj is None:
        return None
    body = sketch_obj.slvs_body
    return body if is_body(body) else None


def sketch_of(body: Optional[bpy.types.Object]) -> Optional[bpy.types.Object]:
    """The sketch a body reads, or None."""
    if not is_body(body):
        return None
    sketch = body.get(BODY_SKETCH_KEY)
    return sketch if isinstance(sketch, bpy.types.Object) else None


def ensure_body(context, sketch_obj: bpy.types.Object) -> bpy.types.Object:
    """Get or create the body that realises ``sketch_obj``.

    Created with the sketch rather than when it first becomes solid, so the part
    is anchored in the same object from the start: a body appearing later would
    mean handing the part's root (and its transform) over mid-edit.
    """
    from ..model.sketch_ref import is_sketch_object

    assert is_sketch_object(sketch_obj), "ensure_body: not a sketch"

    existing = body_of(sketch_obj)
    if existing is not None:
        return existing
    return _new_body(context, sketch_obj)


def _new_body(context, sketch_obj: bpy.types.Object) -> bpy.types.Object:
    """A bare body bound to ``sketch_obj``: linked, placed, reading the sketch."""
    from .collections import link_to_scene_root
    from .curve_data import _ensure_convert_modifier

    body = bpy.data.objects.new("Part", bpy.data.meshes.new("Part"))
    body.data.name = body.name  # or the two number themselves apart
    body[BODY_SKETCH_KEY] = sketch_obj
    sketch_obj.slvs_body = body
    link_to_scene_root(body, context.scene)

    # The convert group reads the sketch in the body's local space, so matching
    # the transforms keeps the geometry planar locally and correct in the world.
    body.matrix_basis = sketch_obj.matrix_world.copy()

    _ensure_convert_modifier(body)
    bind_body_to_sketch(body, sketch_obj)
    return body


def name_after_body(body: bpy.types.Object, sketch_obj, plane=None) -> None:
    """Name a body's sketch (and its own plane) after the body.

    The body is the part as far as the user is concerned, so the outliner reads
    as one thing with its source under it instead of three objects called
    "Part". Only a plane the part owns is renamed: one it was drawn on belongs
    to something else.
    """
    body.data.name = body.name
    sketch_obj.name = f"{body.name} Sketch"
    sketch_obj.data.name = sketch_obj.name
    if plane is not None:
        plane.name = f"{body.name} Plane"


def remove_body(sketch_obj: bpy.types.Object) -> None:
    """Delete the body of a sketch that is going away."""
    body = body_of(sketch_obj)
    if body is None:
        return
    sketch_obj.slvs_body = None
    bpy.data.objects.remove(body)


def bind_body_to_sketch(body: bpy.types.Object, sketch_obj: bpy.types.Object) -> None:
    """Point ``body``'s convert modifier at the sketch it is built from."""
    from ..operators.modifiers import set_modifier_input
    from .convert_nodes import CONVERT_NODE_GROUP, SKETCH_INPUT, input_identifier

    for modifier in body.modifiers:
        group = getattr(modifier, "node_group", None)
        if modifier.type != "NODES" or group is None:
            continue
        if group.name != CONVERT_NODE_GROUP:
            continue
        identifier = input_identifier(group, SKETCH_INPUT)
        if identifier is not None:
            set_modifier_input(modifier, identifier, sketch_obj)


def _copy_modifier(source, body: bpy.types.Object):
    """Recreate one Geometry Nodes modifier on ``body``, settings and all.

    Values are read and written through the group's interface rather than the
    modifier's raw properties, which are not always accessible as IDProperties.
    """
    from ..operators.modifiers import get_modifier_input, set_modifier_input

    group = source.node_group
    copy = body.modifiers.new(source.name, "NODES")
    copy.node_group = group
    if group is None:
        return copy

    for socket in group.interface.items_tree:
        if getattr(socket, "in_out", "") != "INPUT":
            continue
        if getattr(socket, "socket_type", "") == "NodeSocketGeometry":
            continue  # carries no value: it is what the stack is fed
        try:
            value = get_modifier_input(source, socket.identifier)
        except (AttributeError, KeyError):
            continue
        if value is None:
            continue
        set_modifier_input(copy, socket.identifier, value)
    return copy


def _redirect_to_body(scene, sketch_obj: bpy.types.Object, body: bpy.types.Object):
    """Point everything that referenced the sketch's *geometry* at its body.

    A file written before the split used the sketch object as the body, so other
    parts' booleans cut with it and face anchors were stamped from it. Those mean
    the mesh, which is now a different object.
    """
    from ..operators.modifiers import (
        boolean_input_ids,
        get_modifier_input,
        set_modifier_input,
    )
    from .boolean_nodes import BOOLEAN_NODE_GROUP
    from .face_anchor import KEY_SOURCE

    for obj in scene.objects:
        if obj.get(KEY_SOURCE) == sketch_obj:
            obj[KEY_SOURCE] = body
        for modifier in obj.modifiers:
            group = getattr(modifier, "node_group", None)
            if modifier.type != "NODES" or group is None:
                continue
            if group.name != BOOLEAN_NODE_GROUP:
                continue
            cutter_id = boolean_input_ids(group)["Cutter"]
            if get_modifier_input(modifier, cutter_id) == sketch_obj:
                set_modifier_input(modifier, cutter_id, body)


def _rehome_onto_body(context, sketch_obj: bpy.types.Object, body: bpy.types.Object):
    """Put the body where the sketch used to sit in the hierarchy.

    The body becomes what carries the part: a sketch that was its own plane gets
    one (minted where it stood), and a sketch already placed by a plane keeps it,
    with the body hanging from that plane as a new sketch's would.
    """
    from ..operators.add_sketch import new_workplane_empty
    from .part import PART_ROOT_KEY, clear_part_root, fix_transform, mark_part_root

    was_root = bool(sketch_obj.get(PART_ROOT_KEY, False))
    children = list(sketch_obj.children)
    plane = sketch_obj.slvs_workplane

    if plane is None:
        # The sketch was its own plane: mint one where it stands, and let it ride
        # on the body, which now carries the transform.
        plane = new_workplane_empty(context, sketch_obj.matrix_world.copy())
        owns_plane = True
        body.matrix_basis = sketch_obj.matrix_world.copy()
        plane.parent = body
        plane.matrix_parent_inverse = Matrix.Identity(4)
        plane.matrix_basis = Matrix.Identity(4)
    else:
        # It was placed by a plane already: the body hangs from that plane, the
        # way a new sketch's body does.
        owns_plane = False
        body.parent = plane
        body.matrix_parent_inverse = Matrix.Identity(4)
        body.matrix_basis = Matrix.Identity(4)

    sketch_obj.parent = plane
    sketch_obj.slvs_workplane = plane
    sketch_obj.matrix_parent_inverse = Matrix.Identity(4)
    sketch_obj.matrix_basis = Matrix.Identity(4)
    fix_transform(sketch_obj)
    fix_transform(plane)

    # Whatever hung from the sketch belonged to the part, which the body now
    # anchors: its own plane excepted, that is where those go.
    for child in children:
        if child in (plane,):
            continue
        child.parent = body

    # The body took over the sketch's place, so it takes its name too: whatever
    # the user called the part in the old file stays on the thing they now grab.
    # The sketch has to let go of the name first, or the body gets a numbered one.
    taken = sketch_obj.name
    sketch_obj.name = f"{taken}.source"
    body.name = taken
    body.data.name = body.name
    name_after_body(body, sketch_obj, plane if owns_plane else None)

    if was_root:
        clear_part_root(sketch_obj)
        mark_part_root(body)


def migrate_bodies(context, scene) -> bool:
    """Give every sketch in an older file the body its geometry belongs on.

    Files written before the split used the sketch object itself as the body, so
    its modifiers changed a Curves object into a mesh: that is what stops the
    stack being applied (issue #723). The stack moves to a real mesh, the sketch
    keeps only its curves, and everything that referred to the sketch's geometry
    is pointed at the body instead.

    Idempotent: a sketch that already has a body is left alone.
    """
    from ..model.sketch_ref import get_sketches, hide_sketch_curves
    from .collections import is_editable

    changed = False
    for sketch in list(get_sketches(scene)):
        sketch_obj = sketch.target_object
        if not is_editable(sketch_obj) or body_of(sketch_obj) is not None:
            continue

        body = _new_body(context, sketch_obj)
        # The sketch's own convert modifier carries the settings the file was
        # drawn with, so it replaces the fresh one the body was given.
        for modifier in list(body.modifiers):
            body.modifiers.remove(modifier)
        for modifier in list(sketch_obj.modifiers):
            _copy_modifier(modifier, body)
            sketch_obj.modifiers.remove(modifier)
        bind_body_to_sketch(body, sketch_obj)

        _redirect_to_body(scene, sketch_obj, body)
        _rehome_onto_body(context, sketch_obj, body)
        # What the user sees is the body now; the curves would only double it.
        hide_sketch_curves(sketch_obj)
        changed = True

    return changed
