from bpy.types import Operator, Context
from bpy.props import IntProperty
from bpy.utils import register_classes_factory

from ..declarations import Operators


class View3D_OT_slvs_show_solver_state(Operator):
    """Show details about solver status"""

    bl_idname = Operators.ShowSolverState
    bl_label = "Solver Status"

    index: IntProperty(default=-1)

    def execute(self, context: Context):
        from ..model.sketch_ref import get_active_sketch

        sketch = get_active_sketch(context)
        if not sketch:
            return {"CANCELLED"}

        def draw_item(self, context: Context):
            layout = self.layout
            state = sketch.get_solver_state()

            row = layout.row(align=True)
            row.alignment = "LEFT"
            row.label(text=state.name, icon=state.icon)

            layout.separator()
            layout.label(text=state.description)

        context.window_manager.popup_menu(draw_item)
        return {"FINISHED"}


register, unregister = register_classes_factory((View3D_OT_slvs_show_solver_state,))
