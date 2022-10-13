import logging

from bpy.utils import register_classes_factory
from bpy.props import IntProperty, StringProperty
from bpy.types import Operator, Context

from ..utilities.view import refresh
from ..solver import solve_system
from ..declarations import Operators
from ..utilities.highlighting import HighlightElement


logger = logging.getLogger(__name__)


class View3D_OT_slvs_delete_constraint(Operator, HighlightElement):
    """Delete constraint by type and index"""

    bl_idname = Operators.DeleteConstraint
    bl_label = "Delete Constraint"
    bl_description = "Delete Constraint"
    bl_options = {"UNDO"}

    type: StringProperty(name="Type")
    index: IntProperty(default=-1)

    @classmethod
    def description(cls, context, properties):
        cls.handle_highlight_hover(context, properties)
        if properties.type:
            return "Delete: " + properties.type.capitalize()
        return ""

    def execute(self, context: Context):
        constraints = context.scene.sketcher.constraints

        # NOTE: It's not really necessary to first get the
        # constraint from its index before deleting

        constr = constraints.get_from_type_index(self.type, self.index)
        logger.debug("Delete: {}".format(constr))

        constraints.remove(constr)

        sketch = context.scene.sketcher.active_sketch
        solve_system(context, sketch=sketch)
        refresh(context)
        return {"FINISHED"}


register, unregister = register_classes_factory((View3D_OT_slvs_delete_constraint,))
