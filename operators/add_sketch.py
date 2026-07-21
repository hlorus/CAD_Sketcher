import logging

import bpy
from bpy.types import Operator, Context, Event

from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from ..stateful_operator.state import state_from_args
from .base_3d import Operator3d
from .utilities import activate_sketch
from ..utilities.workplane import ensure_origin_workplane_empties, resolve_sketch_base
from ..utilities.geometry import face_workplane_matrix
from ..model.curve_ref import PointRef


logger = logging.getLogger(__name__)


# TODO:
# - Draw sketches
class View3D_OT_slvs_add_sketch(Operator, Operator3d):
    """Add a sketch"""

    bl_idname = Operators.AddSketch
    bl_label = "Add Sketch"
    bl_options = {"UNDO"}

    sketch_state1_doc = ["Workplane", "Pick a workplane or mesh face as base for the sketch."]

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
        return [o for o in context.selected_objects if o.type == 'EMPTY']

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
        """Create a workplane Empty aligned to a mesh face."""
        empty = bpy.data.objects.new("Workplane", None)
        empty.empty_display_type = 'PLAIN_AXES'
        empty.empty_display_size = 0.5
        context.scene.collection.objects.link(empty)

        empty.matrix_world = face_workplane_matrix(context, ob, face_index)
        empty.parent = ob
        empty.matrix_parent_inverse = ob.matrix_world.inverted()
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
        from ..model.sketch_ref import Sketch
        from ..utilities.curve_data import ensure_sketch_curve_object

        wp_empty = self.wp
        if not wp_empty or wp_empty.type != 'EMPTY':
            self.report({'WARNING'}, "Please select an Empty as workplane")
            return False

        # Create sketch as a Curves object (parent provides the transform)
        curve = bpy.data.hair_curves.new("Sketch")
        sketch_obj = bpy.data.objects.new("Sketch", curve)

        scene = context.scene
        if sketch_obj.name not in scene.collection.objects:
            scene.collection.objects.link(sketch_obj)

        # Stamp sketch custom properties
        from ..model.sketch_ref import stamp_sketch_props
        stamp_sketch_props(sketch_obj)

        # Add GN modifier
        from ..utilities.curve_data import _ensure_convert_modifier
        _ensure_convert_modifier(sketch_obj)

        # Parent to workplane empty (before activate so align_view works)
        wp_orig = wp_empty.original if hasattr(wp_empty, 'original') else wp_empty
        sketch_obj.parent = wp_orig
        sketch_obj.lock_location = (True, True, True)
        sketch_obj.lock_rotation = (True, True, True)
        sketch_obj.lock_scale = (True, True, True)

        # Wrap as Sketch accessor
        sketch = Sketch(sketch_obj)

        # Add origin point
        origin = PointRef.create(sketch, (0.0, 0.0), fixed=True)
        assert origin is not None, "Failed to create origin point"

        activate_sketch(context, sketch_obj, self)
        self.target = sketch
        return True

    def fini(self, context: Context, succeed: bool):
        # NOTE: don't switch tools here — a cancel also happens when a click
        # simply misses a valid target, and we want to stay on the Add Sketch
        # tool then. Explicit ESC/RMB -> select is handled by the tool keymap.
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))


register, unregister = register_stateops_factory((View3D_OT_slvs_add_sketch,))
