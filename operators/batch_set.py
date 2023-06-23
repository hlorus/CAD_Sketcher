from bpy.types import Operator
from bpy.props import BoolProperty, StringProperty
from bpy.utils import register_class, unregister_class

from ..declarations import Operators
from ..utilities.view import refresh


class View3D_OT_slvs_batch_set(Operator):
    """Batch set a property on all items in a given sequence"""

    bl_idname = Operators.BatchSet
    bl_label = "Batch Set"
    bl_options = {"UNDO"}

    data_path: StringProperty(
        name="Data Path",
        description="Data path to resolve from the context e.g. 'context.scene'",
    )
    sequence: StringProperty(name="Sequence")
    property: StringProperty(name="Property")
    value: BoolProperty(name="Value")

    def execute(self, context):
        data_path = context.path_resolve(self.data_path)
        for entity in getattr(data_path, self.sequence):
            setattr(entity, self.property, self.value)
        refresh(context)
        return {"FINISHED"}


def register():
    register_class(View3D_OT_slvs_batch_set)


def unregister():
    unregister_class(View3D_OT_slvs_batch_set)
