import logging
import json
import math

import bpy
from bpy.types import Context, Operator

from .. import global_data
from ..declarations import GizmoGroups, WorkSpaceTools
from ..converters import update_convertor_geometry
from ..utilities.preferences import get_prefs
from ..utilities.data_handling import entities_3d
from ..model.types import SlvsPoint2D, SlvsLine2D, SlvsCircle, SlvsArc

logger = logging.getLogger(__name__)


def update_linked_workplane_bounds(context, sketch):
    """Resize sketch workplane display to fit geometry when leaving sketch.

    If entities are selected in this sketch, use those; otherwise use all sketch
    entities. Computes bounding extents and applies them to workplane display.
    """
    wp = sketch.wp
    print(
        "[CAD_Sketcher] wp_resize: start "
        f"sketch='{getattr(sketch, 'name', '?')}' "
        f"index={getattr(sketch, 'slvs_index', -1)} "
        f"wp_index={getattr(wp, 'slvs_index', -1)} "
        f"source_line_i={getattr(sketch, 'source_line_i', -1)} "
        f"current_width={getattr(wp, 'linked_wp_width', 0.0):.6f} "
        f"current_height={getattr(wp, 'linked_wp_height', 0.0):.6f}"
    )

    sse = context.scene.sketcher.entities
    selected = []
    for entity_index in global_data.selected:
        if entity_index is None:
            continue
        entity = sse.get(entity_index)
        if entity is None or not hasattr(entity, "sketch"):
            continue
        if entity.sketch == sketch:
            selected.append(entity)

    entities = selected if selected else list(sketch.sketch_entities(context))
    print(
        "[CAD_Sketcher] wp_resize: entities "
        f"selected_in_sketch={len(selected)} "
        f"used={'selected' if selected else 'all'} "
        f"count={len(entities)}"
    )
    if not entities:
        print("[CAD_Sketcher] wp_resize: skip, no entities available")
        return

    points_uv = []

    def _add_uv(co):
        points_uv.append((float(co[0]), float(co[1])))

    for entity in entities:
        if isinstance(entity, SlvsPoint2D):
            _add_uv(entity.co)
            continue

        if isinstance(entity, SlvsLine2D):
            _add_uv(entity.p1.co)
            _add_uv(entity.p2.co)
            continue

        if isinstance(entity, SlvsCircle):
            ct = entity.ct.co
            r = float(entity.radius)
            _add_uv((ct.x - r, ct.y))
            _add_uv((ct.x + r, ct.y))
            _add_uv((ct.x, ct.y - r))
            _add_uv((ct.x, ct.y + r))
            continue

        if isinstance(entity, SlvsArc):
            _add_uv(entity.start.co)
            _add_uv(entity.end.co)

            start_angle = float(entity.start_angle)
            sweep = float(entity.angle)
            for candidate in (0.0, 0.5 * math.pi, math.pi, 1.5 * math.pi):
                relative = (candidate - start_angle) % (2.0 * math.pi)
                if relative <= sweep + 1e-7:
                    _add_uv(entity.point_on_curve(candidate, relative=False))

    if not points_uv:
        print(
            "[CAD_Sketcher] wp_resize: skip, no supported geometry points "
            "collected from entities"
        )
        return

    xs = [p[0] for p in points_uv]
    ys = [p[1] for p in points_uv]

    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)

    is_linked = getattr(sketch, "source_line_i", -1) != -1
    if is_linked:
        # Linked sketches are rendered origin-anchored in local X and signed in Y.
        width = max(0.0, max_x)
        height = max_y if abs(max_y) >= abs(min_y) else min_y
        center_x = 0.0
        center_y = 0.0
    else:
        # Regular sketches use a tight local bounding box around sketch geometry.
        width = max_x - min_x
        height = max_y - min_y
        center_x = (min_x + max_x) * 0.5
        center_y = (min_y + max_y) * 0.5

    print(
        "[CAD_Sketcher] wp_resize: bounds "
        f"mode={'linked' if is_linked else 'bbox'} "
        f"min_x={min_x:.6f} max_x={max_x:.6f} "
        f"min_y={min_y:.6f} max_y={max_y:.6f} "
        f"target_width={width:.6f} target_height={height:.6f} "
        f"target_center=({center_x:.6f}, {center_y:.6f})"
    )

    if width > 0.0:
        wp.linked_wp_width = width
    if height != 0.0:
        wp.linked_wp_height = height
    wp.linked_wp_center_x = center_x
    wp.linked_wp_center_y = center_y
    wp.is_dirty = True
    print(
        "[CAD_Sketcher] wp_resize: applied "
        f"new_width={wp.linked_wp_width:.6f} "
        f"new_height={wp.linked_wp_height:.6f} "
        f"new_center=({wp.linked_wp_center_x:.6f}, {wp.linked_wp_center_y:.6f})"
    )


def select_invert(context: Context):
    sketch = context.scene.sketcher.active_sketch
    if sketch:
        logger.debug(
            f"Inverting selection of sketcher entities in sketch : {sketch.name} (slvs_index: {sketch.slvs_index})"
        )
        generator = sketch.sketch_entities(context)
    else:
        logger.debug(f"Inverting selection of sketcher entities")
        generator = entities_3d(context)

    for e in generator:
        e.selected = not e.selected


def select_extend(context: Context):
    sketch = context.scene.sketcher.active_sketch
    if sketch:
        logger.debug(
            f"Extending chain selection of sketcher entities in sketch : {sketch.name} (slvs_index: {sketch.slvs_index})"
        )
        generator = sketch.sketch_entities(context)
    else:
        logger.debug(f"Extending chain selection of sketcher entities")
        generator = entities_3d(context)

    to_select = []
    for e in generator:
        if not e.is_point():
            if e.selected:
                to_select.extend(e.connection_points())
            elif any(p.selected for p in e.connection_points()):
                to_select.append(e)

    for coincident in context.scene.sketcher.constraints.coincident:
        if any(entity.selected for entity in coincident.entities()):
            to_select.extend(coincident.entities())

    is_something_to_select = not all(e.selected for e in to_select)
    for entity in to_select:
        entity.selected = True

    return is_something_to_select


# NOTE: The draw handler has to be registered before this has any effect, currently it's possible that
# entities are first created with an entity that was hovered in the previous state
# Not sure if it's possible to force draw handlers...
# Also note that a running modal operator might prevent redraws, avoid returning running_modal
def ignore_hover(entity):
    ignore_list = global_data.ignore_list
    index = entity if isinstance(entity, int) else entity.slvs_index
    ignore_list.append(index)


# TODO: could probably check entity type only through index, instead of getting the entity first...
def get_hovered(context: Context, *types):
    hovered = global_data.hover
    entity = None

    if hovered != -1:
        entity = context.scene.sketcher.entities.get(hovered)
        if type(entity) in types:
            return entity
    return None


SMOOTHVIEW_FACTOR = 0


def align_view(rv3d, mat_start, mat_end):

    global SMOOTHVIEW_FACTOR
    SMOOTHVIEW_FACTOR = 0
    time_step = 0.01
    increment = 0.01

    def move_view():
        global SMOOTHVIEW_FACTOR
        SMOOTHVIEW_FACTOR += increment
        mat = mat_start.lerp(mat_end, SMOOTHVIEW_FACTOR)
        rv3d.view_matrix = mat

        if SMOOTHVIEW_FACTOR < 1:
            return time_step

    bpy.app.timers.register(move_view)

    # rv3d.view_distance = 6


def switch_sketch_mode(self, context: Context, to_sketch_mode: bool):
    if to_sketch_mode:
        tool = context.workspace.tools.from_space_view3d_mode(context.mode)
        if tool.widget != GizmoGroups.Preselection:
            bpy.ops.wm.tool_set_by_id(name=WorkSpaceTools.Select)
        return True

    bpy.ops.wm.tool_set_by_index(index=0, expand=False)
    return True


def _toggle_local_view(context: Context, enter: bool):
    """Hide/show all scene objects and other sketches when entering/leaving a sketch.

    localview() requires selected objects and returns CANCELLED when nothing is
    selected, so we manually toggle view-layer visibility instead and persist
    the pre-sketch state in scene custom properties.
    """
    _OBJ_PROP = "slvs_pre_sketch_hidden"
    _SK_PROP = "slvs_pre_sketch_visible"
    _WP_PROP = "slvs_pre_sketch_wp_visible"

    if enter:
        active_index = context.scene.sketcher.active_sketch_i

        # Only save the pre-sketch state the very first time sketch mode is
        # entered.  When switching directly from one sketch to another (e.g.
        # add_linked_sketch activates the new sketch while still inside the
        # source sketch) the previously saved state must NOT be overwritten —
        # it represents the true "outside sketch" visibility that must be
        # restored when the user eventually leaves sketch mode.
        already_saved = _OBJ_PROP in context.scene

        if not already_saved:
            # --- Blender objects ---
            obj_state = {obj.name: obj.hide_get() for obj in context.view_layer.objects}
            context.scene[_OBJ_PROP] = json.dumps(obj_state)
            print(f"[CAD_Sketcher] isolate: saving {len(obj_state)} object(s)")

            # --- Other sketches ---
            sketches = context.scene.sketcher.entities.sketches
            sk_state = {str(i): s.visible for i, s in enumerate(sketches)}
            context.scene[_SK_PROP] = json.dumps(sk_state)
            print(
                f"[CAD_Sketcher] isolate: saving sketch visibility (total={len(sk_state)})"
            )

            # --- Global 3D entities (workplanes, points3D, lines3D, normals3D) ---
            ents = context.scene.sketcher.entities
            _global_cols = (
                ents.points3D,
                ents.lines3D,
                ents.normals3D,
                ents.workplanes,
            )
            wp_state = {}
            for col in _global_cols:
                for ent in col:
                    wp_state[str(ent.slvs_index)] = ent.visible
            context.scene[_WP_PROP] = json.dumps(wp_state)
            print(f"[CAD_Sketcher] isolate: saving {len(wp_state)} 3D entity/entities")

        # Always hide everything except the newly active sketch.
        print(
            f"[CAD_Sketcher] isolate: hiding non-active entities (already_saved={already_saved})"
        )
        for obj in context.view_layer.objects:
            obj.hide_set(True)

        sketches = context.scene.sketcher.entities.sketches
        for sketch in sketches:
            if sketch.slvs_index != active_index:
                sketch.visible = False

        ents = context.scene.sketcher.entities
        _global_cols = (ents.points3D, ents.lines3D, ents.normals3D, ents.workplanes)
        for col in _global_cols:
            for ent in col:
                ent.visible = False

    else:
        # --- Restore Blender objects ---
        obj_state_str = context.scene.get(_OBJ_PROP)
        if obj_state_str is not None:
            try:
                obj_state = json.loads(obj_state_str)
                print(
                    f"[CAD_Sketcher] de-isolate: restoring {len(obj_state)} object(s)"
                )
                for obj in context.view_layer.objects:
                    obj.hide_set(obj_state.get(obj.name, False))
            except (json.JSONDecodeError, TypeError):
                print("[CAD_Sketcher] de-isolate: failed to parse object state")
            del context.scene[_OBJ_PROP]
        else:
            print("[CAD_Sketcher] de-isolate: no saved object state found")

        # --- Restore other sketches ---
        sk_state_str = context.scene.get(_SK_PROP)
        if sk_state_str is not None:
            try:
                sk_state = json.loads(sk_state_str)
                sketches = context.scene.sketcher.entities.sketches
                print(
                    f"[CAD_Sketcher] de-isolate: restoring {len(sk_state)} sketch(es)"
                )
                for i, sketch in enumerate(sketches):
                    sketch.visible = sk_state.get(str(i), sketch.visible)
            except (json.JSONDecodeError, TypeError):
                print("[CAD_Sketcher] de-isolate: failed to parse sketch state")
            del context.scene[_SK_PROP]
        else:
            print("[CAD_Sketcher] de-isolate: no saved sketch state found")

        # --- Restore global 3D entities ---
        wp_state_str = context.scene.get(_WP_PROP)
        if wp_state_str is not None:
            try:
                wp_state = json.loads(wp_state_str)
                ents = context.scene.sketcher.entities
                _global_cols = (
                    ents.points3D,
                    ents.lines3D,
                    ents.normals3D,
                    ents.workplanes,
                )
                for col in _global_cols:
                    for ent in col:
                        ent.visible = wp_state.get(str(ent.slvs_index), ent.visible)
            except (json.JSONDecodeError, TypeError):
                print("[CAD_Sketcher] de-isolate: failed to parse 3D entity state")
            del context.scene[_WP_PROP]


def activate_sketch(context: Context, index: int, operator: Operator):
    space_data = context.space_data

    props = context.scene.sketcher
    if index == props.active_sketch_i:
        return {"CANCELLED"}

    sketch_mode = index != -1
    sk = context.scene.sketcher.entities.get(index)
    print(
        f"[CAD_Sketcher] activate_sketch: index={index}  sketch_mode={sketch_mode}"
        f"  area={context.area}  area.type={getattr(context.area, 'type', 'N/A')}  mode={context.mode}"
    )
    switch_sketch_mode(self=operator, context=context, to_sketch_mode=sketch_mode)
    # Align view
    if get_prefs().use_align_view:
        bpy.ops.view3d.slvs_align_view(sketch_index=index)

    # Hide objects
    fade_objects = get_prefs().auto_hide_objects
    if fade_objects:
        space_data.shading.show_xray = sketch_mode

    # Local view: isolate sketch by hiding all Blender objects when entering,
    # restore when leaving (numpad / equivalent).
    # CAD Sketcher entities are GPU-drawn so they remain visible in local view.
    # active_sketch_i must be updated BEFORE _toggle_local_view so that the
    # hide loop uses the correct (new) active index, not the previous one.
    last_sketch = context.scene.sketcher.active_sketch
    logger.debug("Activate: {}".format(sk))
    props.active_sketch_i = index
    _toggle_local_view(context, enter=sketch_mode)

    # Reset reference toggles so they start unchecked for every new sketch session.
    if sketch_mode:
        props.sketch_show_objects = False
        props.sketch_show_sketches = False
        props.sketch_show_workplanes = False

    context.area.tag_redraw()

    if index != -1:
        # Re-sync intermediate linked points if activating a linked sketch,
        # so that any points added to or moved on the source line since the
        # last activation are reflected inside the sketch.
        if sk is not None and getattr(sk, "source_line_i", -1) != -1:
            from ..handlers import sync_linked_intermediate_points

            sync_linked_intermediate_points(context.scene, sk)
        return {"FINISHED"}

    if context.mode != "OBJECT":
        return {"FINISHED"}

    if last_sketch:
        print(
            "[CAD_Sketcher] activate_sketch: leave sketch "
            f"name='{getattr(last_sketch, 'name', '?')}' "
            f"index={getattr(last_sketch, 'slvs_index', -1)} "
            f"wp_width={getattr(last_sketch.wp, 'linked_wp_width', 0.0):.6f} "
            f"wp_height={getattr(last_sketch.wp, 'linked_wp_height', 0.0):.6f}"
        )
        update_linked_workplane_bounds(context, last_sketch)
        print(
            "[CAD_Sketcher] activate_sketch: after resize "
            f"wp_width={getattr(last_sketch.wp, 'linked_wp_width', 0.0):.6f} "
            f"wp_height={getattr(last_sketch.wp, 'linked_wp_height', 0.0):.6f}"
        )

    update_convertor_geometry(context.scene, sketch=last_sketch)

    select_target_ob(context, last_sketch)

    return {"FINISHED"}


def select_target_ob(context, sketch):
    mode = sketch.convert_type
    target_ob = sketch.target_object if mode == "MESH" else sketch.target_curve_object

    bpy.ops.object.select_all(action="DESELECT")
    if not target_ob:
        return

    if target_ob.name in context.view_layer.objects:
        target_ob.select_set(True)
        context.view_layer.objects.active = target_ob
