import logging
import json

import bpy
from bpy.types import Context, Operator

from .. import global_data
from ..declarations import GizmoGroups, WorkSpaceTools
from ..converters import update_convertor_geometry
from ..utilities.preferences import get_prefs
from ..utilities.data_handling import entities_3d
from ..model.types import SlvsPoint2D

logger = logging.getLogger(__name__)


def update_linked_workplane_height(context, sketch):
    """Update the linked workplane display height to match the extreme
    non-linked 2D point in the sketch (positive = upward, negative = downward).
    Called when leaving a linked sketch."""
    wp = sketch.wp
    if wp.linked_wp_width <= 0:
        return

    extreme_y = 0.0
    for e in sketch.sketch_entities(context):
        if not isinstance(e, SlvsPoint2D):
            continue
        _, v = e.co
        if abs(v) > abs(extreme_y):
            extreme_y = v

    if extreme_y != 0.0:
        wp.linked_wp_height = extreme_y
        wp.is_dirty = True


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
        return {"FINISHED"}

    if context.mode != "OBJECT":
        return {"FINISHED"}

    if last_sketch and getattr(last_sketch.wp, "linked_wp_width", 0) > 0:
        update_linked_workplane_height(context, last_sketch)

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
