import logging

import bpy
from bpy.app.handlers import persistent

logger = logging.getLogger(__name__)

_builtin_handlers = {}


# Utility functions to simplify registering bpy.app handlers
#
# Builtin handlers have to be registered and unregistered,
# call register_handlers after all modules are registered and
# vice versa when unregistering
#
# Example usage:
# from event_system import add_builtin_handler
#
# add_builtin_handler("save_pre", write_addon_version)
# add_builtin_handler("version_update", do_versioning)


def add_builtin_handler(event: str, callback):
    """
    Add to bpy.app.handlers, gets (un)registered on addon enable or disabled.
    Does not support registering handlers at runtime
    """

    global _builtin_handlers
    func = persistent(callback)
    _builtin_handlers.setdefault(event, list()).append(func)


def register_handlers():
    global _builtin_handlers
    for handler_name in _builtin_handlers.keys():
        msg = "Append <{}> builtin handlers: ".format(handler_name)

        for cb in _builtin_handlers[handler_name]:
            getattr(bpy.app.handlers, handler_name).append(cb)
            msg += "\n  - {}".format(cb.__name__)

        logger.debug(msg)


def unregister_handlers():
    global _builtin_handlers
    for handler_name in _builtin_handlers.keys():
        msg = "Remove <{}> builtin handlers: ".format(handler_name)

        for cb in _builtin_handlers[handler_name]:
            handler_list = getattr(bpy.app.handlers, handler_name)

            if cb not in handler_list:
                continue

            msg += "\n  - {}".format(cb.__name__)
            handler_list.remove(cb)

        logger.debug(msg)


def on_load_post(*args):
    """Migrate legacy entity-based sketches to native curves on file load."""
    from .utilities.migrate import scene_needs_migration, migrate_scene
    from .utilities.validate import reset_cache

    reset_cache()
    context = bpy.context
    try:
        if scene_needs_migration(context):
            summary = migrate_scene(context)
            logger.info("Migrated legacy sketches to curves: %s", summary)
    except Exception:
        logger.exception("Legacy sketch migration failed")


def on_depsgraph_update(scene, depsgraph):
    from . import global_data

    # Keep face-anchored workplanes on their mesh face as geometry changes.
    from .utilities.face_anchor import update_face_workplanes
    update_face_workplanes(bpy.context, depsgraph)

    # Repair invariants if a built-in tool edited our curve data outside the
    # addon. Skip while one of our operators is mid-run (it owns the data and
    # keeps invariants itself).
    if not global_data.stateful_op_running:
        from .utilities.validate import validate_all_sketches
        if validate_all_sketches(scene):
            global_data.needs_solve = True

    if depsgraph.id_type_updated("SCENE"):
        global_data.needs_solve = True

    if global_data.needs_solve:
        if global_data.stateful_op_running:
            return

        global_data.needs_solve = False
        from .curve_solver import solve_system
        from .model.sketch_ref import get_active_sketch

        context = bpy.context
        sketch = get_active_sketch(context)
        solve_system(context, sketch=sketch)

    if global_data.needs_redraw:
        global_data.needs_redraw = False
        context = bpy.context
        if context.space_data and context.space_data.type == "VIEW_3D":
            context.space_data.show_gizmo = True


def _setup_builtin_handlers():
    from .versioning import do_versioning, write_addon_version

    add_builtin_handler("version_update", do_versioning)
    add_builtin_handler("save_pre", write_addon_version)
    add_builtin_handler("load_post", on_load_post)
    add_builtin_handler("depsgraph_update_post", on_depsgraph_update)


def register():
    _setup_builtin_handlers()
    register_handlers()


def unregister():
    unregister_handlers()
