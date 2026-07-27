from bpy.types import Operator, Context
from ..model.sketch_ref import get_active_sketch, get_sketches
from bpy.props import BoolProperty
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..curve_solver import solve_system


class View3D_OT_slvs_solve(Operator):
    bl_idname = Operators.Solve
    bl_label = "Solve"

    all: BoolProperty(name="Solve All", options={"SKIP_SAVE"})

    def execute(self, context: Context):
        if self.all:
            sketches = list(get_sketches(context))
            ok = all(solve_system(context, sketch=s) for s in sketches)
        else:
            sketch = get_active_sketch(context)
            ok = solve_system(context, sketch=sketch)

        # Keep messages simple, sketches are marked with solvestate
        if ok:
            self.report({"INFO"}, "Successfully solved")
        else:
            self.report({"WARNING"}, "Solver failed")

        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


register, unregister = register_classes_factory((View3D_OT_slvs_solve,))
