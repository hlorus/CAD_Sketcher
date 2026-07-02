from bpy.types import Operator, Context
from bpy.props import IntProperty, StringProperty, BoolProperty
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..model.curve_ref import curve_ref


class View3D_OT_slvs_set_curve_flag(Operator):
    """Toggle a flag on a curve"""

    bl_idname = Operators.SetCurveFlag
    bl_label = "Set Curve Flag"
    bl_options = {"UNDO"}

    curve_id: IntProperty()
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
        context.area.tag_redraw()
        return {"FINISHED"}


register, unregister = register_classes_factory((View3D_OT_slvs_set_curve_flag,))
