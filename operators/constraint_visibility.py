from bpy.utils import register_classes_factory
from bpy.props import EnumProperty
from bpy.types import Operator, Context

from ..utilities.highlighting import HighlightElement
from ..declarations import Operators, VisibilityTypes


class View3D_OT_slvs_set_all_constraints_visibility(Operator, HighlightElement):
    """Set all constraints' visibility"""

    bl_idname = Operators.SetAllConstraintsVisibility
    bl_label = "Set all constraints' visibility"
    bl_description = "Set all constraints' visibility"
    bl_options = {"UNDO"}

    _visibility_items = [
        (VisibilityTypes.Hide, "Hide all", "Hide all constraints"),
        (VisibilityTypes.Show, "Show all", "Show all constraints"),
    ]

    visibility: EnumProperty(
        name="Visibility", description="Visibility", items=_visibility_items
    )

    @classmethod
    def poll(cls, context: Context):
        return True

    @classmethod
    def description(cls, context: Context, properties):
        for vi in cls._visibility_items:
            if vi[0] == properties.visibility:
                return vi[2]
        return None

    def execute(self, context: Context):
        constraint_lists = context.scene.sketcher.constraints.get_lists()
        for constraint_list in constraint_lists:
            for constraint in constraint_list:
                if not hasattr(constraint, "visible"):
                    continue
                constraint.visible = self.visibility == "SHOW"
        return {"FINISHED"}


register, unregister = register_classes_factory(
    (View3D_OT_slvs_set_all_constraints_visibility,)
)
