from bpy.types import Context

from ..solver import solve_system


def update_system_cb(self, context: Context):
    """Update scene and re-run the solver, used as a property update callback"""
    sketch = context.scene.sketcher.active_sketch
    solve_system(context, sketch=sketch)
