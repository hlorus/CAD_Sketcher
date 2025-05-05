import logging

import bpy
import gpu
from bpy.types import Context, Operator
from bpy.utils import register_class, unregister_class

from . import global_data
from .utilities.preferences import use_experimental
from .utilities.constants import CLEAR_COLOR
from .declarations import Operators
from .model.types import SlvsWorkplane
from .shaders import Shaders

logger = logging.getLogger(__name__)


def draw_selection_buffer(context: Context):
    """Draw elements offscreen using a four-pass approach."""
    offscreen = global_data.offscreen
    if offscreen is None:
        logger.error("draw_selection_buffer: No offscreen buffer found!")
        return

    logger.debug("--- Drawing Selection Buffer START ---")
    with offscreen.bind():
        # Clear the buffer
        gpu.state.depth_mask_set(True)
        fb = gpu.state.active_framebuffer_get()
        fb.clear(color=CLEAR_COLOR, depth=1.0)
        logger.debug("Buffer cleared.")

        # Group entities by type
        entities = list(context.scene.sketcher.entities.all)
        point_entities = [e for e in entities if e.is_point() and e.slvs_index not in global_data.ignore_list]
        line_entities = [e for e in entities if (not e.is_point() and not isinstance(e, SlvsWorkplane)) 
                         and e.slvs_index not in global_data.ignore_list]
        workplanes = [e for e in entities if isinstance(e, SlvsWorkplane) 
                      and e.slvs_index not in global_data.ignore_list]
        logger.debug(f"Entities grouped: {len(point_entities)} points, {len(line_entities)} lines, {len(workplanes)} workplanes.")

        # Pass 1: Draw Workplane Faces with standard depth testing
        gpu.state.depth_test_set('LESS')
        line_shader = Shaders.id_line_3d()
        line_shader.bind()
        logger.debug("Pass 1: Workplane Faces (LESS depth)")
        drawn_count = 0
        for wp in reversed(workplanes):
            if wp.is_selectable(context) and hasattr(wp, "draw_id_face"):
                logger.debug(f"  Drawing face for WP {wp.slvs_index}")
                wp.draw_id_face(context, line_shader)
                drawn_count += 1
        logger.debug(f"  Drawn {drawn_count} faces.")
        gpu.shader.unbind() # Corrected unbind

        # Pass 2: Draw point entities with standard depth testing
        point_shader = Shaders.id_shader_3d()
        point_shader.bind()
        logger.debug("Pass 2: Point Entities (LESS depth)")
        drawn_count = 0
        for e in reversed(point_entities):
            if e.is_selectable(context):
                logger.debug(f"  Drawing point {e.slvs_index}")
                e.draw_id(context, point_shader)
                drawn_count += 1
        logger.debug(f"  Drawn {drawn_count} points.")
        gpu.shader.unbind() # Corrected unbind
        
        # Pass 3: Draw line entities with standard depth testing
        line_shader = Shaders.id_line_3d()
        line_shader.bind()
        logger.debug("Pass 3: Line Entities (LESS depth)")
        drawn_count = 0
        for e in reversed(line_entities):
            if e.is_selectable(context):
                logger.debug(f"  Drawing line {e.slvs_index}")
                e.draw_id(context, line_shader)
                drawn_count += 1
        logger.debug(f"  Drawn {drawn_count} lines.")
        gpu.shader.unbind() # Corrected unbind
        
        # Pass 4: Draw ONLY workplane EDGES with depth testing disabled ('ALWAYS')
        gpu.state.depth_test_set('ALWAYS')
        line_shader = Shaders.id_line_3d()
        line_shader.bind()
        logger.debug("Pass 4: Workplane Edges (ALWAYS depth)")
        drawn_count = 0
        for wp in reversed(workplanes):
            if wp.is_selectable(context) and hasattr(wp, "draw_id_edges"):
                logger.debug(f"  Drawing edges for WP {wp.slvs_index}")
                wp.draw_id_edges(context, line_shader)
                drawn_count += 1
        logger.debug(f"  Drawn {drawn_count} edges.")
        gpu.shader.unbind() # Corrected unbind
        
        # Restore default state
        gpu.state.depth_test_set('NONE')
        gpu.state.depth_mask_set(False)
        logger.debug("OpenGL state restored.")
    logger.debug("--- Drawing Selection Buffer END ---")


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
    area = context.area
    if not area or area.type != 'VIEW_3D':
        # Not in a 3D View context, cannot draw
        return

    # Ensure offscreen buffer exists and matches area dimensions
    width = area.width
    height = area.height
    if not global_data.offscreen or global_data.offscreen.width != width or global_data.offscreen.height != height:
        try:
            if global_data.offscreen:
                logger.debug(f"Recreating offscreen buffer for new dimensions: {width}x{height}")
                global_data.offscreen.free()
            else:
                logger.debug(f"Creating offscreen buffer: {width}x{height}")
            global_data.offscreen = gpu.types.GPUOffScreen(width, height)
            global_data.redraw_selection_buffer = True # Force redraw after creation
        except Exception as e:
            logger.error(f"Failed to create/recreate offscreen buffer: {e}")
            global_data.offscreen = None # Ensure it's None on failure
            return # Cannot proceed without buffer

    force = use_experimental("force_redraw", True)
    update_elements(context, force=force)
    draw_elements(context)

    # Redraw selection buffer if needed (set by updates or buffer creation)
    if global_data.redraw_selection_buffer:
        ensure_selection_texture(context)


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
    # Clean up offscreen buffer when addon is unregistered
    if global_data.offscreen:
        logger.debug("Freeing offscreen buffer.")
        global_data.offscreen.free()
        global_data.offscreen = None
        
    unregister_class(View3D_OT_slvs_unregister_draw_cb)
    unregister_class(View3D_OT_slvs_register_draw_cb)
