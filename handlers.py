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
    """Reset transient in-memory state carried over from the previous file.

    Cheap and always safe. Migrating legacy (entity-based) sketches and
    upgrading a baked revolve node group are NOT done here -- they are the
    manual ``slvs_migrate_legacy`` operator, surfaced by the Sketcher panel when
    legacy data is detected, so all users don't pay for it on every file load.
    """
    from .drawing import overlay, selection
    from .utilities.validate import reset_cache

    reset_cache()
    overlay.invalidate()
    selection.clear()


def on_depsgraph_update(scene, depsgraph):
    from . import global_data

    # Keep face-anchored workplanes on their mesh face as geometry changes.
    from .utilities.face_anchor import update_face_workplanes

    update_face_workplanes(bpy.context, depsgraph)

    # Keep projected native points attached to their source mesh vertices.
    from .utilities.projection_anchor import update_projected_geometry

    update_projected_geometry(bpy.context, depsgraph)

    # Repair invariants if a built-in tool edited our curve data outside the
    # addon. Skip while one of our operators is mid-run (it owns the data and
    # keeps invariants itself).
    if not global_data.stateful_op_running:
        from .utilities.validate import validate_all_sketches

        if validate_all_sketches(scene):
            global_data.needs_solve = True

        # Undo/redo can flatten the origin workplane empties to identity (they
        # then stack into a mushy overlap, #571); re-assert their transforms.
        # Only rewrites when drifted, so this settles in one pass.
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
            # The solver writes point positions in place, which does not make
            # the Geometry Nodes modifier re-evaluate; force a topology rebuild
            # so the generated mesh matches the solved geometry (operators that
            # solve do this themselves; this covers the depsgraph-driven path,
            # e.g. editing a dimension value).
            refresh_curve_geometry(sketch)

    if global_data.needs_redraw:
        global_data.needs_redraw = False
        context = bpy.context
        if context.space_data and context.space_data.type == "VIEW_3D":
            context.space_data.show_gizmo = True


def on_frame_change(scene, depsgraph=None):
    """Re-solve on frame changes so animated/driven dimensions update.

    Dimensional values are stored in ``scene["slvs:c:{uid}"]`` custom properties
    specifically so they can be driven/animated (issue #544). A driver writes
    that value during depsgraph evaluation, which does not reliably re-flag the
    scene for ``depsgraph_update_post``; ``frame_change_post`` does fire, so we
    re-solve here. Covers timeline scrubbing and playback. Projected source
    geometry is refreshed first so animated source objects stay attached too.
    """
    from . import global_data

    if global_data.stateful_op_running:
        return

    from .curve_solver import solve_system
    from .model.sketch_ref import get_sketches
    from .utilities.curve_data import refresh_curve_geometry
    from .utilities.projection_anchor import refresh_projection_for_sketch

    context = bpy.context
    depsgraph = depsgraph or context.evaluated_depsgraph_get()
    for sketch in get_sketches(scene):
        refresh_projection_for_sketch(sketch, depsgraph, force=True)
        if solve_system(context, sketch=sketch):
            refresh_curve_geometry(sketch)


def on_undo_redo(scene, *args):
    """Reconcile sketch mode with the active sketch after undo/redo.

    The sketch-mode flag and its registered tool set are Python state that
    Blender's undo cannot revert, while ``active_sketch_object`` is undo-tracked.
    Undoing sketch creation nulls the pointer but leaves sketch mode on -- a dead
    end where you can neither add nor leave a sketch. Re-sync them here.
    """
    from .model.sketch_ref import get_active_sketch
    from .workspacetools.manager import sync_sketch_mode

    sketch = get_active_sketch(bpy.context)
    sync_sketch_mode(
        sketch is not None,
        is_3d=bool(sketch and sketch.is_3d),
    )


def _setup_builtin_handlers():
    from .versioning import write_addon_version

    # NOTE: entity-data versioning (do_versioning) is NOT a handler -- it runs
    # inside the manual slvs_migrate_legacy operator, right before the legacy
    # sketches are converted to curves, so nothing versions data on file load.
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
