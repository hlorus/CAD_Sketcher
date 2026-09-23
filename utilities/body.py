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
    from .body_nodes import BODY_NODE_GROUP, body_input_ids, build_body_node_group
    from .collections import link_to_scene_root
    from .curve_data import _ensure_convert_modifier

    assert is_sketch_object(sketch_obj), "ensure_body: not a sketch"

    existing = body_of(sketch_obj)
    if existing is not None:
        return existing

    body = bpy.data.objects.new("Part", bpy.data.meshes.new("Part"))
    body[BODY_SKETCH_KEY] = sketch_obj
    sketch_obj.slvs_body = body
    link_to_scene_root(body, context.scene)

    # Object Info reads in the body's local space, so matching the transforms
    # keeps the geometry planar locally and correct in the world.
    body.matrix_basis = sketch_obj.matrix_world.copy()

    group = build_body_node_group()
    source = body.modifiers.new(BODY_NODE_GROUP, "NODES")
    source.node_group = group
    from ..operators.modifiers import set_modifier_input

    set_modifier_input(source, body_input_ids(group)["Sketch"], sketch_obj)

    # Then the usual conversion, now running on a mesh object.
    _ensure_convert_modifier(body)
    return body


def remove_body(sketch_obj: bpy.types.Object) -> None:
    """Delete the body of a sketch that is going away."""
    body = body_of(sketch_obj)
    if body is None:
        return
    sketch_obj.slvs_body = None
    bpy.data.objects.remove(body)
