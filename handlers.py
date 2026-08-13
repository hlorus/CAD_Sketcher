import logging

import bpy
from bpy.app.handlers import persistent

logger = logging.getLogger(__name__)

_builtin_handlers = {}


def add_builtin_handler(event: str, callback):
    """Add a callback to bpy.app.handlers for addon lifetime."""
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
    from .drawing import overlay, selection
    overlay.invalidate()
    selection.clear()
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

    # Keep mesh-projected native points attached to their source vertices. This
    # may set needs_solve so constraints consuming projected geometry update in
    # the same depsgraph pass.
    from .utilities.projection_anchor import update_projected_geometry
    update_projected_geometry(bpy.context, depsgraph)

    if not global_data.stateful_op_running:
        from .utilities.validate import validate_all_sketches
        if validate_all_sketches(scene):
            global_data.needs_solve = True

        from .utilities.workplane import repair_origin_workplanes
        repair_origin_workplanes(bpy.context)

    if depsgraph.id_type_updated("SCENE"):
        global_data.needs_solve = True

    if global_data.needs_solve:
        if global_data.stateful_op_running:
            return

        global_data.needs_solve = False
        from .curve_solver import solve_system
        from .model.sketch_ref import get_active_sketch
        from .utilities.curve_data import refresh_curve_geometry

        context = bpy.context
        sketch = get_active_sketch(context)
        if solve_system(context, sketch=sketch) and sketch:
            refresh_curve_geometry(sketch)

    if global_data.needs_redraw:
        global_data.needs_redraw = False
        context = bpy.context
        if context.space_data and context.space_data.type == "VIEW_3D":
            context.space_data.show_gizmo = True


def on_frame_change(scene, depsgraph=None):
    """Re-solve animated dimensions and live mesh projections on frame changes."""
    from . import global_data
    if global_data.stateful_op_running:
        return

    from .curve_solver import solve_system
    from .utilities.curve_data import refresh_curve_geometry
    from .model.sketch_ref import get_sketches
    from .utilities.projection_anchor import refresh_projection_for_sketch

    context = bpy.context
    depsgraph = depsgraph or context.evaluated_depsgraph_get()
    for sketch in get_sketches(scene):
        refresh_projection_for_sketch(sketch, depsgraph, force=True)
        if solve_system(context, sketch=sketch):
            refresh_curve_geometry(sketch)


def on_undo_redo(scene, *args):
    """Reconcile sketch mode with the active sketch after undo/redo."""
    from .model.sketch_ref import get_active_sketch
    from .workspacetools.manager import sync_sketch_mode

    sync_sketch_mode(get_active_sketch(bpy.context) is not None)


def _setup_builtin_handlers():
    from .versioning import do_versioning, write_addon_version

    add_builtin_handler("version_update", do_versioning)
    add_builtin_handler("save_pre", write_addon_version)
    add_builtin_handler("load_post", on_load_post)
    add_builtin_handler("depsgraph_update_post", on_depsgraph_update)
    add_builtin_handler("frame_change_post", on_frame_change)
    add_builtin_handler("undo_post", on_undo_redo)
    add_builtin_handler("redo_post", on_undo_redo)


def register():
    _setup_builtin_handlers()
    register_handlers()


def unregister():
    unregister_handlers()
