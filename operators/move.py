import bpy
import numpy as np
from bpy.props import FloatVectorProperty
from bpy.types import Context, Event, Operator
from mathutils import Vector
from mathutils.geometry import intersect_line_plane

from ..curve_solver import solve_system
from ..declarations import Operators
from ..drawing import selection
from ..model.curve_ref import PointRef, curve_ref
from ..model.native_3d import rebuild_3d_lines
from ..model.sketch_ref import get_active_sketch
from ..stateful_operator.state import state_from_args
from ..stateful_operator.utilities.register import register_stateops_factory
from ..utilities.curve_data import batch_update, refresh_curve_geometry
from ..utilities.view import get_picking_origin_dir, get_picking_origin_end, get_pos_2d
from .base_2d import Operator2d


def get_points(context: Context):
    """Return PointRefs for all selected points + points of selected lines/arcs."""
    sketch = get_active_sketch(context)
    if not sketch:
        return []

    point_cids = set()

    for cid in selection.selected:
        ref = curve_ref(sketch, cid)
        if not ref.valid:
            continue

        if isinstance(ref, PointRef):
            point_cids.add(cid)
        else:
            # Collect relationship points
            for attr in ("start_point_id", "end_point_id", "center_point_id"):
                pt_cid = ref._get_attr_value(attr, 0)
                if pt_cid:
                    point_cids.add(pt_cid)

    return [PointRef(sketch, cid) for cid in point_cids]


class View3D_OT_slvs_move(Operator, Operator2d):
    """Move selected entities around, independent of constraints"""

    bl_idname = Operators.Move
    bl_label = "Move Entities"
    bl_options = {"UNDO", "REGISTER"}

    offset: FloatVectorProperty(
        name="Offset", subtype="COORDINATES", size=2, options={"SKIP_SAVE"}
    )
    offset_3d: FloatVectorProperty(
        name="3D Offset",
        subtype="XYZ",
        size=3,
        unit="LENGTH",
        precision=5,
        options={"SKIP_SAVE"},
    )

    states = (
        state_from_args(
            "Offset",
            description=(
                "Offset vector to apply to the selection. Native 3D sketches "
                "accept numeric XYZ delta input."
            ),
            property="move_property",
            state_func="get_offset",
            interactive=True,
            axis_lock=True,
        ),
    )

    def move_property(self, _index):
        sketch = self.sketch
        return "offset_3d" if sketch and sketch.is_3d else "offset"

    # A move only shifts point positions, so override the base operator's
    # full-scene snapshot (which rebuilds every sketch's curves + constraints
    # each mouse-move) with a positions-only snapshot of the active sketch.
    def create_snapshot(self, context: Context):
        sketch = get_active_sketch(context)
        if not sketch or not sketch.target_object or not sketch.target_object.data:
            return {}
        obj = sketch.target_object
        positions = np.empty(len(obj.data.points) * 3, dtype=np.float32)
        obj.data.points.foreach_get("position", positions)
        return {"name": obj.name, "positions": positions}

    def restore_snapshot(self, context: Context, snapshot):
        if not snapshot:
            return
        obj = bpy.data.objects.get(snapshot["name"])
        if not obj or not obj.data:
            return
        positions = snapshot["positions"]
        if len(obj.data.points) * 3 != len(positions):
            return  # topology changed unexpectedly; leave as-is
        obj.data.points.foreach_set("position", positions)
        obj.data.update_tag()

    def invoke(self, context: Context, event: Event):
        coords = Vector((event.mouse_region_x, event.mouse_region_y))
        sketch = get_active_sketch(context)
        is_3d = bool(sketch and sketch.is_3d)

        # 3D placement data is independent of Operator2d.init(), so prepare it
        # before the modal starts. Keep classic 2D initialization after super()
        # because _get_wp() relies on the active-sketch cache set there.
        if is_3d:
            points = get_points(context)
            if points:
                self._move_anchor_world = points[0].location.copy()
            elif sketch.target_object.parent:
                self._move_anchor_world = (
                    sketch.target_object.parent.matrix_world.translation.copy()
                )
            else:
                self._move_anchor_world = sketch.target_object.matrix_world.translation.copy()

            _origin, direction = get_picking_origin_dir(context, coords)
            self._move_view_normal = Vector(direction).normalized()
            ray_origin, ray_end = get_picking_origin_end(context, coords)
            self.origin_pos_world = intersect_line_plane(
                ray_origin,
                ray_end,
                self._move_anchor_world,
                self._move_view_normal,
            )
            if self.origin_pos_world is None:
                self.origin_pos_world = self._move_anchor_world.copy()

        retval = super().invoke(context, event)
        if not is_3d:
            self.origin_coords = get_pos_2d(context, self._get_wp(), coords)
        return retval

    def get_offset(self, context: Context, coords):
        if self.sketch.is_3d:
            ray_origin, ray_end = get_picking_origin_end(context, coords)
            pos = intersect_line_plane(
                ray_origin,
                ray_end,
                self._move_anchor_world,
                self._move_view_normal,
            )
            if pos is None:
                return Vector((0.0, 0.0, 0.0))

            delta_world = Vector(pos) - self.origin_pos_world
            if self._axis_lock is not None:
                constrained = Vector((0.0, 0.0, 0.0))
                constrained[self._axis_lock] = delta_world[self._axis_lock]
                delta_world = constrained

            basis = self.sketch.target_object.matrix_world.to_3x3()
            return basis.inverted_safe() @ delta_world

        wp = self._get_wp()
        pos = get_pos_2d(context, wp, coords)
        if pos is None:
            return None
        delta = Vector(pos) - self.origin_coords
        if self._axis_lock is not None:
            constrained = Vector((0.0, 0.0))
            if self._axis_lock < 2:
                constrained[self._axis_lock] = delta[self._axis_lock]
            delta = constrained
        return delta

    def _move_points_3d(self, points):
        offset = Vector(self.offset_3d).to_3d()
        curve_data = self.sketch.target_object.data

        for point in points:
            if not point._resolve():
                continue
            point_index = point._curve_slice.points[0].index
            current = Vector(curve_data.points[point_index].position)
            curve_data.points[point_index].position = tuple(current + offset)

        rebuild_3d_lines(self.sketch)
        curve_data.update_tag()

    def main(self, context: Context):
        points = get_points(context)
        moved_ids = {p.curve_id for p in points}

        if self.sketch.is_3d:
            self._move_points_3d(points)
            return {"FINISHED"}

        # Only the moved points changed, so scope the segment rebuild to them.
        with batch_update(self.sketch, point_ids=moved_ids):
            offset = Vector(self.offset[:2])
            for point in points:
                point.co = point.co + offset
        return {"FINISHED"}

    def fini(self, context: Context, succeede: bool):
        if succeede:
            if self.sketch:
                self.sketch.geometry_solved = False
            solve_system(context, sketch=self.sketch)
            refresh_curve_geometry(self.sketch)


register, unregister = register_stateops_factory((View3D_OT_slvs_move,))
