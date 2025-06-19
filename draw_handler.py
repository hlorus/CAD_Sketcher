import logging

import bpy
import gpu
from bpy.types import Context, Operator
from bpy.utils import register_class, unregister_class
from mathutils import Vector

from . import global_data
from .utilities.preferences import use_experimental
from .declarations import Operators

logger = logging.getLogger(__name__)


def get_entity_distance_from_camera(entity, context):
    """Calculate the distance from the entity to the camera for depth sorting."""
    try:
        # Get camera/view location
        view_matrix = context.region_data.view_matrix
        camera_location = view_matrix.inverted().translation

        # Get entity location (use placement method if available, otherwise try common location attributes)
        if hasattr(entity, 'placement'):
            entity_location = entity.placement()
        elif hasattr(entity, 'location'):
            entity_location = entity.location
        elif hasattr(entity, 'p1') and hasattr(entity.p1, 'location'):
            # For entities like workplanes that have a p1 point
            entity_location = entity.p1.location
        else:
            # Fallback: return a large distance so entity is drawn first (behind others)
            return float('inf')

        # Calculate distance
        if hasattr(entity_location, '__len__') and len(entity_location) >= 3:
            entity_pos = Vector(entity_location[:3])
        else:
            entity_pos = Vector(entity_location)

        return (camera_location - entity_pos).length

    except Exception as e:
        logger.debug(f"Error calculating distance for entity {entity}: {e}")
        # Return large distance on error so entity is drawn first
        return float('inf')


def draw_selection_buffer(context: Context):
    """Draw elements offscreen with depth-aware sorting"""
    region = context.region

    # create offscreen
    width, height = region.width, region.height
    offscreen = global_data.offscreen = gpu.types.GPUOffScreen(width, height)

    with offscreen.bind():
        # Enable depth testing for proper z-buffer behavior
        gpu.state.depth_test_set('LESS')
        gpu.state.depth_mask_set(True)

        fb = gpu.state.active_framebuffer_get()
        fb.clear(color=(0.0, 0.0, 0.0, 0.0), depth=1.0)

        # Get all selectable entities
        entities = []
        for e in context.scene.sketcher.entities.all:
            if e.slvs_index in global_data.ignore_list:
                continue
            if not hasattr(e, "draw_id"):
                continue
            if not e.is_selectable(context):
                continue
            entities.append(e)

        # Sort entities by distance from camera (farthest first)
        # This ensures closer entities are drawn last and have selection priority
        entities.sort(key=lambda e: get_entity_distance_from_camera(e, context), reverse=True)

        # Draw entities in distance-sorted order
        for e in entities:
            e.draw_id(context)

        # Restore default depth state
        gpu.state.depth_test_set('NONE')
        gpu.state.depth_mask_set(False)


def ensure_selection_texture(context: Context):
    if not global_data.redraw_selection_buffer:
        return

    draw_selection_buffer(context)
    global_data.redraw_selection_buffer = False


def update_elements(context: Context, force: bool = False):
    """
    TODO: Avoid to always update batches and selection texture
    """
    entities = list(context.scene.sketcher.entities.all)

    for e in entities:
        if not hasattr(e, "update"):
            continue
        if not force and not e.is_dirty:
            continue
        e.update()

    def _get_msg():
        msg = "Update geometry batches:"
        for e in entities:
            if not e.is_dirty:
                continue
            msg += "\n - " + str(e)
        return msg

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(_get_msg())


def draw_elements(context: Context):
    for entity in reversed(list(context.scene.sketcher.entities.all)):
        if hasattr(entity, "draw"):
            entity.draw(context)


def draw_cb():
    context = bpy.context

    force = use_experimental("force_redraw", True)
    update_elements(context, force=force)
    draw_elements(context)

    global_data.redraw_selection_buffer = True


class View3D_OT_slvs_register_draw_cb(Operator):
    bl_idname = Operators.RegisterDrawCB
    bl_label = "Register Draw Callback"

    def execute(self, context: Context):
        global_data.draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            draw_cb, (), "WINDOW", "POST_VIEW"
        )

        return {"FINISHED"}


class View3D_OT_slvs_unregister_draw_cb(Operator):
    bl_idname = Operators.UnregisterDrawCB
    bl_label = ""

    def execute(self, context: Context):
        global_data.draw_handler.remove_handle()
        return {"FINISHED"}


def register():
    register_class(View3D_OT_slvs_register_draw_cb)
    register_class(View3D_OT_slvs_unregister_draw_cb)


def unregister():
    unregister_class(View3D_OT_slvs_unregister_draw_cb)
    unregister_class(View3D_OT_slvs_register_draw_cb)
