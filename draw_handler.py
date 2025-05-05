import logging

import bpy
import gpu
from bpy.types import Context, Operator
from bpy.utils import register_class, unregister_class

from .utilities.preferences import use_experimental
from .utilities.constants import CLEAR_COLOR
from .declarations import Operators
from .model.types import SlvsWorkplane
from .shaders import Shaders
from .model.normal_2d import SlvsNormal2D
from .model.normal_3d import SlvsNormal3D
from .model.sketch import SlvsSketch
from .model.categories import POINT, LINE, CURVE
from . import global_data  # Keep the general import for modifying global variables

logger = logging.getLogger(__name__)


def draw_selection_buffer(context: Context):
    """Draw elements offscreen using a four-pass approach."""
    if global_data.offscreen is None:
        logger.error("draw_selection_buffer: No offscreen buffer found!")
        return

    logger.debug("--- Drawing Selection Buffer START ---")
    
    # Set the restricted context flag - we're in a drawing context
    global_data.set_restricted_context(True)
    
    try:
        # Ensure origin elements exist and are properly registered
        logger.debug("Making sure origin elements are created before drawing")
        context.scene.sketcher.entities.ensure_origin_elements(context)
        
        # Store original show_origin value but don't try to modify it
        original_show_origin = context.scene.sketcher.show_origin
        
        with global_data.offscreen.bind():
            # Clear the buffer
            gpu.state.depth_mask_set(True)
            fb = gpu.state.active_framebuffer_get()
            fb.clear(color=CLEAR_COLOR, depth=1.0)
            logger.debug("Buffer cleared.")

            # Debug context state
            logger.debug(f"Active sketch: {context.scene.sketcher.active_sketch}")
            
            # Get all entities
            entities = list(context.scene.sketcher.entities.all)
            logger.debug(f"Raw entity count: {len(entities)}")
            
            # If there are no entities, don't continue
            if not entities:
                logger.debug("No entities to draw in selection buffer")
                # Restore default state
                gpu.state.depth_test_set('NONE')
                gpu.state.depth_mask_set(False)
                
                logger.debug("--- Drawing Selection Buffer END (no entities) ---")
                return
                
            # Group entities by drawing requirements
            standard_draw_entities = []   # Entities using standard draw_id(context, shader)
            context_only_entities = []    # Entities with draw_id(context) signature
            workplanes = []               # Workplanes (need special face/edge drawing)
            
            for e in entities:
                if e.slvs_index in global_data.ignore_list:
                    continue
                    
                # Categorize based on entity type and draw_id signature requirements
                if isinstance(e, SlvsWorkplane):
                    workplanes.append(e)
                elif isinstance(e, (SlvsNormal2D, SlvsNormal3D, SlvsSketch)):
                    context_only_entities.append(e)
                else:
                    standard_draw_entities.append(e)
            
            logger.debug(f"Entities grouped: {len(standard_draw_entities)} standard, " +
                        f"{len(workplanes)} workplanes, {len(context_only_entities)} context-only")
            
            # Sort entities by drawing category using category constants
            points = [e for e in standard_draw_entities if type(e) in POINT]
            lines = [e for e in standard_draw_entities if type(e) in LINE]
            curves = [e for e in standard_draw_entities if type(e) in CURVE]
            
            logger.debug(f"Standard entities: {len(points)} points, {len(lines)} lines, {len(curves)} curves")
            
            # Skip drawing passes if no entities of that type
            # Pass 1: Draw Workplane Faces with standard depth testing
            if workplanes:
                gpu.state.depth_test_set('LESS')
                line_shader = Shaders.id_line_3d()
                line_shader.bind()
                logger.debug("Pass 1: Workplane Faces (LESS depth)")
                drawn_count = 0
                
                for wp in reversed(workplanes):
                    # Update the workplane to ensure it has batches
                    batch = global_data.get_batch(wp)
                    if not batch and hasattr(wp, "update"):
                        logger.debug(f"  Generating batch for workplane {wp.slvs_index}")
                        wp.update()
                        
                    # Draw workplane face
                    if hasattr(wp, "draw_id_face"):
                        logger.debug(f"  Drawing face for WP {wp.slvs_index}")
                        wp.draw_id_face(context, line_shader)
                        drawn_count += 1
                        
                logger.debug(f"  Drawn {drawn_count} faces.")
                gpu.shader.unbind()

            # Pass 2: Draw point entities with standard depth testing
            if points:
                point_shader = Shaders.id_shader_3d()
                point_shader.bind()
                logger.debug("Pass 2: Point Entities (LESS depth)")
                drawn_count = 0
                
                for e in reversed(points):
                    # Update the entity to ensure it has batches - use the safe batch access
                    batch = global_data.get_batch(e)
                    if not batch and hasattr(e, "update"):
                        logger.debug(f"  Generating batch for point {e.slvs_index}")
                        e.update()
                        
                    # Draw point entity with shader
                    logger.debug(f"  Drawing point {e.slvs_index} of type {type(e).__name__}")
                    e.draw_id(context, point_shader)
                    drawn_count += 1
                    
                logger.debug(f"  Drawn {drawn_count} points.")
                gpu.shader.unbind()
            
            # Pass 3: Draw line entities with standard depth testing
            if lines:
                line_shader = Shaders.id_line_3d()
                line_shader.bind()
                logger.debug("Pass 3: Line Entities (LESS depth)")
                drawn_count = 0
                
                for e in reversed(lines):
                    # Update the entity to ensure it has batches - use the safe batch access
                    batch = global_data.get_batch(e)
                    if not batch and hasattr(e, "update"):
                        logger.debug(f"  Generating batch for line {e.slvs_index}")
                        e.update()
                    
                    # Draw line entity with shader
                    logger.debug(f"  Drawing line {e.slvs_index} of type {type(e).__name__}")
                    e.draw_id(context, line_shader)
                    drawn_count += 1
                    
                logger.debug(f"  Drawn {drawn_count} lines.")
                gpu.shader.unbind()

            # Pass 3b: Draw curve entities with standard depth testing
            if curves:
                line_shader = Shaders.id_line_3d()
                line_shader.bind()
                logger.debug("Pass 3b: Curve Entities (LESS depth)")
                drawn_count = 0
                
                for e in reversed(curves):
                    # Update the entity to ensure it has batches - use the safe batch access
                    batch = global_data.get_batch(e)
                    if not batch and hasattr(e, "update"):
                        logger.debug(f"  Generating batch for curve {e.slvs_index}")
                        e.update()
                    
                    # Draw curve entity with shader
                    logger.debug(f"  Drawing curve {e.slvs_index} of type {type(e).__name__}")
                    e.draw_id(context, line_shader)
                    drawn_count += 1
                    
                logger.debug(f"  Drawn {drawn_count} curves.")
                gpu.shader.unbind()
            
            # Pass 4: Draw entities with context-only draw_id method
            if context_only_entities:
                logger.debug("Pass 4: Context-only entities")
                drawn_count = 0
                
                for e in context_only_entities:
                    # Update if possible - use the safe property access system
                    if hasattr(e, "update") and callable(e.update):
                        e.update()
                        
                    logger.debug(f"  Drawing context-only entity {e.slvs_index} of type {type(e).__name__}")
                    # These have draw_id(context) signature
                    e.draw_id(context)
                    drawn_count += 1
                    
                logger.debug(f"  Drawn {drawn_count} context-only entities.")
            
            # Pass 5: Draw ONLY workplane EDGES with depth testing disabled ('ALWAYS')
            if workplanes:
                gpu.state.depth_test_set('ALWAYS')
                line_shader = Shaders.id_line_3d()
                line_shader.bind()
                logger.debug("Pass 5: Workplane Edges (ALWAYS depth)")
                drawn_count = 0
                
                for wp in reversed(workplanes):
                    # Draw workplane edges
                    if hasattr(wp, "draw_id_edges"):
                        logger.debug(f"  Drawing edges for WP {wp.slvs_index}")
                        wp.draw_id_edges(context, line_shader)
                        drawn_count += 1
                        
                logger.debug(f"  Drawn {drawn_count} edges.")
                gpu.shader.unbind()
            
            # Restore default state
            gpu.state.depth_test_set('NONE')
            gpu.state.depth_mask_set(False)
            logger.debug("OpenGL state restored.")
    finally:
        # Reset the restricted context flag
        global_data.set_restricted_context(False)
    
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
    updated_entities = False

    for e in entities:
        if not hasattr(e, "update"):
            continue
        if not force and not e.is_dirty:
            continue
        e.update()
        updated_entities = True

    # If any entities were updated, we need to redraw the selection buffer
    if updated_entities:
        global_data.redraw_selection_buffer = True
        logger.debug("Entities updated, marked selection buffer for redraw")

    def _get_msg():
        msg = "Update geometry batches:"
        for e in entities:
            if not e.is_dirty:
                continue
            msg += "\n - " + str(e)
        return msg

    #if logger.isEnabledFor(logging.DEBUG):
    #    logger.debug(_get_msg())


def draw_elements(context: Context):
    """Draw all visible entities in the scene, optimized by entity type.
    
    This function categorizes entities by type and uses appropriate shaders
    and drawing settings for each category to minimize state changes.
    """
    # Get all visible entities
    entities = [e for e in context.scene.sketcher.entities.all if hasattr(e, "draw")]
    if not entities:
        return
        
    # Group entities by category for optimized drawing
    points = [e for e in entities if type(e) in POINT and e.is_visible(context)]
    lines = [e for e in entities if type(e) in LINE and e.is_visible(context)]
    curves = [e for e in entities if type(e) in CURVE and e.is_visible(context)]
    
    # Get special entities that need custom drawing
    workplanes = [e for e in entities if isinstance(e, SlvsWorkplane) and e.is_visible(context)]
    other_entities = [e for e in entities if e.is_visible(context) and
                     not type(e) in POINT and 
                     not type(e) in LINE and
                     not type(e) in CURVE and
                     not isinstance(e, SlvsWorkplane)]
    
    # 1. Draw points with point shader
    if points:
        # Set up point drawing once for all points
        point_shader = Shaders.uniform_color_3d()
        point_shader.bind()
        gpu.state.blend_set("ALPHA")
        
        for entity in reversed(points):
            batch = entity._batch
            if not batch:
                continue
                
            # Set entity-specific settings
            gpu.state.point_size_set(entity.point_size)
            point_shader.uniform_float("color", entity.color(context))
            
            # Draw the entity
            batch.draw(point_shader)
            
        # Clean up after all points
        gpu.shader.unbind()
        
    # 2. Draw lines with line shader
    if lines:
        # Set up line drawing once for all lines
        line_shader = Shaders.uniform_color_line_3d()
        line_shader.bind()
        gpu.state.blend_set("ALPHA")
        
        for entity in reversed(lines):
            batch = entity._batch
            if not batch:
                continue
                
            # Set entity-specific settings
            gpu.state.line_width_set(entity.line_width)
            line_shader.uniform_float("color", entity.color(context))
            line_shader.uniform_bool("dashed", (entity.is_dashed(),))
            line_shader.uniform_float("dash_width", 0.05)
            line_shader.uniform_float("dash_factor", 0.3)
            
            # Draw the entity
            batch.draw(line_shader)
            
        # Clean up after all lines
        gpu.shader.unbind()
        
    # 3. Draw curves with line shader
    if curves:
        # Set up curve drawing once for all curves
        curve_shader = Shaders.uniform_color_line_3d()
        curve_shader.bind()
        gpu.state.blend_set("ALPHA")
        
        for entity in reversed(curves):
            batch = entity._batch
            if not batch:
                continue
                
            # Set entity-specific settings
            gpu.state.line_width_set(entity.line_width)
            curve_shader.uniform_float("color", entity.color(context))
            curve_shader.uniform_bool("dashed", (entity.is_dashed(),))
            curve_shader.uniform_float("dash_width", 0.05)
            curve_shader.uniform_float("dash_factor", 0.3)
            
            # Draw the entity
            batch.draw(curve_shader)
            
        # Clean up after all curves
        gpu.shader.unbind()
    
    # 4. Draw workplanes with their custom drawing method
    for entity in reversed(workplanes):
        entity.draw(context)
    
    # 5. Draw remaining entities with their regular drawing method
    for entity in reversed(other_entities):
        entity.draw(context)
        
    # Restore OpenGL defaults
    gpu.state.line_width_set(1)
    gpu.state.point_size_set(1)
    gpu.state.blend_set("NONE")


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
