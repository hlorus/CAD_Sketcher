from bpy.types import Context

from .. import global_data


def update_system_cb(self, context: Context):
    """Mark that the solver needs to run, deferred to depsgraph_update_post."""
    global_data.needs_solve = True


def constraint_value_update_cb(self, context: Context):
    """Mark that the solver needs to run and sync the stable driver endpoint."""
    global_data.needs_solve = True
    scene = getattr(self, "id_data", None)
    if not scene:
        return
    key = scene.sketcher.get_or_create_constraint_value_endpoint(self)
    if not key:
        return
    scene[key] = self.value
