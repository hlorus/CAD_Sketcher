import bpy
from bpy.utils import register_classes_factory
from bpy.types import Operator, Context

from .. import global_data
from ..declarations import Operators
from ..serialize import paste
from ..utilities.select import deselect_all
from ..serialize import iter_elements_dict


class View3D_OT_slvs_copy(Operator):
    """Copy selected entities"""

    bl_idname = Operators.Copy
    bl_label = "Copy"
    bl_options = {"UNDO"}

    def execute(self, context: Context):
        buffer = {"entities": {}, "constraints": {}}
        entities_dict = context.scene.sketcher["entities"].to_dict()

        # Only copy etities that are selected
        for entity_collection_name, entities in entities_dict.items():
            if not isinstance(entities, list):
                continue
            for entity in entities:
                if not "slvs_index" in entity.keys():
                    continue
                if not entity["slvs_index"] in global_data.selected:
                    continue

                entity_list = buffer["entities"].setdefault(entity_collection_name, [])
                entity_list.append(entity)

        global_data.COPY_BUFFER = buffer
        print("copy", global_data.COPY_BUFFER)
        return {"FINISHED"}


class View3D_OT_slvs_paste(Operator):
    """Paste copied entities"""

    bl_idname = Operators.Paste
    bl_label = "Paste"
    bl_options = {"UNDO"}

    def execute(self, context: Context):
        buffer = global_data.COPY_BUFFER
        print("paste", buffer)
        paste(context, buffer.copy())

        deselect_all(context)

        # Select all pasted entities
        for element in iter_elements_dict(buffer):
            if not "slvs_index" in element.keys():
                continue

            index = element["slvs_index"]
            entity = context.scene.sketcher.entities.get(index)
            if not entity:
                continue
            entity.selected = True

        context.area.tag_redraw()

        bpy.ops.view3d.slvs_move("INVOKE_DEFAULT")
        return {"FINISHED"}


register, unregister = register_classes_factory(
    (View3D_OT_slvs_copy, View3D_OT_slvs_paste)
)
