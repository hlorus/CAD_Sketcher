from bpy.types import Operator, Context, Event
from bpy.props import StringProperty, BoolProperty
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..model.curve_ref import curve_ref


class View3D_OT_slvs_set_curve_flag(Operator):
    """Toggle a flag on a curve"""

    bl_idname = Operators.SetCurveFlag
    bl_label = "Set Curve Flag"
    bl_options = {"UNDO"}

    curve_id: StringProperty()
    flag: StringProperty()
    value: BoolProperty()

    def execute(self, context: Context):
        from ..model.sketch_ref import get_active_sketch
        sketch = get_active_sketch(context)
        if not sketch:
            return {"CANCELLED"}

        ref = curve_ref(sketch, self.curve_id)
        if not ref.valid:
            return {"CANCELLED"}

        setattr(ref, self.flag, self.value)
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class View3D_OT_slvs_rename_curve(Operator):
    """Rename this entity"""

    bl_idname = Operators.RenameCurve
    bl_label = "Rename Entity"
    bl_options = {"UNDO"}

    curve_id: StringProperty()
    new_name: StringProperty(name="Name")

    def invoke(self, context: Context, event: Event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: Context):
        self.layout.prop(self, "new_name")

    def execute(self, context: Context):
        from ..model.sketch_ref import get_active_sketch

        sketch = get_active_sketch(context)
        if not sketch:
            return {"CANCELLED"}
        ref = curve_ref(sketch, self.curve_id)
        if not ref.valid:
            return {"CANCELLED"}
        ref.name = self.new_name
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


register, unregister = register_classes_factory(
    (View3D_OT_slvs_set_curve_flag, View3D_OT_slvs_rename_curve)
)
