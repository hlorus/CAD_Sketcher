import bpy
from bpy.types import Context, Event, Operator
from bpy.utils import register_classes_factory

from .. import global_data
from ..curve_solver import CurveSolver
from ..declarations import Operators
from ..drawing import selection
from ..drawing.snap import draw_snap_marker
from ..model.sketch_ref import get_active_sketch
from ..utilities.curve_data import (
    get_curve_data,
    refresh_curve_geometry,
)
from ..utilities.view import (
    get_blender_snap_info,
    get_picking_origin_dir,
    get_pos_2d,
    get_wp_matrix,
)


class View3D_OT_slvs_tweak(Operator):
    """Tweak the hovered element"""

    bl_idname = Operators.Tweak
    bl_label = "Tweak Solvespace Entities"
    bl_options = {"UNDO"}

    # Current geometry snap target for the marker (dict from get_blender_snap_info
    # or None), and the POST_PIXEL draw handle that renders it while dragging.
    _snap = None
    _snap_handle = None

    def _register_snap_marker(self, context: Context):
        """Show the same snap marker the draw tools use, for the drag's lifetime."""
        self._snap = None
        self._snap_handle = bpy.types.SpaceView3D.draw_handler_add(
            draw_snap_marker, (self, context), "WINDOW", "POST_PIXEL"
        )

    def _remove_snap_marker(self):
        handle = getattr(self, "_snap_handle", None)
        if handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(handle, "WINDOW")
            self._snap_handle = None
        self._snap = None

    def _get_wp(self):
        """The sketch's workplane object (same resolution as the solver uses)."""
        wp = self.sketch.workplane_object if self.sketch else None
        if not wp and self.sketch.target_object and self.sketch.target_object.parent:
            wp = self.sketch.target_object.parent
        return wp

    def _get_tweak_pos(self, context: Context, coords):
        """World-space picking position, honoring Blender's snapping."""
        wp = self._get_wp()
        if wp is None:
            return None
        pos_2d = get_pos_2d(context, wp, coords, respect_snapping=True)
        if pos_2d is None:
            return None
        return get_wp_matrix(wp) @ pos_2d.to_3d()

    def invoke(self, context: Context, event):
        curve_id = selection.hover
        if not curve_id:
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

        # Get picking position on the workplane (honoring Blender's snapping)
        coords = (event.mouse_region_x, event.mouse_region_y)
        origin, _view_vector = get_picking_origin_dir(context, coords)

        pos = self._get_tweak_pos(context, coords)
        if pos is None:
            return {"PASS_THROUGH"}

        self.depth = (pos - origin).length

        self._register_snap_marker(context)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context: Context, event: Event):
        if event.type == "LEFTMOUSE" and event.value == "RELEASE":
            # Topology rebuild to trigger GN modifier refresh
            refresh_curve_geometry(self.sketch)
            self._remove_snap_marker()
            context.window.cursor_modal_restore()
            return {"FINISHED"}

        context.window.cursor_modal_set("HAND")

        if event.type == "MOUSEMOVE":
            coords = (event.mouse_region_x, event.mouse_region_y)

            global_data.snap_bypass = bool(event.shift)  # Shift bypasses snapping
            # Same snap target the position uses, surfaced as a marker while
            # dragging (issue #106).
            self._snap = get_blender_snap_info(context, coords)
            pos = self._get_tweak_pos(context, coords)
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
