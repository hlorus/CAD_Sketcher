import logging

import bpy
from bpy.types import Context, Event, Operator
from mathutils import Matrix

from ..declarations import Operators, WorkSpaceTools
from ..model.curve_ref import PointRef
from ..stateful_operator.state import state_from_args
from ..stateful_operator.utilities.register import register_stateops_factory
from ..utilities.geometry import face_workplane_matrix
from ..utilities.workplane import ensure_origin_workplane_empties, resolve_sketch_base
from .base_3d import Operator3d
from .utilities import activate_sketch

logger = logging.getLogger(__name__)


def _ensure_focused_part_planes(context: Context):
    """Make sure the part in focus has its own base planes to offer.

    Objects can only be added from operator context, so the pickers ask for them
    as they start rather than the draw code creating them on the fly.
    """
    from ..utilities.part import ensure_part_planes, focused_part

    root = focused_part(context)
    if root is not None:
        ensure_part_planes(context, root)


def _part_for_workplane(context: Context, wp_empty):
    """The part a sketch on ``wp_empty`` belongs to, creating one if it should.

    Sketching on a mesh face means "add a feature to that thing", so the face's
    object becomes a part (if it is not already in one) and the sketch joins it.
    A sketch on a base datum plane belongs to no existing part, so it starts one
    of its own and there is nothing to return.
    """
    from ..utilities.face_anchor import KEY_SOURCE
    from ..utilities.part import mark_part_root, part_root_of

    root = part_root_of(wp_empty)
    if root is not None:
        return root

    source = wp_empty.get(KEY_SOURCE)
    if not isinstance(source, bpy.types.Object):
        return None

    root = part_root_of(source)
    if root is None:
        root = source
        mark_part_root(root)
    return root


def build_sketch_on_workplane(context: Context, wp_empty):
    """Create a Curves sketch on ``wp_empty``, without activating it.

    A sketch that joins an existing part is placed by its workplane, as features
    are; one that starts a part roots it and owns its own transform.
    Returns the wrapped :class:`Sketch`.
    """
    from ..model.sketch_ref import Sketch, stamp_sketch_props

    # Create sketch as a Curves object (parent provides the transform)
    curve = bpy.data.hair_curves.new("Sketch")
    sketch_obj = bpy.data.objects.new("Sketch", curve)

    scene = context.scene
    from ..utilities.collections import link_to_scene_root

    link_to_scene_root(sketch_obj, scene)

    stamp_sketch_props(sketch_obj)

    # Resolve the plane and the part before activate, so align_view sees both.
    wp_orig = wp_empty.original if hasattr(wp_empty, "original") else wp_empty
    root = _part_for_workplane(context, wp_orig)
    from ..utilities.body import ensure_body
    from ..utilities.part import fix_transform, free_transform, join_part, part_root_of

    # Every sketch is realised on a body, and the body is what carries the
    # transform: the sketch always sits on a workplane, and that workplane hangs
    # under the body. A sketch drawn on a shared datum gets a plane of its own
    # there, since the scene's datums belong to no part.
    body = ensure_body(context, sketch_obj)

    starts_a_part = root is None or _is_shared_datum(context, wp_orig)
    plane = (
        new_workplane_empty(context, wp_orig.matrix_world.copy())
        if starts_a_part
        else wp_orig
    )

    if starts_a_part:
        # Nothing to hang from: the body anchors the part and the plane rides on
        # it, so body, plane and sketch all share one world matrix.
        body.matrix_basis = plane.matrix_world.copy()
        plane.parent = body
        plane.matrix_parent_inverse = Matrix.Identity(4)
        plane.matrix_basis = Matrix.Identity(4)
        free_transform(body)
    else:
        # The plane is already part of something (a face of a body, or that
        # part's own datum), so it stays where it is and the new body hangs from
        # it. Re-parenting the plane instead would take the part's datum away.
        if part_root_of(plane) is None:
            # A plane picked on a body that has just become a part: it has to
            # join, or nothing in this chain reaches the part.
            join_part(root, plane)
        body.parent = plane
        body.matrix_parent_inverse = Matrix.Identity(4)
        body.matrix_basis = Matrix.Identity(4)
        fix_transform(body)

    sketch_obj.parent = plane
    sketch_obj.slvs_workplane = plane
    sketch_obj.matrix_parent_inverse = Matrix.Identity(4)
    sketch_obj.matrix_basis = Matrix.Identity(4)
    fix_transform(sketch_obj)
    fix_transform(plane)

    from ..utilities.body import name_after_body

    name_after_body(body, sketch_obj, plane if starts_a_part else None)

    sketch = Sketch(sketch_obj)

    origin = PointRef.create(sketch, (0.0, 0.0), fixed=True, is_origin=True)
    assert origin is not None, "Failed to create origin point"

    return sketch


def _is_shared_datum(context: Context, wp_empty) -> bool:
    """Whether ``wp_empty`` is one of the scene's datums, shared by everything."""
    from ..utilities.face_anchor import is_origin_workplane

    return is_origin_workplane(context.scene, wp_empty)


def create_sketch_on_workplane(context: Context, wp_empty, operator: Operator):
    """Create and activate a Curves sketch on ``wp_empty``.

    Shared by the interactive Add Sketch operator and the direct
    keyboard-driven origin-plane operator so both build the sketch identically.
    Returns the wrapped :class:`Sketch`.
    """
    sketch = build_sketch_on_workplane(context, wp_empty)
    activate_sketch(context, sketch.target_object, operator)
    return sketch


def new_workplane_empty(context: Context, matrix):
    """Create an unattached workplane Empty at ``matrix``, linked at scene level."""
    from ..utilities.collections import link_to_scene_root
    from ..utilities.workplane import hide_managed_workplane, mark_managed_workplane

    empty = bpy.data.objects.new("Workplane", None)
    empty.empty_display_type = "PLAIN_AXES"
    empty.empty_display_size = 0.5
    mark_managed_workplane(empty)
    link_to_scene_root(empty, context.scene)
    empty.matrix_world = matrix
    # A workplane is only worth looking at while you are choosing one, and the
    # pickers draw it themselves; left visible its axes clutter every other mode.
    hide_managed_workplane(empty, context)
    return empty


def create_face_workplane(context: Context, ob, face_index: int):
    """Create a workplane Empty anchored to a mesh face.

    The empty is not parented to the mesh; instead it is anchored to the face
    via a persistent id and the depsgraph handler re-derives its transform from
    the evaluated mesh, so it follows edits and deformation (see
    utilities/face_anchor).
    """
    from ..stateful_operator.utilities.geometry import get_evaluated_obj
    from ..utilities.face_anchor import KEY_SOURCE, can_anchor_face, stamp_face_anchor

    source = getattr(ob, "original", ob)
    empty = new_workplane_empty(context, face_workplane_matrix(context, ob, face_index))

    # Record what the sketch was drawn on even when the face itself cannot be
    # anchored: that is what puts the sketch in the same part as the thing it sits
    # on. Only sketches on a *mesh* can be anchored (a sketch body is a Curves
    # object, so drawing on a sketch's own face never anchors), and a modifier
    # that changed the topology rules it out too (issue #342-adjacent crash on
    # box.blend meshes) -- the empty then stays a plain fixed workplane.
    empty[KEY_SOURCE] = source
    if can_anchor_face(source, get_evaluated_obj(context, source)):
        stamp_face_anchor(empty, source, face_index)
    return empty


def _owns_workplane(context: Context, sketch_obj, wp) -> bool:
    """Whether ``wp`` is a workplane only ``sketch_obj`` uses (safe to change).

    Origin planes are shared by definition; any other child (another sketch or
    an object the user parented) counts as a use.
    """
    from ..utilities.face_anchor import is_origin_workplane

    return (
        wp is not None
        and not is_origin_workplane(context.scene, wp)
        and all(c == sketch_obj for c in wp.children)
    )


def _sketch_workplane(sketch_obj):
    """The workplane object of a sketch object, pointer first then parent."""
    wp = getattr(sketch_obj, "slvs_workplane", None)
    return wp if wp is not None else sketch_obj.parent


def set_sketch_workplane(context: Context, sketch_obj, wp_empty) -> bool:
    """Move a 2D sketch onto another workplane, keeping its 2D geometry.

    The sketch's curves live in its workplane's local frame, so reparenting
    carries the whole sketch (and its constraints) rigidly onto the new plane.
    A workplane left unused is deleted when CAD Sketcher manages it (anchored,
    or grouped in the sketch's collection) so moving sketches around doesn't
    litter the scene; any other one moves to the scene level.
    Returns False when ``wp_empty`` already is the sketch's workplane.
    """
    from .. import global_data
    from ..utilities.collections import link_to_scene_root
    from ..utilities.face_anchor import KEY_FACE_ID, clear_anchor
    from ..utilities.part import is_part_root
    from ..utilities.workplane import is_managed_workplane

    wp_empty = wp_empty.original if hasattr(wp_empty, "original") else wp_empty
    old = _sketch_workplane(sketch_obj)
    if old == wp_empty:
        return False

    if is_part_root(sketch_obj):
        # A root is not placed by a plane; putting it "on" one moves the part
        # there and leaves it owning its transform.
        sketch_obj.matrix_world = wp_empty.matrix_world.copy()
        global_data.needs_solve = True
        return True

    owned = _owns_workplane(context, sketch_obj, old)
    managed = old is not None and (KEY_FACE_ID in old or is_managed_workplane(old))
    sketch_obj.parent = wp_empty
    sketch_obj.slvs_workplane = wp_empty
    sketch_obj.matrix_parent_inverse.identity()

    if owned and managed:
        clear_anchor(old)
        bpy.data.objects.remove(old, do_unlink=True)
    elif owned:
        link_to_scene_root(old, context.scene)

    global_data.needs_solve = True
    return True


def move_sketch_to_face(context: Context, sketch_obj, ob, face_index: int):
    """Put a sketch on a mesh face, reusing its workplane when only it uses it.

    Creating a fresh empty every time would leave the old one behind unused, so
    a workplane the sketch owns is simply re-anchored to the new face. A shared
    one is left to the other sketches and the sketch gets a new workplane.
    Returns the sketch's workplane.
    """
    from .. import global_data
    from ..stateful_operator.utilities.geometry import get_evaluated_obj
    from ..utilities.face_anchor import can_anchor_face, clear_anchor, stamp_face_anchor

    wp = _sketch_workplane(sketch_obj)
    if not _owns_workplane(context, sketch_obj, wp):
        empty = create_face_workplane(context, ob, face_index)
        set_sketch_workplane(context, sketch_obj, empty)
        return empty

    clear_anchor(wp)
    wp.matrix_world = face_workplane_matrix(context, ob, face_index)
    if can_anchor_face(ob, get_evaluated_obj(context, ob)):
        stamp_face_anchor(wp, ob, face_index)
    global_data.needs_solve = True
    return wp


def free_sketch_workplane(context: Context, sketch_obj):
    """Stop a sketch's workplane following its mesh face, for this sketch only.

    The anchor lives on the workplane, which other sketches may share; freeing
    it in place would silently change them too. So a shared workplane is left
    as is and the sketch moves to a new free one at the same spot. Returns the
    sketch's (now free) workplane.
    """
    from ..utilities.face_anchor import clear_anchor

    wp = _sketch_workplane(sketch_obj)
    if wp is None:
        return None
    if _owns_workplane(context, sketch_obj, wp):
        clear_anchor(wp)
        return wp
    empty = new_workplane_empty(context, wp.matrix_world.copy())
    set_sketch_workplane(context, sketch_obj, empty)
    return empty


# TODO:
# - Draw sketches
class View3D_OT_slvs_add_sketch(Operator, Operator3d):
    """Add a sketch"""

    bl_idname = Operators.AddSketch
    bl_label = "Add Sketch"
    bl_options = {"UNDO"}

    # Creating a sketch enters sketch mode, so return to the sketch-mode select
    # tool (not Blender's object select) once done, via the framework setting.
    return_to_tool = WorkSpaceTools.Select

    sketch_state1_doc = [
        "Workplane",
        "Pick a workplane or mesh face as base for the sketch.",
    ]

    states = (
        state_from_args(
            sketch_state1_doc[0],
            description=sketch_state1_doc[1],
            pointer="wp",
            types=(bpy.types.Object,),
            property=None,
            use_create=False,
        ),
    )

    def gather_selection(self, context):
        return [o for o in context.selected_objects if o.type == "EMPTY"]

    def _use_workplane(self, empty):
        self.state_data["is_existing_entity"] = True
        self.state_data["type"] = bpy.types.Object
        return empty.name

    def pick_element(self, context, coords):
        # Priority: workplane border > mesh face > workplane interior, so an
        # outline is never obscured by a mesh (shared with the gizmo hover).
        kind, a, b = resolve_sketch_base(context, coords)

        if kind in ("border", "interior"):
            return self._use_workplane(b)

        if kind == "mesh":
            empty = create_face_workplane(context, a, b)
            if empty:
                return self._use_workplane(empty)

        return None

    def prepare_origin_elements(self, context):
        ensure_origin_workplane_empties(context)
        _ensure_focused_part_planes(context)
        return True

    def invoke(self, context: Context, event: Event):
        # Entry points (Ctrl+Shift+A, panel, menu) switch to the tool and invoke
        # with wait_for_input. With a preselected workplane empty we create the
        # sketch right away; without one there's nothing to do here — the tool +
        # gizmo let the user pick interactively — so just make sure the origin
        # planes exist and end instead of sitting in a modal wait.
        if self.wait_for_input and not self.gather_selection(context):
            self.prepare_origin_elements(context)
            return {"CANCELLED"}
        return super().invoke(context, event)

    def init(self, context: Context, event: Event):
        # Origin workplanes are drawn by the workplane gizmo while the tool is
        # active; just make sure they exist. Sketch mode is entered later, once
        # the sketch actually exists (see main() -> activate_sketch).
        self.prepare_origin_elements(context)
        bpy.ops.ed.undo_push(message="Ensure Origin Elements")
        return True

    def main(self, context: Context):
        wp_empty = self.wp
        if not wp_empty or wp_empty.type != "EMPTY":
            self.report({"WARNING"}, "Please select an Empty as workplane")
            return False

        self.target = create_sketch_on_workplane(context, wp_empty, self)
        return True

    def fini(self, context: Context, succeed: bool):
        # NOTE: don't switch tools here — a cancel also happens when a click
        # simply misses a valid target, and we want to stay on the Add Sketch
        # tool then. Explicit ESC/RMB -> select is handled by the tool keymap.
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))


class View3D_OT_slvs_add_sketch_on_plane(Operator):
    """Create a sketch on an origin workplane by its normal axis.

    Bound to X/Y/Z on the Add Sketch tool so a plane can be chosen directly,
    without aiming at its (possibly edge-on) rectangle.
    """

    bl_idname = Operators.AddSketchOnPlane
    bl_label = "Add Sketch on Origin Plane"
    bl_options = {"REGISTER", "UNDO"}

    # Value is the origin plane; the key is the axis normal to it (what the user
    # presses): Z -> XY, Y -> XZ, X -> YZ.
    plane: bpy.props.EnumProperty(
        name="Plane",
        items=(
            ("XY", "XY", "Ground plane (normal Z)"),
            ("XZ", "XZ", "Front plane (normal Y)"),
            ("YZ", "YZ", "Side plane (normal X)"),
        ),
        default="XY",
    )

    def execute(self, context: Context):
        ensure_origin_workplane_empties(context)
        sketcher = context.scene.sketcher
        empty = {
            "XY": sketcher.wp_xy,
            "XZ": sketcher.wp_xz,
            "YZ": sketcher.wp_yz,
        }[self.plane]
        if empty is None:
            self.report({"WARNING"}, "Origin workplane not available")
            return {"CANCELLED"}

        create_sketch_on_workplane(context, empty, self)
        return {"FINISHED"}


_register_stateops, _unregister_stateops = register_stateops_factory(
    (View3D_OT_slvs_add_sketch,)
)


def register():
    bpy.utils.register_class(View3D_OT_slvs_add_sketch_on_plane)
    _register_stateops()


def unregister():
    _unregister_stateops()
    bpy.utils.unregister_class(View3D_OT_slvs_add_sketch_on_plane)
