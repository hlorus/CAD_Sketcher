import logging

import bpy
from bpy.types import Context, Operator

from .. import global_data
from ..declarations import GizmoGroups, WorkSpaceTools
from ..converters import update_convertor_geometry
from ..utilities.preferences import get_prefs
from ..utilities.data_handling import entities_3d

logger = logging.getLogger(__name__)


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


def activate_sketch(context: Context, index: int, operator: Operator):
    space_data = context.space_data

    props = context.scene.sketcher
    if index == props.active_sketch_i:
        return {"CANCELLED"}

    sketch_mode = index != -1
    sk = context.scene.sketcher.entities.get(index)
    switch_sketch_mode(self=operator, context=context, to_sketch_mode=sketch_mode)

    # Align view
    if get_prefs().use_align_view:
        bpy.ops.view3d.slvs_align_view(sketch_index=index)

    # Hide objects
    fade_objects = get_prefs().auto_hide_objects
    if fade_objects:
        space_data.shading.show_xray = sketch_mode

    last_sketch = context.scene.sketcher.active_sketch
    logger.debug("Activate: {}".format(sk))
    props.active_sketch_i = index
    context.area.tag_redraw()

    if index != -1:
        return {"FINISHED"}

    if context.mode != "OBJECT":
        return {"FINISHED"}

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
