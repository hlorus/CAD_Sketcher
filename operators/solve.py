from bpy.types import Operator, Context
from bpy.props import BoolProperty
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..solver import Solver


class View3D_OT_slvs_solve(Operator):
    bl_idname = Operators.Solve
    bl_label = "Solve"

    all: BoolProperty(name="Solve All", options={"SKIP_SAVE"})

    def execute(self, context: Context):
        sketch = context.scene.sketcher.active_sketch
        solver = Solver(context, sketch, all=self.all)
        ok = solver.solve()

        # Keep messages simple, sketches are marked with solvestate
        if ok:
            self.report({"INFO"}, "Successfully solved")
        else:
            self.report({"WARNING"}, "Solver failed")

        context.area.tag_redraw()
        return {"FINISHED"}


register, unregister = register_classes_factory((View3D_OT_slvs_solve,))
