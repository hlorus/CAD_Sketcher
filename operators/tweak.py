from bpy.types import Operator, Context, Event
from ..model.sketch_ref import get_active_sketch
from bpy.utils import register_classes_factory
from mathutils.geometry import intersect_line_plane

from .. import global_data
from ..declarations import Operators
from ..curve_solver import CurveSolver
from ..utilities.view import get_picking_origin_dir
from ..utilities.curve_data import get_curve_data, get_curve_type, refresh_curve_geometry
from ..utilities.workplane import get_workplane_origin_normal
from ..model.constants import SketchCurveType


class View3D_OT_slvs_tweak(Operator):
    """Tweak the hovered element"""

    bl_idname = Operators.Tweak
    bl_label = "Tweak Solvespace Entities"
    bl_options = {"UNDO"}

    def invoke(self, context: Context, event):
        curve_id = global_data.hover
        if curve_id is None or curve_id <= 0:
            return {"PASS_THROUGH"}

        sketch = get_active_sketch(context)
        if not sketch:
            return {"PASS_THROUGH"}

        self.curve_id = curve_id
        self.sketch = sketch

        # Verify curve exists
        curve_data, idx, _ = get_curve_data(sketch, curve_id)
        if curve_data is None:
            return {"PASS_THROUGH"}

        # Get picking position from workplane intersection
        coords = (event.mouse_region_x, event.mouse_region_y)
        origin, view_vector = get_picking_origin_dir(context, coords)

        wp_origin, wp_normal = get_workplane_origin_normal(sketch)
        if wp_origin is None:
            return {"PASS_THROUGH"}
        end_point = view_vector * context.space_data.clip_end + origin
        pos = intersect_line_plane(origin, end_point, wp_origin, wp_normal)

        if pos is None:
            return {"PASS_THROUGH"}

        self.depth = (pos - origin).length

        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context: Context, event: Event):
        if event.type == "LEFTMOUSE" and event.value == "RELEASE":
            # Topology rebuild to trigger GN modifier refresh
            refresh_curve_geometry(self.sketch)
            context.window.cursor_modal_restore()
            return {"FINISHED"}

        context.window.cursor_modal_set("HAND")

        if event.type == "MOUSEMOVE":
            coords = (event.mouse_region_x, event.mouse_region_y)

            origin, dir = get_picking_origin_dir(context, coords)

            wp_origin, wp_normal = get_workplane_origin_normal(self.sketch)
            if wp_origin is None:
                return {"RUNNING_MODAL"}
            end_point = dir * context.space_data.clip_end + origin
            pos = intersect_line_plane(origin, end_point, wp_origin, wp_normal)

            if pos is None:
                return {"RUNNING_MODAL"}

            solver = CurveSolver(context, self.sketch)
            solver.tweak(self.curve_id, pos)
            solver.solve()

            # Topology rebuild to trigger GN modifier refresh
            refresh_curve_geometry(self.sketch)

            context.area.tag_redraw()

        return {"RUNNING_MODAL"}


register, unregister = register_classes_factory((View3D_OT_slvs_tweak,))
