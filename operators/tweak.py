import bpy
from bpy.types import Context, Event, Operator
from bpy.utils import register_classes_factory
from mathutils import Vector
from mathutils.geometry import intersect_line_plane

from .. import global_data
from ..curve_solver import CurveSolver
from ..declarations import Operators
from ..drawing import selection
from ..drawing.snap import draw_snap_marker
from ..model.constants import SketchCurveType
from ..model.curve_ref import PointRef
from ..model.native_3d import rebuild_3d_lines
from ..model.sketch_ref import get_active_sketch
from ..utilities.curve_data import (
    get_curve_data,
    get_curve_type,
    refresh_curve_geometry,
)
from ..utilities.view import (
    get_blender_snap_info,
    get_picking_origin_dir,
    get_picking_origin_end,
    get_pos_2d,
    get_wp_matrix,
)
from .base_sketch_3d import resolve_locked_position


class View3D_OT_slvs_tweak(Operator):
    """Tweak the hovered element"""

    bl_idname = Operators.Tweak
    bl_label = "Tweak Solvespace Entities"
    bl_options = {"UNDO"}

    # Current geometry snap target for the marker (dict from get_blender_snap_info
    # or None), and the POST_PIXEL draw handle that renders it while dragging.
    _snap = None
    _snap_handle = None
    _axis_lock = None
    _plane_lock = None
    _tweak_anchor = None
    _view_normal = None

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

    def _get_tweak_pos_3d(self, context: Context, coords):
        """World-space free-3D drag position on the temporary interaction plane."""
        ray_origin, ray_end = get_picking_origin_end(context, coords)
        self._snap = get_blender_snap_info(context, coords)

        if self._snap and "world_point" in self._snap:
            pos = Vector(self._snap["world_point"])
        else:
            pos = intersect_line_plane(
                ray_origin,
                ray_end,
                self._tweak_anchor,
                self._view_normal,
            )
            if pos is None:
                pos = self._tweak_anchor.copy()

        return resolve_locked_position(
            pos,
            self._tweak_anchor,
            axis_lock=self._axis_lock,
            plane_lock=self._plane_lock,
            ray_origin=ray_origin,
            ray_end=ray_end,
        )

    def _get_tweak_pos(self, context: Context, coords):
        """World-space picking position, honoring Blender's snapping."""
        if self.sketch.is_3d:
            return self._get_tweak_pos_3d(context, coords)

        wp = self._get_wp()
        if wp is None:
            return None
        pos_2d = get_pos_2d(context, wp, coords, respect_snapping=True)
        if pos_2d is None:
            return None
        return get_wp_matrix(wp) @ pos_2d.to_3d()

    def _set_3d_point_position(self, pos):
        curve_data, idx, _ = get_curve_data(self.sketch, self.curve_id)
        if curve_data is None or idx is None:
            return False
        curve_slice = curve_data.curves[idx]
        if not curve_slice.points_length:
            return False

        local = self.sketch.target_object.matrix_world.inverted_safe() @ pos
        point_index = curve_slice.points[0].index
        curve_data.points[point_index].position = tuple(local)
        rebuild_3d_lines(self.sketch)
        curve_data.update_tag()
        return True

    def invoke(self, context: Context, event):
        curve_id = selection.hover
        if not curve_id:
            return {"PASS_THROUGH"}

        sketch = get_active_sketch(context)
        if not sketch:
            return {"PASS_THROUGH"}

        self.curve_id = curve_id
        self.sketch = sketch
        self._axis_lock = None
        self._plane_lock = None

        # Verify curve exists.
        curve_data, idx, _ = get_curve_data(sketch, curve_id)
        if curve_data is None:
            return {"PASS_THROUGH"}

        coords = (event.mouse_region_x, event.mouse_region_y)
        origin, view_vector = get_picking_origin_dir(context, coords)

        if sketch.is_3d:
            # The first editing slice intentionally tweaks native 3D points;
            # line editing continues through its referenced endpoint points.
            if get_curve_type(sketch, curve_id) != SketchCurveType.POINT:
                return {"PASS_THROUGH"}
            self._tweak_anchor = PointRef(sketch, curve_id).location.copy()
            self._view_normal = Vector(view_vector).normalized()

        pos = self._get_tweak_pos(context, coords)
        if pos is None:
            return {"PASS_THROUGH"}

        self.depth = (pos - origin).length

        self._register_snap_marker(context)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context: Context, event: Event):
        if event.type == "LEFTMOUSE" and event.value == "RELEASE":
            # Dragging a point onto an external-geometry snap anchors it there,
            # matching placement snapping (issue #106) — otherwise a later solve
            # could pull the point back off the snapped location.
            if (
                self._snap is not None
                and get_curve_type(self.sketch, self.curve_id) == SketchCurveType.POINT
            ):
                PointRef(self.sketch, self.curve_id).fixed = True

            if self.sketch.is_3d:
                CurveSolver(context, self.sketch).solve()

            refresh_curve_geometry(self.sketch)
            self._remove_snap_marker()
            context.window.cursor_modal_restore()
            global_data.snap_bypass = False
            return {"FINISHED"}

        if (
            self.sketch.is_3d
            and event.value == "PRESS"
            and event.type in ("X", "Y", "Z")
        ):
            axis = "XYZ".index(event.type)
            if event.shift:
                self._axis_lock = None
                self._plane_lock = None if self._plane_lock == axis else axis
            else:
                self._plane_lock = None
                self._axis_lock = None if self._axis_lock == axis else axis
            context.area.tag_redraw()
            return {"RUNNING_MODAL"}

        context.window.cursor_modal_set("HAND")

        if event.type == "MOUSEMOVE":
            coords = (event.mouse_region_x, event.mouse_region_y)

            global_data.snap_bypass = bool(event.shift)  # Shift bypasses snapping
            if self.sketch.is_3d:
                pos = self._get_tweak_pos_3d(context, coords)
                if pos is None or not self._set_3d_point_position(pos):
                    return {"RUNNING_MODAL"}
                CurveSolver(context, self.sketch).solve()
            else:
                # Same snap target the position uses, surfaced as a marker while
                # dragging (issue #106).
                self._snap = get_blender_snap_info(context, coords)
                pos = self._get_tweak_pos(context, coords)
                if pos is None:
                    return {"RUNNING_MODAL"}

                solver = CurveSolver(context, self.sketch)
                solver.tweak(self.curve_id, pos)
                solver.solve()

            # Topology rebuild to trigger GN modifier refresh.
            refresh_curve_geometry(self.sketch)
            context.area.tag_redraw()

        return {"RUNNING_MODAL"}


register, unregister = register_classes_factory((View3D_OT_slvs_tweak,))
