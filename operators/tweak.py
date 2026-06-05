from bpy.types import Operator, Context, Event
from bpy.utils import register_classes_factory
from mathutils.geometry import intersect_line_plane

from .. import global_data
from ..declarations import Operators
from ..solver import Solver
from ..utilities.view import get_picking_origin_dir, get_pos_2d


class View3D_OT_slvs_tweak(Operator):
    """Tweak the hovered element"""

    bl_idname = Operators.Tweak
    bl_label = "Tweak Solvespace Entities"
    bl_options = {"UNDO"}

    def _get_tweak_pos(self, context: Context, entity, coords):
        wp = entity.wp
        pos_2d = get_pos_2d(context, wp, coords, respect_snapping=True)
        if pos_2d is None:
            return None
        return wp.matrix_basis @ pos_2d.to_3d()

    def invoke(self, context: Context, event):
        index = global_data.hover
        # TODO: hover should be -1 if nothing is hovered, not None!
        if index is None or index == -1:
            return {"PASS_THROUGH"}

        entity = context.scene.sketcher.entities.get(index)
        self.entity = entity
        self._moved = False

        coords = (event.mouse_region_x, event.mouse_region_y)
        origin, view_vector = get_picking_origin_dir(context, coords)

        if not hasattr(entity, "closest_picking_point"):
            if not hasattr(entity, "sketch"):
                self.report(
                    {"WARNING"}, "Cannot tweak element of type {}".format(type(entity))
                )
                return {"CANCELLED"}

            coords = (event.mouse_region_x, event.mouse_region_y)
            pos = self._get_tweak_pos(context, entity, coords)
        else:
            pos = entity.closest_picking_point(origin, view_vector)

        # find the depth
        self.depth = (pos - origin).length

        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context: Context, event: Event):
        if event.type == "LEFTMOUSE" and event.value == "RELEASE":
            context.window.cursor_modal_restore()
            sketch = context.scene.sketcher.active_sketch
            if sketch:
                sketch.geometry_solved = False
            return {"FINISHED"}

        context.window.cursor_modal_set("HAND")

        if event.type == "MOUSEMOVE":
            entity = self.entity
            coords = (event.mouse_region_x, event.mouse_region_y)

            # Get tweaking position
            origin, dir = get_picking_origin_dir(context, coords)

            if hasattr(entity, "sketch"):
                pos = self._get_tweak_pos(context, entity, coords)
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
            self._moved = True

        return {"RUNNING_MODAL"}


register, unregister = register_classes_factory((View3D_OT_slvs_tweak,))
