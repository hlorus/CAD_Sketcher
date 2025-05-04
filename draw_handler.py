import logging

import bpy
import gpu
from bpy.types import Context, Operator
from bpy.utils import register_class, unregister_class

from . import global_data
from .utilities.preferences import use_experimental
from .declarations import Operators
from .model.types import SlvsWorkplane

logger = logging.getLogger(__name__)


def draw_selection_buffer(context: Context):
    """Draw elements offscreen"""
    region = context.region

    # create offscreen
    width, height = region.width, region.height
    offscreen = global_data.offscreen = gpu.types.GPUOffScreen(width, height)

    with offscreen.bind():
        fb = gpu.state.active_framebuffer_get()
        fb.clear(color=(0.0, 0.0, 0.0, 0.0))
        
        entities = list(context.scene.sketcher.entities.all)
        
        # First pass: Draw all non-workplane entities and workplane FACES with depth testing
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.depth_mask_set(True)
        
        for e in reversed(entities):
            if e.slvs_index in global_data.ignore_list:
                continue
            if not hasattr(e, "draw_id"):
                continue
            if not e.is_selectable(context):
                continue
                
            # For workplanes, only draw faces in this first pass
            if isinstance(e, SlvsWorkplane):
                if hasattr(e, "draw_id_face"):
                    e.draw_id_face(context)
            else:
                # Draw all non-workplane entities normally
                e.draw_id(context)
        
        # Second pass: Draw ALL workplane EDGES with depth testing disabled
        # This ensures edges can always be selected regardless of other geometry
        gpu.state.depth_test_set('ALWAYS')
        
        for e in reversed(entities):
            if e.slvs_index in global_data.ignore_list:
                continue
            if not isinstance(e, SlvsWorkplane):
                continue
            if not hasattr(e, "draw_id_edges"):
                continue
            if not e.is_selectable(context):
                continue
            
            # Draw workplane edges
            e.draw_id_edges(context)
        
        # Restore default state
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
