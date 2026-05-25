# pyright: reportInvalidTypeForm=false
import logging

import bpy
from bpy.types import Operator, Context, Event
from bpy.utils import register_classes_factory
from ..model.types import SlvsWorkplane
from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from ..stateful_operator.state import state_from_args
from .base_3d import Operator3d
from .utilities import activate_sketch, switch_sketch_mode

logger = logging.getLogger(__name__)


def _create_sketch_for_workplane(
    context: Context, wp: SlvsWorkplane, operator: Operator
):
    sse = context.scene.sketcher.entities
    sketch = sse.add_sketch(wp)

    # XY plane -> Plan (normal ~= +/-Z); any other orientation -> Elevation
    if abs(wp.normal.z) > 0.99:
        sketch.tag = "Plan"
    else:
        sketch.tag = "Elevation"

    # Add point at origin
    p = sse.add_point_2d((0.0, 0.0), sketch)
    p.fixed = True

    activate_sketch(context, sketch.slvs_index, operator)
    return sketch


class View3D_OT_slvs_add_sketch_origin_offset(Operator):
    """Create a sketch from an origin workplane with local Z offset."""

    bl_idname = Operators.AddSketchOriginOffset
    bl_label = "Origin Plane Offset"
    bl_options = {"UNDO"}

    wp_index: bpy.props.IntProperty(options={"HIDDEN", "SKIP_SAVE"}, default=-1)
    local_z_offset: bpy.props.FloatProperty(
        name="Local Z Offset",
        description="Offset along the selected origin plane's local Z axis",
        default=0.0,
        unit="LENGTH",
    )

    def invoke(self, context: Context, event: Event):
        return context.window_manager.invoke_props_dialog(self, width=320)

    def draw(self, context: Context):
        self.layout.prop(self, "local_z_offset")

    def execute(self, context: Context):
        sse = context.scene.sketcher.entities
        base_wp = sse.get(self.wp_index)
        if base_wp is None:
            self.report({"ERROR"}, "Invalid origin workplane")
            return {"CANCELLED"}

        origin_co = base_wp.p1.location + (base_wp.normal * self.local_z_offset)
        origin = sse.add_point_3d(origin_co)
        nm = sse.add_normal_3d(base_wp.nm.orientation)
        wp = sse.add_workplane(origin, nm)

        sketch = _create_sketch_for_workplane(context, wp, self)
        wp.visible = False
        logger.debug("Add: {}".format(sketch))
        return {"FINISHED"}


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
            types=(SlvsWorkplane,),
            property=None,
            use_create=False,
        ),
    )

    def prepare_origin_elements(self, context):
        context.scene.sketcher.entities.ensure_origin_elements(context)
        return True

    def init(self, context: Context, event: Event):
        switch_sketch_mode(self, context, to_sketch_mode=True)
        self.prepare_origin_elements(context)
        bpy.ops.ed.undo_push(message="Ensure Origin Elements")
        context.scene.sketcher.show_origin = True
        return True

    def main(self, context: Context):
        if self.wait_for_input and getattr(self.wp, "origin", False):
            bpy.ops.view3d.slvs_add_sketch_origin_offset(
                "INVOKE_DEFAULT", wp_index=self.wp.slvs_index
            )
            return True

        sketch = _create_sketch_for_workplane(context, self.wp, self)
        self.target = sketch
        return True

    def fini(self, context: Context, succeed: bool):
        context.scene.sketcher.show_origin = False
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))

        if succeed:
            self.wp.visible = False
        else:
            switch_sketch_mode(self, context, to_sketch_mode=False)


_register_stateops, _unregister_stateops = register_stateops_factory(
    (View3D_OT_slvs_add_sketch,)
)
_register_classes, _unregister_classes = register_classes_factory(
    (View3D_OT_slvs_add_sketch_origin_offset,)
)


def register():
    _register_stateops()
    _register_classes()


def unregister():
    _unregister_classes()
    _unregister_stateops()
