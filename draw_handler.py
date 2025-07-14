import bpy
import gpu
from bpy.types import Context, Operator
from bpy.utils import register_class, unregister_class
from bpy.app.handlers import persistent
from mathutils import Vector

from . import global_data
from .utilities.preferences import use_experimental
from .utilities.constants import RenderingConstants
from .utilities.gpu_manager import GPUResourceManager
from .declarations import Operators


# Performance cache for expensive calculations
class PerformanceCache:
    """Cache expensive calculations to avoid redundant work."""

    def __init__(self):
        self.reset()

    def reset(self):
        """Reset all cached values."""
        self._camera_location = None
        self._camera_view_matrix_hash = None
        self._last_entity_count = 0
        self._last_viewport_size = (0, 0)
        self._entities_dirty = True

    def get_camera_location(self, context):
        """Get cached camera location, recalculating only when view matrix changes."""
        if not hasattr(context, 'region_data') or not context.region_data:
            return Vector((0, 0, 0))

        view_matrix = context.region_data.view_matrix
        # Use matrix hash to detect changes efficiently - revert to original working method
        current_hash = hash(tuple(view_matrix.col[0]) + tuple(view_matrix.col[1]) +
                           tuple(view_matrix.col[2]) + tuple(view_matrix.col[3]))

        if self._camera_view_matrix_hash != current_hash:
            self._camera_location = view_matrix.inverted().translation
            self._camera_view_matrix_hash = current_hash

        return self._camera_location

    def should_redraw_selection_buffer(self, context):
        """Determine if selection buffer needs redrawing based on scene changes."""
        current_entity_count = len(context.scene.sketcher.entities.all)
        current_viewport_size = (context.region.width, context.region.height)

        # Check if view matrix changed (camera moved/rotated/zoomed)
        view_matrix_changed = False
        if hasattr(context, 'region_data') and context.region_data:
            view_matrix = context.region_data.view_matrix
            current_hash = hash(tuple(view_matrix.col[0]) + tuple(view_matrix.col[1]) +
                               tuple(view_matrix.col[2]) + tuple(view_matrix.col[3]))

            # If we haven't stored a hash yet, or if it changed, mark as changed
            if self._camera_view_matrix_hash is None or self._camera_view_matrix_hash != current_hash:
                view_matrix_changed = True
                # Update stored hash for next comparison
                self._camera_view_matrix_hash = current_hash

        # Check if we need to redraw
        needs_redraw = (
            self._entities_dirty or  # Entities were modified/moved
            current_entity_count != self._last_entity_count or  # Entity count changed
            current_viewport_size != self._last_viewport_size or  # Viewport resized
            view_matrix_changed or  # Camera moved/rotated/zoomed
            not global_data.offscreen  # No offscreen buffer exists
        )

        if needs_redraw:
            self._last_entity_count = current_entity_count
            self._last_viewport_size = current_viewport_size
            self._entities_dirty = False

        return needs_redraw

    def mark_entities_dirty(self):
        """Mark entities as dirty to force next selection buffer redraw."""
        self._entities_dirty = True

# Global performance cache instance
_perf_cache = PerformanceCache()

# Frame counter for periodic cleanup
_cleanup_frame_counter = 0


def get_entity_distance_from_camera(entity, context, camera_location=None):
    """Calculate the distance from the entity to the camera for depth sorting."""
    try:
        # Use cached camera location if provided
        if camera_location is None:
            camera_location = _perf_cache.get_camera_location(context)

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

    except (AttributeError, ValueError, TypeError) as e:
        # Log specific errors for debugging while gracefully handling them
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"Distance calculation failed for entity {getattr(entity, '__class__', type(entity)).__name__}: {e}")
        # Return large distance on error so entity is drawn first
        return float('inf')


def draw_selection_buffer(context: Context):
    """Draw elements offscreen with depth-aware sorting and performance optimizations."""
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

        # Cache camera location for all distance calculations
        camera_location = _perf_cache.get_camera_location(context)

        # Custom sorting for better workplane selection:
        # 1. Sort by distance from camera (farthest first)
        # 2. BUT give workplanes selection priority by treating them as closer
        def get_sorting_key(entity):
            distance = get_entity_distance_from_camera(entity, context, camera_location)

            # Give workplanes selection priority by reducing their effective distance
            is_workplane = entity.__class__.__name__ == 'SlvsWorkplane'

            if is_workplane:
                # Reduce workplane distance significantly to give them selection priority
                distance *= RenderingConstants.WORKPLANE_SELECTION_PRIORITY

            return distance

        # Sort entities by modified distance (farthest first, but workplanes get priority)
        entities.sort(key=get_sorting_key, reverse=True)

        # Draw entities in distance-sorted order
        for e in entities:
            e.draw_id(context)

        # Restore default depth state
        gpu.state.depth_test_set('NONE')
        gpu.state.depth_mask_set(False)


def ensure_selection_texture(context: Context):
    """Ensure selection texture is up to date - restored original simple logic."""
    if not global_data.redraw_selection_buffer:
        return

    # Always redraw when flag is set (original behavior)
    # This ensures selection works reliably
    draw_selection_buffer(context)
    global_data.redraw_selection_buffer = False


def update_elements(context: Context, force: bool = False):
    """
    Update entity geometry batches when needed.
    """
    entities = list(context.scene.sketcher.entities.all)
    entities_updated = False

    for e in entities:
        if not hasattr(e, "update"):
            continue
        if not force and not e.is_dirty:
            continue
        e.update()
        entities_updated = True

    # Mark selection buffer as needing redraw if entities were updated
    if entities_updated:
        _perf_cache.mark_entities_dirty()


def draw_elements(context: Context):
    for entity in reversed(list(context.scene.sketcher.entities.all)):
        if hasattr(entity, "draw"):
            entity.draw(context)


def draw_cb():
    context = bpy.context

    # Ensure performance cache is initialized for loaded files
    global _perf_cache
    if not hasattr(_perf_cache, '_initialized_for_scene'):
        _perf_cache.reset()
        _perf_cache.mark_entities_dirty()
        _perf_cache._initialized_for_scene = True

    force = use_experimental("force_redraw", True)
    update_elements(context, force=force)
    draw_elements(context)

    # Restore original behavior: mark for redraw every frame
    # This ensures selection works correctly
    global_data.redraw_selection_buffer = True

    # Periodic cleanup of GPU resources (time-based instead of frame-based)
    cleanup_stats = GPUResourceManager.periodic_cleanup(context)

    # Keep the old frame-based cleanup as a backup for very long sessions
    global _cleanup_frame_counter
    _cleanup_frame_counter += 1
    if _cleanup_frame_counter >= (RenderingConstants.CLEANUP_FRAME_INTERVAL * 10):  # Much less frequent
        # Force cleanup every 10,000 frames as a safety net
        GPUResourceManager.force_cleanup_all(context)
        _cleanup_frame_counter = 0


def reset_performance_cache():
    """Reset performance cache - call when scene changes significantly."""
    global _perf_cache
    _perf_cache.reset()


def force_selection_buffer_refresh(context):
    """Force an immediate selection buffer refresh - useful for debugging selection issues."""
    global _perf_cache
    _perf_cache.mark_entities_dirty()
    draw_selection_buffer(context)


def get_cache_status():
    """Get current cache status for debugging."""
    global _perf_cache
    return {
        "entities_dirty": _perf_cache._entities_dirty,
        "last_entity_count": _perf_cache._last_entity_count,
        "last_viewport_size": _perf_cache._last_viewport_size,
        "has_camera_location": _perf_cache._camera_location is not None,
        "has_offscreen_buffer": global_data.offscreen is not None
    }


@persistent
def load_handler_reset_cache(dummy):
    """Reset performance cache when file is loaded to ensure selection works with existing entities."""
    global _perf_cache
    _perf_cache.reset()
    _perf_cache.mark_entities_dirty()
    # Clear scene initialization flag so it gets properly set up
    if hasattr(_perf_cache, '_initialized_for_scene'):
        delattr(_perf_cache, '_initialized_for_scene')
    # Force selection buffer redraw
    global_data.redraw_selection_buffer = True

    # Clean up GPU resources on file load to prevent accumulation
    try:
        import bpy
        # Use a dummy context for cleanup - should be safe during file load
        context = bpy.context
        GPUResourceManager.force_cleanup_all(context)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"GPU cleanup on file load failed: {e}")

    # Ensure Select tool is active to enable click selection - use timer for deferred activation
    def activate_select_tool():
        """Deferred function to activate select tool after file load completes."""
        from .declarations import WorkSpaceTools
        try:
            # Check if we're in the right context (3D viewport)
            for area in bpy.context.screen.areas:
                if area.type == 'VIEW_3D':
                    # Activate the CAD Sketcher Select tool so click selection works
                    bpy.ops.wm.tool_set_by_id(name=WorkSpaceTools.Select)
                    break
        except Exception as e:
            # Log but don't fail if tool activation fails
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"Could not activate Select tool on file load: {e}")
        return None  # Don't repeat the timer

    # Schedule tool activation for next frame to ensure everything is loaded
    bpy.app.timers.register(activate_select_tool, first_interval=0.1)


class View3D_OT_slvs_register_draw_cb(Operator):
    bl_idname = Operators.RegisterDrawCB
    bl_label = "Register Draw Callback"

    def execute(self, context: Context):
        global_data.draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            draw_cb, (), "WINDOW", "POST_VIEW"
        )
        # Reset cache when registering new draw callback
        reset_performance_cache()
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
    # Register file load handler to reset cache when files are loaded
    if load_handler_reset_cache not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(load_handler_reset_cache)


def unregister():
    unregister_class(View3D_OT_slvs_unregister_draw_cb)
    unregister_class(View3D_OT_slvs_register_draw_cb)
    # Unregister file load handler
    if load_handler_reset_cache in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(load_handler_reset_cache)
