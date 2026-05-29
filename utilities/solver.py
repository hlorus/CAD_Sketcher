from bpy.types import Context

from .. import global_data


def update_system_cb(self, context: Context):
    """Mark that the solver needs to run, deferred to depsgraph_update_post."""
    scene = getattr(context, "scene", None) if context is not None else None
    sketcher = getattr(scene, "sketcher", None) if scene is not None else None
    if sketcher is not None and not getattr(sketcher, "geometry_solved", True):
        return

    if not global_data.needs_solve:
        print(
            "[CAD_Sketcher] needs_solve=True by "
            f"{type(self).__name__}"
        )
    global_data.needs_solve = True
