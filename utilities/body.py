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
# Set once a body has been put where the sketch used to stand. A body can exist
# before that: the file update builds one to carry an old stack, since a Curves
# object holds only Geometry Nodes modifiers.
BODY_PLACED_KEY = "slvs:body_placed"


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


def ensure_body(
    context, sketch_obj: bpy.types.Object, name: str = ""
) -> bpy.types.Object:
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
    return _new_body(context, sketch_obj, name)


def default_body_name(root: Optional[bpy.types.Object] = None) -> str:
    """What to call a new body: after the part it joins, else just "Body".

    Not everything a sketch makes is a part -- a body can be a feature of one, a
    cutter, or nothing solid yet -- so "Body" says what it is without claiming
    more. A body joining a part takes the part's name, which Blender numbers, so
    "Bracket" gains "Bracket.001" rather than an unrelated "Body.007".
    """
    if root is not None and root.name:
        return root.name
    return "Body"


def _new_body(
    context, sketch_obj: bpy.types.Object, name: str = ""
) -> bpy.types.Object:
    """A bare body bound to ``sketch_obj``: linked, placed, reading the sketch."""
    from .collections import link_to_scene_root
    from .curve_data import _ensure_convert_modifier

    name = name or default_body_name()
    body = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    body.data.name = body.name  # or the two number themselves apart
    body[BODY_SKETCH_KEY] = sketch_obj
    sketch_obj.slvs_body = body
    link_to_scene_root(body, context.scene)

    # The convert group reads the sketch in the body's local space, so matching
    # the transforms keeps the geometry planar locally and correct in the world.
    # Composed from the parent chain rather than read back: ``matrix_world`` is
    # evaluated state, and a sketch parented a moment ago still reads identity.
    from .part import world_matrix_of

    body.matrix_basis = world_matrix_of(sketch_obj)

    _ensure_convert_modifier(body)
    bind_body_to_sketch(body, sketch_obj)
    return body


def name_after_body(body: bpy.types.Object, sketch_obj, plane=None) -> bool:
    """Name a body's sketch, base planes and mesh after the body.

    The body is the thing the user grabs, so the outliner reads as one named
    thing with its source under it: rename the body and the rest follows. A
    ``plane`` is renamed only when the body owns it; one the sketch was drawn on
    belongs to something else. Returns whether anything was actually renamed.
    """
    from .part import PART_PLANE_AXES, PART_PLANE_KEY, existing_part_plane

    changed = _rename(body.data, body.name)
    if sketch_obj is not None:
        changed |= _rename(sketch_obj, f"{body.name} Sketch")
        changed |= _rename(sketch_obj.data, sketch_obj.name)
    if plane is not None and PART_PLANE_KEY not in plane:
        changed |= _rename(plane, f"{body.name} Workplane")
    for axis, _euler in PART_PLANE_AXES:
        base = existing_part_plane(body, axis)
        if base is not None:
            changed |= _rename(base, f"{body.name} {axis}")
    return changed


def _rename(datablock, name: str) -> bool:
    """Give ``datablock`` a name, unless it has it already. True if renamed.

    Assigning a name that is taken makes Blender append ``.001``, so a pass that
    reassigns the name it just set would walk a body's sketch up the numbers on
    every depsgraph update.
    """
    if datablock is None or datablock.name == name:
        return False
    datablock.name = name
    return True


def rename_after_bodies(scene, depsgraph=None) -> bool:
    """Keep what hangs under a body named after it.

    Renaming the body is how a part is named: its sketch, planes and mesh are
    labels derived from that name rather than names of their own, so they are
    re-derived rather than remembered.

    ``depsgraph`` narrows the pass to what this update actually touched -- a
    rename tags the datablock, so a body or sketch that nobody touched cannot
    have drifted. Matched by name, never by reading ``id.original``, which
    crashes on an id that is still being built.
    """
    from .. import global_data
    from ..model.sketch_ref import get_sketches
    from .collections import is_editable

    if global_data.migrating_bodies:
        return False

    touched = None
    if depsgraph is not None:
        touched = set()
        for update in depsgraph.updates:
            try:
                touched.add(update.id.name)
            except (AttributeError, ReferenceError):
                continue

    changed = False
    for sketch in get_sketches(scene):
        sketch_obj = sketch.target_object
        body = body_of(sketch_obj)
        if body is None:
            continue
        if touched is not None and not {body.name, sketch_obj.name} & touched:
            continue
        if not is_editable(body) or not is_editable(sketch_obj):
            continue
        if name_after_body(body, sketch_obj, sketch_obj.slvs_workplane):
            changed = True
    return changed


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
    """Recreate one of a legacy sketch's modifiers on its body.

    Any type, not only Geometry Nodes: a file can carry a modifier the user
    added themselves, and an older one carries what the file update translated.
    """
    from ..operators.modifiers import copy_modifier

    return copy_modifier(source, body)


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
            # A linked group cannot be rebuilt to the current interface, so it
            # may not have the socket at all: leave such a modifier alone rather
            # than failing the whole update.
            cutter_id = boolean_input_ids(group).get("Cutter")
            if cutter_id is None:
                continue
            if get_modifier_input(modifier, cutter_id) == sketch_obj:
                set_modifier_input(modifier, cutter_id, body)


def _inherit_visibility(sketch_obj: bpy.types.Object, body: bpy.types.Object) -> None:
    """Give the body the visibility its sketch object had before the split.

    In old files the sketch object carried the modifiers, so hiding it hid the
    result. The body is that result now, and a part the user had put away has to
    stay away: created visible it pops back into the scene on update.
    """
    body.hide_viewport = sketch_obj.hide_viewport
    body.hide_render = sketch_obj.hide_render
    try:
        body.hide_set(sketch_obj.hide_get())
    except RuntimeError:
        pass  # one of them is not in this view layer


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

    Idempotent: a sketch whose body has been put in place is left alone. A body
    that exists but has not been placed is one the file update built to carry an
    old modifier stack; it still needs its place here.
    """
    from .. import global_data

    changed = False
    global_data.migrating_bodies = True
    try:
        changed = _migrate_bodies(context, scene)
    finally:
        global_data.migrating_bodies = False
    return changed


def _migrate_bodies(context, scene) -> bool:
    """The conversion itself; see :func:`migrate_bodies`."""
    from ..model.sketch_ref import get_sketches, hide_sketch_curves
    from .collections import is_editable

    changed = False
    for sketch in list(get_sketches(scene)):
        sketch_obj = sketch.target_object
        if not is_editable(sketch_obj):
            continue
        body = body_of(sketch_obj)
        if body is not None and body.get(BODY_PLACED_KEY):
            continue
        if body is not None and not sketch_obj.modifiers:
            # The split this pass performs has already happened: the stack lives
            # on the body and the sketch is pure curves. Files written before the
            # flag was stamped at creation reach here once; marking them keeps
            # running the update on a current file the no-op it claims to be
            # (unmarked, it renamed the body after the sketch on every run).
            body[BODY_PLACED_KEY] = True
            continue
        if body is None:
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
        body[BODY_PLACED_KEY] = True
        _inherit_visibility(sketch_obj, body)
        # What the user sees is the body now; the curves would only double it.
        hide_sketch_curves(sketch_obj)
        changed = True

    return changed
