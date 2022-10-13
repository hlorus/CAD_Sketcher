from bpy.utils import register_classes_factory
from bpy.types import Operator, Context


from .. import global_data
from ..declarations import Operators
from ..serialize import paste


class View3D_OT_slvs_copy(Operator):
    """Copy selected entities"""

    bl_idname = Operators.Copy
    bl_label = "Copy"
    bl_options = {"UNDO"}

    def execute(self, context: Context):
        sse = context.scene.sketcher.entities
        entities = sse.selected_entities
        buffer = {"entities": {}, "constraints": {}}

        for e in entities:
            collection_name = sse.collection_name_from_index(e.slvs_index)
            entity_list = buffer["entities"].setdefault(collection_name, [])
            entity_list.append(dict(e))

        global_data.COPY_BUFFER = buffer
        print("copy", global_data.COPY_BUFFER)
        return {"FINISHED"}


class View3D_OT_slvs_paste(Operator):
    """Paste copied entities"""

    bl_idname = Operators.Paste
    bl_label = "Paste"
    bl_options = {"UNDO"}

    def execute(self, context: Context):
        print("paste", global_data.COPY_BUFFER)
        paste(context, global_data.COPY_BUFFER)
        return {"FINISHED"}


register, unregister = register_classes_factory(
    (View3D_OT_slvs_copy, View3D_OT_slvs_paste)
)
