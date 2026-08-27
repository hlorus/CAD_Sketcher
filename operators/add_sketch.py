import logging

import bpy
from bpy.types import Context, Event, Operator

from ..declarations import Operators, WorkSpaceTools
from ..model.curve_ref import PointRef
from ..stateful_operator.state import state_from_args
from ..stateful_operator.utilities.register import register_stateops_factory
from ..utilities.geometry import face_workplane_matrix
from ..utilities.workplane import ensure_origin_workplane_empties, resolve_sketch_base
from .base_3d import Operator3d
from .utilities import activate_sketch

logger = logging.getLogger(__name__)


def create_sketch_on_workplane(context: Context, wp_empty, operator: Operator):
    """Create and activate a Curves sketch parented to ``wp_empty``.

    Shared by the interactive Add Sketch operator and the direct
    keyboard-driven origin-plane operator so both build the sketch identically.
    Returns the wrapped :class:`Sketch`.
    """
    from ..model.sketch_ref import Sketch, stamp_sketch_props
    from ..utilities.curve_data import _ensure_convert_modifier

    # Create sketch as a Curves object (parent provides the transform)
    curve = bpy.data.hair_curves.new("Sketch")
    sketch_obj = bpy.data.objects.new("Sketch", curve)

    scene = context.scene
    if sketch_obj.name not in scene.collection.objects:
        scene.collection.objects.link(sketch_obj)

    stamp_sketch_props(sketch_obj)
    _ensure_convert_modifier(sketch_obj)

    # Parent to workplane empty (before activate so align_view works)
    wp_orig = wp_empty.original if hasattr(wp_empty, "original") else wp_empty
    sketch_obj.parent = wp_orig
    sketch_obj.lock_location = (True, True, True)
    sketch_obj.lock_rotation = (True, True, True)
    sketch_obj.lock_scale = (True, True, True)

    sketch = Sketch(sketch_obj)

    origin = PointRef.create(sketch, (0.0, 0.0), fixed=True, is_origin=True)
    assert origin is not None, "Failed to create origin point"

    activate_sketch(context, sketch_obj, operator)
    return sketch


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
            empty = self._create_wp_empty_from_face(context, a, b)
            if empty:
                return self._use_workplane(empty)

        return None

    def _create_wp_empty_from_face(self, context, ob, face_index):
        """Create a workplane Empty anchored to a mesh face.

        The empty is not parented to the mesh; instead it is anchored to the
        face via a persistent id and the depsgraph handler re-derives its
        transform from the evaluated mesh, so it follows edits and deformation
        (see utilities/face_anchor).
        """
        from ..stateful_operator.utilities.geometry import get_evaluated_obj
        from ..utilities.face_anchor import stamp_face_anchor

        empty = bpy.data.objects.new("Workplane", None)
        empty.empty_display_type = "PLAIN_AXES"
        empty.empty_display_size = 0.5
        context.scene.collection.objects.link(empty)

        empty.matrix_world = face_workplane_matrix(context, ob, face_index)

        # face_index is an evaluated-mesh index; it only maps to an original face
        # (which the anchor stamps a persistent id on) when no modifier changed
        # the topology. When it doesn't line up (Solidify/Bevel/etc.), leave the
        # empty as a plain fixed workplane rather than anchor the wrong face or
        # index out of range (issue #342-adjacent crash on box.blend meshes).
        orig = ob.data
        eval_mesh = get_evaluated_obj(context, ob).data
        if (
            hasattr(orig, "polygons")
            and hasattr(eval_mesh, "polygons")
            and len(eval_mesh.polygons) == len(orig.polygons)
        ):
            stamp_face_anchor(empty, ob, face_index)
        return empty

    def prepare_origin_elements(self, context):
        ensure_origin_workplane_empties(context)
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
