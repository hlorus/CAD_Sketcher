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


def sync_linked_intermediate_points(scene, sketch):
    """On activation of a linked sketch, ensure intermediate linked points
    match the current coincident/midpoint points on the source line.

    - Points that already exist (matched by guid, then by X proximity) are
      moved to their updated X position.
    - New source points that have no counterpart yet are created as fixed
      linked points.
    Orphaned linked points (source point removed) are intentionally left in
    place to avoid breaking user constraints.
    """
    if sketch.source_line_i == -1:
        return

    sse = scene.sketcher.entities
    line = sse.get(sketch.source_line_i)
    if line is None:
        return

    origin_3d = line.p1.location.copy()
    p2_3d = line.p2.location.copy()
    line_vec = p2_3d - origin_3d
    line_length = line_vec.length
    if line_length < 1e-8:
        return
    x_new = line_vec.normalized()

    # Reserve the endpoint indices of the main linked guide line
    ext_line = (
        sse.get(sketch.source_linked_line_i)
        if sketch.source_linked_line_i != -1
        else None
    )
    reserved_indices = set()
    if ext_line is not None:
        reserved_indices.add(ext_line.p1.slvs_index)
        reserved_indices.add(ext_line.p2.slvs_index)

    # Index existing intermediate linked points for position-based matching.
    existing_linked_pts = []
    for e in sse.points2D:
        if not hasattr(e, "sketch") or e.sketch.slvs_index != sketch.slvs_index:
            continue
        if not e.linked:
            continue
        if e.slvs_index in reserved_indices:
            continue
        existing_linked_pts.append(e)

    # Helper: update an existing linked point or create a new one.
    def _upsert(t, src_pt):
        for ep in existing_linked_pts:
            if abs(ep.co[0] - t) < 1e-5:
                ep.co = (t, 0.0)
                existing_linked_pts.remove(ep)
                return
        ext_pt = sse.add_point_2d((t, 0.0), sketch)
        ext_pt.fixed = True
        ext_pt.linked = True
        logger.debug(
            "sync_linked_intermediate_points: added linked point "
            "at X=%.4f from %s into sketch %s",
            t,
            src_pt.name,
            sketch.name,
        )

    # Walk coincident/midpoint constraints on the source line to collect the
    # expected intermediate points and their X positions.
    seen_src_indices = {line.p1.slvs_index, line.p2.slvs_index}
    for constraint_col in (
        scene.sketcher.constraints.coincident,
        scene.sketcher.constraints.midpoint,
    ):
        for c in constraint_col:
            if c.entity2.slvs_index != line.slvs_index:
                continue
            src_pt = c.entity1
            if not src_pt.is_point():
                continue
            if src_pt.slvs_index in seen_src_indices:
                continue
            seen_src_indices.add(src_pt.slvs_index)
            _upsert((src_pt.location - origin_3d).dot(x_new), src_pt)

    # --- Also project both endpoints of any line that is colinear with the
    # source line (parallel + one endpoint on the source line's infinite axis).
    # Example: a line parallel to the source line with one coincident endpoint
    # represents a colinear segment; its free endpoint must also appear as a
    # linked reference point.
    _ANGLE_TOL = 1e-4  # |1 - |cos θ|| threshold for parallel
    _DIST_TOL = 1e-4  # max perpendicular distance from axis (metres)
    source_sketch_i = line.sketch.slvs_index
    for cand in sse.lines2D:
        if not hasattr(cand, "sketch"):
            continue
        if cand.sketch.slvs_index != source_sketch_i:
            continue
        if cand.slvs_index == line.slvs_index:
            continue
        cp1 = cand.p1.location
        cp2 = cand.p2.location
        cdir = cp2 - cp1
        clen = cdir.length
        if clen < 1e-8:
            continue
        cdir_n = cdir / clen
        if abs(cdir_n.dot(x_new)) < 1.0 - _ANGLE_TOL:
            continue

        # At least one endpoint must be on the source line's infinite axis.
        def _perp(pt, _o=origin_3d, _x=x_new):
            v = pt - _o
            return (v - v.dot(_x) * _x).length

        if _perp(cp1) >= _DIST_TOL and _perp(cp2) >= _DIST_TOL:
            continue
        # Colinear line — project both endpoints.
        for src_pt in (cand.p1, cand.p2):
            if src_pt.slvs_index in seen_src_indices:
                continue
            seen_src_indices.add(src_pt.slvs_index)
            _upsert((src_pt.location - origin_3d).dot(x_new), src_pt)


def update_linked_sketches(scene):
    """Keep linked sketch workplanes in sync with their source Line2D.

    Returns True if any dependent sketch was updated (so callers can schedule
    a follow-up solve pass for those sketches).
    """
    from mathutils import Matrix

    sse = scene.sketcher.entities
    changed = False
    for sketch in sse.sketches:
        if sketch.source_line_i == -1:
            continue

        line = sse.get(sketch.source_line_i)
        if line is None:
            continue

        origin_3d = line.p1.location.copy()
        p2_3d = line.p2.location.copy()
        line_vec = p2_3d - origin_3d
        line_length = line_vec.length
        if line_length < 1e-8:
            continue

        x_new = line_vec.normalized()
        y_new = line.sketch.wp.normal.copy()
        z_new = x_new.cross(y_new).normalized()
        y_new = z_new.cross(x_new).normalized()

        # Mirror the z-flip that add_linked_sketch applies when the source
        # sketch is an Elevation (so the resulting Plan faces the right way).
        if getattr(line.sketch, "tag", "") == "Elevation":
            z_new = -z_new
            y_new = z_new.cross(x_new).normalized()

        # Optional linked-sketch orientation flip controlled from linking line
        # context menu. Keep right-handed basis by flipping Y and Z together.
        if getattr(sketch, "linked_y_inverted", False):
            y_new = -y_new
            z_new = -z_new

        mat3 = Matrix((x_new, y_new, z_new)).transposed()
        quat = mat3.to_quaternion()

        # Update workplane origin and orientation
        # (assignments trigger tag_update via their update= callbacks)
        sketch.wp.p1.location = origin_3d
        sketch.wp.nm.orientation = quat
        sketch.wp.is_dirty = True

        # Update linked geometry endpoint along X axis
        if sketch.source_linked_line_i != -1:
            ext_line = sse.get(sketch.source_linked_line_i)
            if ext_line is not None:
                ext_line.p2.co = (line_length, 0.0)

        # Keep the workplane display width in sync with the source line length.
        sketch.wp.linked_wp_width = line_length

        changed = True

    return changed


def on_depsgraph_update(scene, depsgraph):
    from . import global_data

    if not getattr(scene.sketcher, "geometry_solved", True):
        return

    if global_data.needs_solve:
        print("[CAD_Sketcher] on_depsgraph_update: running solve pass")
        global_data.needs_solve = False
        from .solver import solve_system
        from .utilities.reference_geometry import refresh_reference_geometry

        context = bpy.context
        sketch = scene.sketcher.active_sketch
        solve_system(context, sketch=sketch)
        linked_changed = update_linked_sketches(scene)
        refs_changed = refresh_reference_geometry(context, sketch=sketch)
        print(
            "[CAD_Sketcher] solve pass done: "
            f"linked_changed={linked_changed} refs_changed={refs_changed}"
        )
        # If reference geometry positions changed, re-solve so that constrained
        # sketch geometry moves to match the updated reference entity positions.
        if refs_changed or linked_changed:
            print("[CAD_Sketcher] re-solving after reference/linked geometry update")
            solve_system(context, sketch=sketch)

    if global_data.needs_redraw:
        global_data.needs_redraw = False
        context = bpy.context
        if context.space_data and context.space_data.type == "VIEW_3D":
            context.space_data.show_gizmo = True


def on_load_post(_filepath):
    scene_named_default = bpy.data.scenes.get("Scene")
    if scene_named_default and hasattr(scene_named_default, "sketcher"):
        scene_named_default.sketcher.sketch_show_objects = True

    context_scene = getattr(bpy.context, "scene", None)
    if context_scene and hasattr(context_scene, "sketcher"):
        context_scene.sketcher.sketch_show_objects = True


def _setup_builtin_handlers():
    from .versioning import do_versioning, write_addon_version

    add_builtin_handler("version_update", do_versioning)
    add_builtin_handler("save_pre", write_addon_version)
    add_builtin_handler("depsgraph_update_post", on_depsgraph_update)
    add_builtin_handler("load_post", on_load_post)


def register():
    _setup_builtin_handlers()
    register_handlers()


def unregister():
    unregister_handlers()
