from bpy.types import Context

from .. import global_data


def update_system_cb(self, context: Context):
    """Mark that the solver needs to run, deferred to depsgraph_update_post."""
    global_data.needs_solve = True


def constraint_value_update_cb(self, context: Context):
    """Mark that the solver needs to run when a constraint value changes."""
    global_data.needs_solve = True
