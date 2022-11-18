import bpy
from bpy.utils import register_classes_factory
from bpy.props import IntProperty, StringProperty
from bpy.types import Operator, Context, Event
from mathutils import Vector
from mathutils.geometry import intersect_line_plane

from ..declarations import Operators
from ..utilities.view import get_picking_origin_end


class View3D_OT_slvs_tweak_constraint_value_pos(Operator):
    bl_idname = Operators.TweakConstraintValuePos
    bl_label = "Tweak Constraint"
    bl_description = "Tweak constraint's value or display position"
    bl_options = {"UNDO"}

    type: StringProperty(name="Type")
    index: IntProperty(default=-1)

    def invoke(self, context: Context, event: Event):
        self.tweak = False
        self.init_mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context: Context, event: Event):
        delta = (
            self.init_mouse_pos - Vector((event.mouse_region_x, event.mouse_region_y))
        ).length
        if not self.tweak and delta > 6:
            self.tweak = True

        if event.type == "LEFTMOUSE" and event.value == "RELEASE":
            if not self.tweak:
                self.execute(context)
            return {"FINISHED"}

        if not self.tweak:
            return {"RUNNING_MODAL"}

        coords = event.mouse_region_x, event.mouse_region_y

        constraints = context.scene.sketcher.constraints
        constr = constraints.get_from_type_index(self.type, self.index)

        origin, end_point = get_picking_origin_end(context, coords)
        pos = intersect_line_plane(origin, end_point, *constr.draw_plane())

        mat = constr.matrix_basis()
        pos = mat.inverted() @ pos

        constr.update_draw_offset(pos, context.preferences.system.ui_scale)
        context.space_data.show_gizmo = True
        return {"RUNNING_MODAL"}

    def execute(self, context: Context):
        bpy.ops.view3d.slvs_context_menu(type=self.type, index=self.index)
        return {"FINISHED"}


register, unregister = register_classes_factory(
    (View3D_OT_slvs_tweak_constraint_value_pos,)
)
