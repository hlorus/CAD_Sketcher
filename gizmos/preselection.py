import gpu
import logging
from bpy.types import Gizmo, GizmoGroup
import math
from mathutils import Vector

from .. import global_data
from ..declarations import Gizmos, GizmoGroups
from ..draw_handler import ensure_selection_texture
from ..utilities.index import rgb_to_index
from ..model.types import SlvsWorkplane
from .utilities import context_mode_check

logger = logging.getLogger(__name__)

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


def is_point_on_edge(workplane, point_2d, tolerance=2):
    """Check if a 2D point is close to any edge of the workplane square
    
    Args:
        workplane: The workplane to check edges for
        point_2d: 2D point coordinates on the workplane (x, y)
        tolerance: Distance threshold for edge detection (greatly increased)
    
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
    
    # Check distance to each edge with a very generous tolerance
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
        global _last_mouse_pos, _edge_selection_active, _selected_edge_workplane
        
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
        
        # Check if mouse has moved since last position
        current_pos = (mouse_x, mouse_y)
        moved_significantly = False
        
        if _last_mouse_pos is not None:
            # Calculate distance moved
            dx = current_pos[0] - _last_mouse_pos[0]
            dy = current_pos[1] - _last_mouse_pos[1]
            distance_moved = math.sqrt(dx*dx + dy*dy)
            
            # Only consider significant movement if moved more than 5 pixels
            moved_significantly = distance_moved > 5
            
        # Only clear the hover stack when moved significantly
        if moved_significantly:
            # Reset selection only if not in edge selection mode or moved significantly
            if not _edge_selection_active or distance_moved > 20:
                global_data.hover_stack = []
                global_data.hover_stack_index = -1
                _edge_selection_active = False
                _selected_edge_workplane = -1
        
        _last_mouse_pos = current_pos

        offscreen = global_data.offscreen
        if not offscreen:
            return -1
        
        # If we're currently in edge selection mode, first check if the 
        # previously selected edge is still valid
        if _edge_selection_active and _selected_edge_workplane != -1:
            entity = context.scene.sketcher.entities.get(_selected_edge_workplane)
            if entity and entity.is_selectable(context) and isinstance(entity, SlvsWorkplane):
                # Check if we're still on the edge
                from ..utilities.view import get_pos_2d
                pos_2d = get_pos_2d(context, entity, location)
                
                if pos_2d and is_point_on_edge(entity, (pos_2d.x, pos_2d.y), tolerance=3.0):
                    # Still on the edge, keep selection active
                    if _selected_edge_workplane not in global_data.hover_stack:
                        global_data.hover_stack = [_selected_edge_workplane]
                    
                    global_data.hover_stack_index = 0
                    global_data.hover = _selected_edge_workplane
                    context.area.tag_redraw()
                    return -1
                else:
                    # Not on the edge anymore and moved significantly
                    if moved_significantly:
                        _edge_selection_active = False
                        _selected_edge_workplane = -1
            
        # Only find all entities if hover stack is empty
        if not global_data.hover_stack:
            found_indices = set()  # Use a set to prevent duplicates
            found_workplanes = []  # List to store found workplanes for edge detection
            entity_depths = {}  # Dictionary to store entity depths
            
            # Get view info for depth calculations
            region = context.region
            rv3d = context.region_data
            view_origin = rv3d.view_matrix.inverted().translation
            
            PICK_SIZE = 5  # select more easily
            for x, y in get_spiral_coords(mouse_x, mouse_y, context.area.width, context.area.height, PICK_SIZE):
                with offscreen.bind():
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
                            # Calculate depth for workplanes
                            depth = float('inf')  # Default to far away
                            if isinstance(entity, SlvsWorkplane):
                                # Calculate depth as distance from view origin to workplane center
                                center_pos = entity.p1.location
                                depth = (center_pos - view_origin).length
                                found_workplanes.append(entity)
                            
                            # Store depth information
                            entity_depths[index] = depth
                            global_data.hover_stack.append(index)
            
            # EVEN MORE AGGRESSIVE: Check ALL workplanes in scene for edges near cursor
            from ..utilities.view import get_pos_2d
            edge_indices = []
            
            # Check all selectable workplanes in the scene for edges
            for entity in context.scene.sketcher.entities.all:
                if isinstance(entity, SlvsWorkplane) and entity.is_selectable(context):
                    # Skip if already found in hover stack
                    if entity.slvs_index in found_indices:
                        continue
                        
                    # Get 2D position on this workplane
                    pos_2d = get_pos_2d(context, entity, location)
                    if pos_2d:
                        # Check if this 2D point is on an edge with large tolerance
                        if is_point_on_edge(entity, (pos_2d.x, pos_2d.y)):
                            edge_indices.append(entity.slvs_index)
                            
                            # Calculate depth for this workplane
                            center_pos = entity.p1.location
                            depth = (center_pos - view_origin).length
                            entity_depths[entity.slvs_index] = depth
                            
                            # Add to hover stack
                            if entity.slvs_index not in global_data.hover_stack:
                                global_data.hover_stack.append(entity.slvs_index)
            
            # Sort entities by depth (except edges which stay at the front)
            if global_data.hover_stack:
                # First separate edges and other entities
                edge_entities = [idx for idx in global_data.hover_stack if idx in edge_indices]
                other_entities = [idx for idx in global_data.hover_stack if idx not in edge_indices]
                
                # Sort the non-edge entities by depth
                other_entities.sort(key=lambda idx: entity_depths.get(idx, float('inf')))
                
                # Put edges first, then depth-sorted entities
                global_data.hover_stack = edge_entities + other_entities
                
                # Prioritize edges for edge selection mode
                if edge_entities:
                    # We found edges, enter edge selection mode
                    _edge_selection_active = True
                    _selected_edge_workplane = edge_entities[0]
                    
                    # Find the closest edge if we have multiple
                    if len(edge_entities) > 1:
                        closest_edge = min(edge_entities, key=lambda idx: entity_depths.get(idx, float('inf')))
                        _selected_edge_workplane = closest_edge
                        
                        # Reorder edge entities by depth
                        edge_entities.sort(key=lambda idx: entity_depths.get(idx, float('inf')))
                        global_data.hover_stack = edge_entities + other_entities
            
            # If we found entities, select the first one
            if global_data.hover_stack:
                global_data.hover_stack_index = 0
                global_data.hover = global_data.hover_stack[0]
                context.area.tag_redraw()
                logger.debug(f"Found {len(global_data.hover_stack)} overlapping entities at cursor")
                return -1
        
        # If we have an existing hover stack but nothing is currently hovered,
        # select the first entity in the stack
        elif global_data.hover_stack and global_data.hover == -1:
            global_data.hover_stack_index = 0
            global_data.hover = global_data.hover_stack[0]
            context.area.tag_redraw()
            return -1

        if not global_data.hover_stack:
            if global_data.hover != -1:
                context.area.tag_redraw()
                global_data.hover = -1
            # Also reset edge selection mode
            _edge_selection_active = False
            _selected_edge_workplane = -1
        
        return -1

    def cycle_hover_stack(self, context):
        """Cycle to the next entity in the hover stack"""
        global _edge_selection_active, _selected_edge_workplane
        
        if not global_data.hover_stack:
            return
        
        stack_len = len(global_data.hover_stack)
        global_data.hover_stack_index = (global_data.hover_stack_index + 1) % stack_len
        global_data.hover = global_data.hover_stack[global_data.hover_stack_index]
        
        # Update edge selection tracking
        entity = context.scene.sketcher.entities.get(global_data.hover)
        if entity and isinstance(entity, SlvsWorkplane):
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