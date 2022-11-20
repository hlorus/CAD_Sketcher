from copy import deepcopy

import bpy
from bpy.utils import register_classes_factory
from bpy.types import Operator, Context

from .. import global_data
from ..declarations import Operators
from ..serialize import paste
from ..utilities.select import deselect_all
from ..utilities.data_handling import get_collective_dependencies
from ..serialize import iter_elements_dict


class View3D_OT_slvs_copy(Operator):
    """Copy selected entities"""

    bl_idname = Operators.Copy
    bl_label = "Copy"
    bl_options = {"UNDO"}

    def execute(self, context: Context):
        if context.scene.sketcher.active_sketch_i == -1:
            self.report({"INFO"}, "Copying is not supported in 3d space")
            return {"CANCELLED"}

        sse = context.scene.sketcher.entities
        buffer = {"entities": {}, "constraints": {}}
        entities_dict = context.scene.sketcher["entities"].to_dict()

        # Copy selected entities along with their dependencies
        entities = filter(
            lambda x: x.is_2d(), get_collective_dependencies(sse.selected_entities)
        )
        whitelist = [e.slvs_index for e in entities]

        # Only copy etities that are selected
        for entity_collection_name, entities in entities_dict.items():
            if not isinstance(entities, list):
                continue
            for entity in entities:
                if not "slvs_index" in entity.keys():
                    continue
                if not entity["slvs_index"] in whitelist:
                    continue

                entity_list = buffer["entities"].setdefault(entity_collection_name, [])
                entity_list.append(entity)
        global_data.COPY_BUFFER = buffer
        return {"FINISHED"}


class View3D_OT_slvs_paste(Operator):
    """Paste copied entities"""

    bl_idname = Operators.Paste
    bl_label = "Paste"
    bl_options = {"UNDO"}

    def execute(self, context: Context):
        if context.scene.sketcher.active_sketch_i == -1:
            self.report({"INFO"}, "Pasting is not supported in 3d space")
            return {"CANCELLED"}

        buffer = deepcopy(global_data.COPY_BUFFER)

        # Replace sketch indices with active sketch
        for element in iter_elements_dict(buffer):
            if not "sketch_i" in element.keys():
                continue
            element["sketch_i"] = context.scene.sketcher.active_sketch_i

        paste(context, buffer)
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
