from copy import deepcopy
from typing import Any, List, Sequence, Tuple

import bpy
from bpy.utils import register_classes_factory
from bpy.types import Operator, Context

from .. import global_data
from ..declarations import Operators
from ..serialize import paste
from ..utilities.select import deselect_all
from ..utilities.data_handling import (
    get_collective_dependencies,
    get_scoped_constraints,
)
from ..serialize import iter_elements_dict


def _filter_elements_dict(
    data, dict_elements: Sequence[tuple[str, list]], whitelist: Sequence[Any]
) -> List[tuple[str, list]]:
    """
    Returns filtered list of elements based on whitelist

    dict_elements must be the dictionary representation of whats stored in data without any modifications
    """

    filtered_elements_dict = {}
    for collection_name, elements in dict_elements.items():
        if not isinstance(elements, list):
            continue

        # Get the actual element corresponding to the dict representation
        for i, element_dict in enumerate(elements):
            element_collection = getattr(data, collection_name)
            element = element_collection[i]

            if element not in whitelist:
                continue

            filtered_elements_dict.setdefault(collection_name, []).append(element_dict)

    return filtered_elements_dict


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

        # Get the whole scene dictionary representation
        scene_dict = context.scene["sketcher"].to_dict()

        # Get dependencies of selected entities
        dependencies = list(
            filter(
                lambda x: x.is_2d(), get_collective_dependencies(sse.selected_active)
            )
        )

        # Get filtered entities dictionary based on selected entities and their dependencies
        buffer["entities"] = _filter_elements_dict(
            context.scene.sketcher.entities, scene_dict["entities"], dependencies
        )

        # Get filtered constraints dictionary based on selected entities and their dependencies
        constraints = get_scoped_constraints(context, dependencies)
        buffer["constraints"] = _filter_elements_dict(
            context.scene.sketcher.constraints, scene_dict["constraints"], constraints
        )

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
