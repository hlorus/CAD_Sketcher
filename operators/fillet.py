"""Operator: add the generic ``CAD Sketcher Fillet`` modifier to the active object.

The fillet is a plain geometry-nodes modifier that rounds the corners of an
object's output geometry. This just adds and selects it on the active object (a
sketch's curves object, a mesh output, or any mesh/curve); all tuning happens on
the modifier's Radius / Count / Fill inputs.
"""

from bpy.props import FloatProperty
from bpy.types import Context, Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..utilities.fillet_nodes import build_fillet_node_group, fillet_input_ids
from .modifiers import set_modifier_input


class View3D_OT_slvs_add_fillet(Operator):
    """Round the corners of the active object's output with a Fillet modifier"""

    bl_idname = Operators.AddFillet
    bl_label = "Add Fillet"
    bl_options = {"REGISTER", "UNDO"}

    radius: FloatProperty(
        name="Radius",
        description="Corner radius",
        default=0.1,
        min=0.0,
        subtype="DISTANCE",
    )

    @classmethod
    def poll(cls, context: Context) -> bool:
        ob = context.object
        return ob is not None and ob.type in {"MESH", "CURVES", "CURVE"}

    def execute(self, context: Context):
        ob = context.object
        group = build_fillet_node_group()
        modifier = ob.modifiers.new("CAD Sketcher Fillet", "NODES")
        modifier.node_group = group
        set_modifier_input(modifier, fillet_input_ids(group)["Radius"], self.radius)
        return {"FINISHED"}


register, unregister = register_classes_factory((View3D_OT_slvs_add_fillet,))
