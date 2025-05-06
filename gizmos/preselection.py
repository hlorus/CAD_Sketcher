import gpu
import logging
from bpy.types import Gizmo, GizmoGroup
import math
from mathutils import Vector

from ..declarations import Gizmos, GizmoGroups
from ..draw_handler import ensure_selection_texture
from ..utilities.index import rgb_to_index
from ..model.types import SlvsWorkplane
from .utilities import context_mode_check
from .constants import WORKPLANE_EDGE_SELECT_TOLERANCE, PICK_SIZE
from ..utilities.view import get_pos_2d
from .. import global_data  # Import the whole module

logger = logging.getLogger(__name__)

# TODO: move this module state to global_data 

_last_mouse_pos = None
_edge_selection_active = False  # Track if we're currently in edge selection mode
_selected_edge_workplane = -1   # Store the currently selected edge's workplane index

class VIEW3D_GGT_slvs_preselection(GizmoGroup):
    bl_idname = GizmoGroups.Preselection
    bl_label = "preselection ggt"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"3D"}

    # NOTE: it would be great to expose the hovered entity as a gizmogroup prop
    # rather than using global variables...

    @classmethod
    def poll(cls, context):
        return context_mode_check(context, cls.bl_idname)

    def setup(self, context):
        self.gizmo = self.gizmos.new(VIEW3D_GT_slvs_preselection.bl_idname)


def is_point_on_edge(workplane, point_2d, tolerance=WORKPLANE_EDGE_SELECT_TOLERANCE):
    """Check if a 2D point is close to any edge of the workplane square
    
    Args:
        workplane: The workplane to check edges for
        point_2d: 2D point coordinates on the workplane (x, y)
        tolerance: Distance threshold for edge detection (default from constants)
    
    Returns:
        bool: True if point is within tolerance of an edge
    """
    size = workplane.size
    half_size = size / 2
    
    # Square coordinates (centered at origin)
    left = -half_size
    right = half_size
    top = half_size
    bottom = -half_size
    
    # Point coordinates
    x, y = point_2d
    
    # First check if point is near or inside the square at all
    if x < left - tolerance or x > right + tolerance or y < bottom - tolerance or y > top + tolerance:
        return False
    
    # Check distance to each edge with a generous tolerance
    # When near corners, both edges will activate
    edges = [
        abs(y - top) <= tolerance and left - tolerance <= x <= right + tolerance,    # Top edge
        abs(y - bottom) <= tolerance and left - tolerance <= x <= right + tolerance, # Bottom edge
        abs(x - left) <= tolerance and bottom - tolerance <= y <= top + tolerance,   # Left edge
        abs(x - right) <= tolerance and bottom - tolerance <= y <= top + tolerance,  # Right edge
    ]
    
    return any(edges)


# NOTE: idealy gizmo would expose active element as a property and
# operators would access hovered element from there
class VIEW3D_GT_slvs_preselection(Gizmo):
    bl_idname = Gizmos.Preselection

    __slots__ = ()

    def draw(self, context):
        pass

    def test_select(self, context, location):
        global _edge_selection_active
        
        # reset gizmo highlight
        if global_data.highlight_constraint:
            global_data.highlight_constraint = None
            context.area.tag_redraw()

        if global_data.highlight_entities:
            global_data.highlight_entities.clear()
            context.area.tag_redraw()

        # ensure selection texture is up to date
        ensure_selection_texture(context)

        # sample selection texture and mark hovered entity
        mouse_x, mouse_y = location
        
        # Track current mouse position
        current_pos = (mouse_x, mouse_y)
        _last_mouse_pos = current_pos

        # Reset hover state every time, but be more careful about it
        # Don't clear everything if we're in a sketch - we need to keep track of sketch entities
        global_data.hover_stack.clear()
        global_data.hover_stack_index = -1
        
        # Keep edge selection state for workplanes
        if not _edge_selection_active:
            _selected_edge_workplane = -1

        # Clear hover state by default but don't do a full reset
        # This allows hover state to be properly updated
        global_data.hover = -1

        # Check for entities at current mouse position
        if not global_data.offscreen:
            # No selection buffer available, clear hover state
            global_data.hover = -1
            return -1
        
        # Find entities under cursor
        found_indices = set()  # Use a set to prevent duplicates
        entity_depths = {}  # Dictionary to store entity depths
        active_sketch = context.scene.sketcher.active_sketch
        
        # Get view info for depth calculations
        region = context.region
        rv3d = context.region_data
        view_origin = rv3d.view_matrix.inverted().translation
        
        # Increased from 5 to 8 to make it easier to select vertical lines
        for x, y in get_spiral_coords(mouse_x, mouse_y, context.area.width, context.area.height, PICK_SIZE):
            with global_data.offscreen.bind():
                fb = gpu.state.active_framebuffer_get()
                buffer = fb.read_color(x, y, 1, 1, 4, 0, "FLOAT")
            r, g, b, alpha = buffer[0][0]

            if alpha > 0:
                index = rgb_to_index(r, g, b)
                if index not in found_indices and index not in global_data.ignore_list:
                    found_indices.add(index)
                    
                    # Verify this is a valid entity
                    entity = context.scene.sketcher.entities.get(index)
                    if entity and entity.is_selectable(context):
                        # Calculate depth for proper sorting
                        depth = float('inf')  # Default to far away
                        if isinstance(entity, SlvsWorkplane):
                            # Calculate depth as distance from view origin to workplane center
                            center_pos = entity.p1.location
                            depth = (center_pos - view_origin).length
                        
                        # Store depth information
                        entity_depths[index] = depth
                        global_data.hover_stack.append(index)
        
        # If we found entities, sort by depth and select the closest one
        if global_data.hover_stack:
            # Sort all found entities by depth
            global_data.hover_stack.sort(key=lambda idx: entity_depths.get(idx, float('inf')))
            
            # Set hover to the closest entity
            global_data.hover_stack_index = 0
            global_data.hover = global_data.hover_stack[0]
            
            # Check if it's a workplane edge
            entity = context.scene.sketcher.entities.get(global_data.hover)
            if entity and isinstance(entity, SlvsWorkplane):
                pos_2d = get_pos_2d(context, entity, location)
                
                if pos_2d and is_point_on_edge(entity, (pos_2d.x, pos_2d.y)):
                    _edge_selection_active = True
                    _selected_edge_workplane = entity.slvs_index
            
            context.area.tag_redraw()
            return -1
        else:
            # No entity found at current position
            global_data.hover = -1
            context.area.tag_redraw()
            return -1

    def cycle_hover_stack(self, context):
        """Cycle to the next entity in the hover stack""" 
        global _edge_selection_active, _selected_edge_workplane

        if not global_data.hover_stack:
            return
        
        stack_len = len(global_data.hover_stack)
        global_data.hover_stack_index = (global_data.hover_stack_index + 1) % stack_len
        global_data.hover = global_data.hover_stack[global_data.hover_stack_index]
        
        # Update edge selection tracking based on the currently cycled entity
        entity = context.scene.sketcher.entities.get(global_data.hover)
        # Simple check: if it's a workplane, assume edge for now
        if entity and isinstance(entity, SlvsWorkplane):
             # Re-check if the current cursor position is actually on its edge?
             # For now, just assume if it's a workplane in the stack, it might be an edge.
            _edge_selection_active = True
            _selected_edge_workplane = entity.slvs_index
        else:
            _edge_selection_active = False
            _selected_edge_workplane = -1
            
        # Log what entity we're hovering
        entity_name = entity.name if entity else "Unknown"
        logger.debug(f"Cycling to entity {global_data.hover_stack_index + 1}/{stack_len}: {entity_name} (index: {global_data.hover})")
        
        context.area.tag_redraw()


def _spiral(N, M):
    x,y = 0,0   
    dx, dy = 0, -1

    for dumb in range(N*M):
        if abs(x) == abs(y) and [dx,dy] != [1,0] or x>0 and y == 1-x:  
            dx, dy = -dy, dx            # corner, change direction

        if abs(x)>N/2 or abs(y)>M/2:    # non-square
            dx, dy = -dy, dx            # change direction
            x, y = -y+dx, x+dy          # jump

        yield x, y
        x, y = x+dx, y+dy

def get_spiral_coords(X: int, Y: int, width: int, height: int, radius: int = 0):
    """Returns a list of coordinates to check starting from given position spiraling out"""

    for x, y in _spiral(radius+1,radius+1):
        if 0 <= (X+x) <= width and 0 <= (Y+y) <= height:
            yield (X+x, Y+y)