from bpy.types import Operator, Context, Event
from bpy.utils import register_classes_factory
from mathutils.geometry import intersect_line_plane

from .. import global_data
from ..declarations import Operators
from ..solver import Solver
from ..utilities.view import get_picking_origin_dir


class View3D_OT_slvs_tweak(Operator):
    """Tweak the hovered element"""

    bl_idname = Operators.Tweak
    bl_label = "Tweak Solvespace Entities"
    bl_options = {"UNDO"}

    def invoke(self, context: Context, event):
        index = global_data.hover
        # TODO: hover should be -1 if nothing is hovered, not None!
        if index is None or index == -1:
            return {"PASS_THROUGH"}

        entity = context.scene.sketcher.entities.get(index)
        self.entity = entity

        coords = (event.mouse_region_x, event.mouse_region_y)
        origin, view_vector = get_picking_origin_dir(context, coords)

        if not hasattr(entity, "closest_picking_point"):
            if not hasattr(entity, "sketch"):
                self.report(
                    {"WARNING"}, "Cannot tweak element of type {}".format(type(entity))
                )
                return {"CANCELLED"}

            # For 2D entities it should be enough precise to get picking point from
            # intersection with workplane
            wp = entity.sketch.wp
            coords = (event.mouse_region_x, event.mouse_region_y)
            origin, dir = get_picking_origin_dir(context, coords)
            end_point = dir * context.space_data.clip_end + origin
            pos = intersect_line_plane(origin, end_point, wp.p1.location, wp.normal)
        else:
            pos = entity.closest_picking_point(origin, view_vector)

        # find the depth
        self.depth = (pos - origin).length

        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context: Context, event: Event):
        if event.type == "LEFTMOUSE" and event.value == "RELEASE":
            context.window.cursor_modal_restore()
            return {"FINISHED"}

        context.window.cursor_modal_set("HAND")

        if event.type == "MOUSEMOVE":
            entity = self.entity
            coords = (event.mouse_region_x, event.mouse_region_y)

            # Get tweaking position
            origin, dir = get_picking_origin_dir(context, coords)

            if hasattr(entity, "sketch"):
                wp = entity.wp
                end_point = dir * context.space_data.clip_end + origin
                pos = intersect_line_plane(origin, end_point, wp.p1.location, wp.normal)
            else:
                pos = dir * self.depth + origin

            sketch = context.scene.sketcher.active_sketch
            solver = Solver(context, sketch)
            solver.tweak(entity, pos)
            retval = solver.solve(report=False)

            # NOTE: There's no blocking cursor
            # also solving frequently returns an error while tweaking which causes flickering
            # if retval != 0:
            # context.window.cursor_modal_set("WAIT")
            # self.report({'WARNING'}, "Cannot solve sketch, error: {}".format(retval))

            context.area.tag_redraw()

        return {"RUNNING_MODAL"}


register, unregister = register_classes_factory((View3D_OT_slvs_tweak,))
