import gpu
import logging
from bpy.types import Gizmo, GizmoGroup

from .. import global_data
from ..declarations import Gizmos, GizmoGroups
from ..draw_handler import ensure_selection_texture
from ..utilities.index import rgb_to_index
from .utilities import context_mode_check

logger = logging.getLogger(__name__)

_last_mouse_pos = None

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


# NOTE: idealy gizmo would expose active element as a property and
# operators would access hovered element from there
class VIEW3D_GT_slvs_preselection(Gizmo):
    bl_idname = Gizmos.Preselection

    __slots__ = ()

    def draw(self, context):
        pass

    def test_select(self, context, location):
        global _last_mouse_pos
        
        # reset gizmo highlight
        if global_data.highlight_constraint:
            global_data.highlight_constraint = None
            context.area.tag_redraw()

        if global_data.highlight_entities:
            global_data.highlight_entities.clear()
            context.area.tag_redraw()

        # ensure selection texture is up to date
        # TODO: avoid dependency on operators module?
        ensure_selection_texture(context)

        # sample selection texture and mark hovered entity
        mouse_x, mouse_y = location
        
        # Check if mouse has moved since last position
        current_pos = (mouse_x, mouse_y)
        # Use the global variable _last_mouse_pos instead of self.last_pos
        if _last_mouse_pos is not None and _last_mouse_pos != current_pos:
            # Mouse moved, clear stack
            global_data.hover_stack = []
            global_data.hover_stack_index = -1
        
        _last_mouse_pos = current_pos

        offscreen = global_data.offscreen
        if not offscreen:
            logger.debug("No offscreen buffer available for hover detection")
            return -1
            
        # Only find all entities if hover stack is empty
        if not global_data.hover_stack:
            found_indices = set()  # Use a set to prevent duplicates
            
            # TODO: Read buffer only once
            PICK_SIZE = 10
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
                            global_data.hover_stack.append(index)
            
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
        
        return -1

    def cycle_hover_stack(self, context):
        """Cycle to the next entity in the hover stack"""
        if not global_data.hover_stack:
            return
        
        stack_len = len(global_data.hover_stack)
        global_data.hover_stack_index = (global_data.hover_stack_index + 1) % stack_len
        global_data.hover = global_data.hover_stack[global_data.hover_stack_index]
        
        # Log what entity we're hovering
        entity = context.scene.sketcher.entities.get(global_data.hover)
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