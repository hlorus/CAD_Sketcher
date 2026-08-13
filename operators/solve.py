from bpy.props import BoolProperty
from bpy.types import Context, Operator
from bpy.utils import register_classes_factory

from ..curve_solver import solve_system
from ..declarations import Operators
from ..model.sketch_ref import get_active_sketch, get_sketches
from ..solver_3d import solve_system_3d


class View3D_OT_slvs_solve(Operator):
    bl_idname = Operators.Solve
    bl_label = "Solve"

    all: BoolProperty(name="Solve All", options={"SKIP_SAVE"})

    def execute(self, context: Context):
        if self.all:
            ok_3d = solve_system_3d(context)
            sketches = list(get_sketches(context))
            ok = ok_3d and all(solve_system(context, sketch=s) for s in sketches)
        else:
            sketch = get_active_sketch(context)
            if sketch:
                ok = solve_system(context, sketch=sketch)
            else:
                ok = solve_system_3d(context)

        # Keep messages simple, sketches are marked with solvestate
        if ok:
            self.report({"INFO"}, "Successfully solved")
        else:
            self.report({"WARNING"}, "Solver failed")

        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


register, unregister = register_classes_factory((View3D_OT_slvs_solve,))
