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


class View3D_OT_slvs_flip_linked_sketch_y(Operator):
    """Flip linked sketch Y direction for sketches driven by this linking line."""

    bl_idname = Operators.FlipLinkedSketchY
    bl_label = "Flip Linked Sketch Y"
    bl_options = {"UNDO"}

    line_index: IntProperty(default=-1)

    def execute(self, context: Context):
        sse = context.scene.sketcher.entities
        line = sse.get(self.line_index)
        if not isinstance(line, SlvsLine2D):
            self.report({"ERROR"}, "No valid Line2D selected")
            return {"CANCELLED"}

        changed = 0
        for sketch in sse.sketches:
            if getattr(sketch, "source_line_i", -1) != line.slvs_index:
                continue
            sketch.linked_y_inverted = not getattr(sketch, "linked_y_inverted", False)
            changed += 1

        if not changed:
            self.report({"WARNING"}, "No linked sketches driven by this line")
            return {"CANCELLED"}

        from ..handlers import update_linked_sketches
        from .. import global_data

        update_linked_sketches(context.scene)
        global_data.needs_redraw = True

        self.report({"INFO"}, f"Flipped linked Y for {changed} sketch(es)")
        return {"FINISHED"}


register, unregister = register_classes_factory(
    (View3D_OT_slvs_flip_line_direction, View3D_OT_slvs_flip_linked_sketch_y)
)
