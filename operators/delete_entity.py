import logging

from bpy.utils import register_classes_factory
from bpy.props import IntProperty, BoolProperty
from bpy.types import Operator, Context

from ..model.types import SlvsSketch
from ..utilities.view import refresh
from ..declarations import Operators
from ..utilities.ui import show_ui_message_popup
from ..utilities.data_handling import (
    get_constraint_local_indices,
    get_entity_deps,
    get_sketch_deps_indicies,
    is_entity_dependency,
)
from ..utilities.highlighting import HighlightElement
from .utilities import activate_sketch
from ..solver import solve_system

logger = logging.getLogger(__name__)


class View3D_OT_slvs_delete_entity(Operator, HighlightElement):
    """Delete Entity by index or based on the selection if index isn't provided"""

    bl_idname = Operators.DeleteEntity
    bl_label = "Delete Entity"
    bl_description = (
        "Delete Entity by index or based on the selection if index isn't provided"
    )
    bl_options = {"UNDO"}

    index: IntProperty(default=-1)
    do_report: BoolProperty(
        name="Report", description="Report entities that prevent deletion", default=True
    )

    @staticmethod
    def main(context: Context, index: int, operator: Operator):
        entities = context.scene.sketcher.entities
        entity = entities.get(index)

        if not entity:
            return {"CANCELLED"}

        if isinstance(entity, SlvsSketch):
            if context.scene.sketcher.active_sketch_i != -1:
                activate_sketch(context, -1, operator)
            entity.remove_objects()

            deps = get_sketch_deps_indicies(entity, context)

            for i in reversed(deps):
                operator.delete(entities.get(i), context)

        elif is_entity_dependency(entity, context):
            if operator.do_report:
                deps = list(get_entity_deps(entity, context))
                msg_deps = "\n".join([f" - {d}" for d in deps])
                message = f"Unable to delete {entity.name}, other entities depend on it:\n{msg_deps}"
                show_ui_message_popup(message=message, icon="ERROR")

                operator.report(
                    {"WARNING"},
                    "Cannot delete {}, other entities depend on it.".format(
                        entity.name
                    ),
                )
            return {"CANCELLED"}

        operator.delete(entity, context)

    @staticmethod
    def delete(entity, context: Context):
        entity.selected = False

        # Delete constraints that depend on entity
        constraints = context.scene.sketcher.constraints

        for data_coll, indices in get_constraint_local_indices(entity, context):
            if not indices:
                continue
            for i in reversed(indices):
                logger.debug("Delete: {}, {}".format(data_coll, i))
                data_coll.remove(i)

        logger.debug("Delete: {}".format(entity))
        entities = context.scene.sketcher.entities
        entities.remove(entity.slvs_index)

    def execute(self, context: Context):
        index = self.index
        selected = context.scene.sketcher.entities.selected_active

        if index != -1:
            # Entity is specified via property
            self.main(context, index, self)
        elif len(selected) == 1:
            # Treat single selection same as specified entity
            self.main(context, selected[0].slvs_index, self)
        else:
            # Batch deletion
            indices = []
            for e in selected:
                indices.append(e.slvs_index)

            indices.sort(reverse=True)
            for i in indices:
                e = context.scene.sketcher.entities.get(i)

                # NOTE: this might be slow when a lot of entities are selected, improve!
                if is_entity_dependency(e, context):
                    continue
                self.delete(e, context)

        solve_system(context, context.scene.sketcher.active_sketch)
        refresh(context)
        return {"FINISHED"}


register, unregister = register_classes_factory((View3D_OT_slvs_delete_entity,))
