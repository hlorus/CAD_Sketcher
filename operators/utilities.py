import logging
from typing import Generator

import bpy
from bpy.types import Context, Operator
from mathutils import Matrix

from .. import global_data
from ..declarations import GizmoGroups, WorkSpaceTools
from ..class_defines import SlvsGenericEntity, point
from ..convertors import update_convertor_geometry
from ..utilities.preferences import use_experimental, get_prefs

logger = logging.getLogger(__name__)

def entities_3d(context: Context) -> Generator[SlvsGenericEntity, None, None]:
    for entity in context.scene.sketcher.entities.all:
        if hasattr(entity, "sketch"):
            continue
        yield entity

def select_all(context: Context):
    sketch = context.scene.sketcher.active_sketch
    if sketch:
        logger.debug(f"Selecting all sketcher entities in sketch : {sketch.name} (slvs_index: {sketch.slvs_index})")
        generator = sketch.sketch_entities(context)
    else:
        logger.debug(f"Selecting all sketcher entities")
        generator = entities_3d(context)

    for e in generator:
        if e.selected:
            continue
        if not e.is_visible(context):
            continue
        if not e.is_active(context.scene.sketcher.active_sketch):
            continue
        e.selected = True

def deselect_all(context: Context):
    logger.debug("Deselecting all sketcher entities")
    global_data.selected.clear()

def select_invert(context: Context):
    sketch = context.scene.sketcher.active_sketch
    if sketch:
        logger.debug(f"Inverting selection of sketcher entities in sketch : {sketch.name} (slvs_index: {sketch.slvs_index})")
        generator = sketch.sketch_entities(context)
    else:
        logger.debug(f"Inverting selection of sketcher entities")
        generator = entities_3d(context)
    
    for e in generator:
        e.selected = not e.selected

def select_extend(context: Context):
    sketch = context.scene.sketcher.active_sketch
    if sketch:
        logger.debug(f"Extending chain selection of sketcher entities in sketch : {sketch.name} (slvs_index: {sketch.slvs_index})")
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
    ignore_list.append(entity.slvs_index)

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

    bpy.ops.wm.tool_set_by_index(index=0)
    return True


def activate_sketch(context: Context, index: int, operator: Operator):
    space_data = context.space_data
    rv3d = context.region_data

    props = context.scene.sketcher
    if index == props.active_sketch_i:
        return {"CANCELLED"}

    sketch_mode = (index != -1)
    switch_sketch_mode(self=operator, context=context, to_sketch_mode=sketch_mode)

    sk = None
    do_align_view = use_experimental("use_align_view", False)
    if sketch_mode:
        sk = context.scene.sketcher.entities.get(index)
        if not sk:
            operator.report({"ERROR"}, "Invalid index: {}".format(index))
            return {"CANCELLED"}
        auto_hide_objects = not get_prefs().auto_hide_objects
        space_data.show_object_viewport_curve = auto_hide_objects
        space_data.show_object_viewport_mesh = auto_hide_objects

        #Align view to normal of wp
        if do_align_view:
            matrix_target = sk.wp.matrix_basis.inverted()
            matrix_start = rv3d.view_matrix
            align_view(rv3d, matrix_start, matrix_target)
            rv3d.view_perspective = "ORTHO"

    else:
        #Reset view
        if do_align_view:
            rv3d.view_distance = 18
            matrix_start = rv3d.view_matrix
            matrix_default = Matrix((
                (0.4100283980369568, 0.9119764566421509, -0.013264661654829979, 0.0),
                (-0.4017425775527954, 0.19364342093467712, 0.8950449228286743, 0.0),
                (0.8188283443450928, -0.36166495084762573, 0.44577890634536743, -17.986562728881836),
                (0.0, 0.0, 0.0, 1.0)
            ))
            align_view(rv3d, matrix_start, matrix_default)
            rv3d.view_perspective = "PERSP"
        space_data.show_object_viewport_curve = True
        space_data.show_object_viewport_mesh = True

    last_sketch = context.scene.sketcher.active_sketch
    logger.debug("Activate: {}".format(sk))
    props.active_sketch_i = index
    context.area.tag_redraw()

    if index != -1:
        return {"FINISHED"}

    if context.mode != "OBJECT":
        return {"FINISHED"}

    update_convertor_geometry(context.scene, sketch=last_sketch)
    return {"FINISHED"}
