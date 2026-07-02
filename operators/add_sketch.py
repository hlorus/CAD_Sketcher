import logging

import bpy
from bpy.types import Operator, Context, Event

from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from ..stateful_operator.state import state_from_args
from .. import global_data
from .base_3d import Operator3d
from .utilities import activate_sketch, switch_sketch_mode
from ..utilities.workplane import ensure_origin_workplane_empties, get_workplane_empty_by_id
from ..model.curve_ref import PointRef


logger = logging.getLogger(__name__)


# TODO:
# - Draw sketches
class View3D_OT_slvs_add_sketch(Operator, Operator3d):
    """Add a sketch"""

    bl_idname = Operators.AddSketch
    bl_label = "Add Sketch"
    bl_options = {"UNDO"}

    sketch_state1_doc = ["Workplane", "Pick a workplane as base for the sketch."]

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

    def pick_element(self, context, coords):
        # Try native empty picking (screen-space projection)
        result = super().pick_element(context, coords)
        if result is not None:
            return result

        # Try overlay ID buffer picking (for workplane rectangles)
        from ..draw_handler import draw_selection_buffer
        from ..utilities.index import rgb_to_index
        import gpu

        draw_selection_buffer(context)
        offscreen = global_data.offscreen
        if offscreen:
            mx, my = int(coords.x), int(coords.y)
            with offscreen.bind():
                fb = gpu.state.active_framebuffer_get()
                buffer = fb.read_color(mx, my, 1, 1, 4, 0, "FLOAT")
            r, g, b, alpha = buffer[0][0]
            if alpha > 0:
                wp_empty = get_workplane_empty_by_id(rgb_to_index(r, g, b))
                if wp_empty:
                    self.state_data["is_existing_entity"] = True
                    self.state_data["type"] = bpy.types.Object
                    return wp_empty.name
        return None

    def prepare_origin_elements(self, context):
        ensure_origin_workplane_empties(context)
        return True

    def _set_wp_visibility(self, context, visible):
        """Show/hide origin workplane empties."""
        sketcher = context.scene.sketcher
        for wp in (sketcher.wp_xy, sketcher.wp_xz, sketcher.wp_yz):
            if wp:
                wp.hide_viewport = not visible

    def init(self, context: Context, event: Event):
        switch_sketch_mode(self, context, to_sketch_mode=True)
        self.prepare_origin_elements(context)
        bpy.ops.ed.undo_push(message="Ensure Origin Elements")
        context.scene.sketcher.show_origin = True
        self._set_wp_visibility(context, True)
        return True

    def main(self, context: Context):
        from ..model.sketch_ref import Sketch
        from ..utilities.curve_data import ensure_sketch_curve_object

        wp_empty = self.wp  # Always an Object (empty)
        if not wp_empty:
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
        context.scene.sketcher.show_origin = False
        self._set_wp_visibility(context, False)
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))

        if not succeed:
            switch_sketch_mode(self, context, to_sketch_mode=False)


register, unregister = register_stateops_factory((View3D_OT_slvs_add_sketch,))
