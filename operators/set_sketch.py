from bpy.utils import register_classes_factory
from bpy.props import IntProperty
from bpy.types import Operator, Context


from ..declarations import Operators
from .utilities import activate_sketch


class View3D_OT_slvs_set_active_sketch(Operator):
    """Set the active sketch"""

    bl_idname = Operators.SetActiveSketch
    bl_label = "Set active Sketch"
    bl_options = {"UNDO"}

    index: IntProperty(default=-1)

    def execute(self, context: Context):
        return activate_sketch(context, self.index, self)


register, unregister = register_classes_factory((View3D_OT_slvs_set_active_sketch,))
