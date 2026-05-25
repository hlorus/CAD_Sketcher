from bpy.types import Operator, Context
from bpy.props import IntProperty
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..model.types import SlvsLine2D


class View3D_OT_slvs_flip_line_direction(Operator):
    """Swap a line's p1 and p2 endpoints."""

    bl_idname = Operators.FlipLineDirection
    bl_label = "Flip Line Direction"
    bl_options = {"UNDO"}

    line_index: IntProperty(default=-1)

    def execute(self, context: Context):
        sse = context.scene.sketcher.entities
        line = sse.get(self.line_index)
        if not isinstance(line, SlvsLine2D):
            self.report({"ERROR"}, "No valid Line2D selected")
            return {"CANCELLED"}

        print(f"Flipping line direction: {line.name} (slvs_index={line.slvs_index})")
        print(f"  before p1: {line.p1.name} (slvs_index={line.p1.slvs_index})")
        print(f"  before p2: {line.p2.name} (slvs_index={line.p2.slvs_index})")

        line.p1, line.p2 = line.p2, line.p1

        print(f"  after p1: {line.p1.name} (slvs_index={line.p1.slvs_index})")
        print(f"  after p2: {line.p2.name} (slvs_index={line.p2.slvs_index})")
        return {"FINISHED"}


register, unregister = register_classes_factory((View3D_OT_slvs_flip_line_direction,))
