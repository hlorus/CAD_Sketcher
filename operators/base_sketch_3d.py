"""Stateful placement helpers for native free-3D sketches (#607)."""

from mathutils import Vector
from mathutils.geometry import intersect_line_line, intersect_line_plane

from ..model.curve_ref import CurveRef, PointRef
from ..model.native_3d import create_point_3d
from ..utilities import view
from .base_2d import Operator2d
from .utilities import ignore_hover


_AXIS = (
    Vector((1.0, 0.0, 0.0)),
    Vector((0.0, 1.0, 0.0)),
    Vector((0.0, 0.0, 1.0)),
)


def _project_to_axis(point, anchor, axis_index):
    axis = _AXIS[axis_index]
    return anchor + axis * (point - anchor).dot(axis)


def _project_to_plane(point, anchor, normal_index):
    normal = _AXIS[normal_index]
    return point - normal * (point - anchor).dot(normal)


def resolve_locked_position(
    point,
    anchor,
    *,
    axis_lock=None,
    plane_lock=None,
    ray_origin=None,
    ray_end=None,
):
    """Resolve an input point against an axis or plane lock.

    ``plane_lock`` stores the plane normal axis: X -> YZ, Y -> XZ, Z -> XY.
    When a view ray is available an axis lock uses the closest point on the
    locked axis to that ray, falling back to orthogonal projection for parallel
    cases. The helper is pure geometry so it can be regression-tested without a
    viewport.
    """
    point = Vector(point).to_3d()
    anchor = Vector(anchor).to_3d()

    if plane_lock is not None:
        return _project_to_plane(point, anchor, plane_lock)

    if axis_lock is None:
        return point

    if ray_origin is not None and ray_end is not None:
        axis = _AXIS[axis_lock]
        result = intersect_line_line(
            Vector(ray_origin).to_3d(),
            Vector(ray_end).to_3d(),
            anchor,
            anchor + axis,
        )
        if result is not None:
            return Vector(result[1])

    return _project_to_axis(point, anchor, axis_lock)


class OperatorSketch3d(Operator2d):
    """Stateful native-3D placement while reusing the 2D operator framework."""

    _plane_lock = None

    @classmethod
    def poll(cls, context):
        obj = context.scene.sketcher.active_sketch_object
        if obj is None:
            return False
        from ..model.sketch_ref import Sketch

        return Sketch(obj).is_3d

    def set_state(self, context, index):
        self._plane_lock = None
        return super().set_state(context, index)

    def modal(self, context, event):
        # Shift+X/Y/Z locks to YZ/XZ/XY respectively. Plain X/Y/Z is handled by
        # StatefulOperatorLogic's existing global-axis lock implementation.
        if (
            event.value == "PRESS"
            and event.shift
            and event.type in ("X", "Y", "Z")
            and getattr(self.state, "axis_lock", False)
        ):
            axis = "XYZ".index(event.type)
            self._axis_lock = None
            self._plane_lock = None if self._plane_lock == axis else axis
            return self.evaluate_state(context, event, False)
        return super().modal(context, event)

    def _anchor_world(self, context):
        if self.state_index > 0:
            previous = self.get_point(context, self.state_index - 1)
            if isinstance(previous, PointRef) and previous.valid:
                return previous.location.copy()

        origin = self.sketch.target_object.parent
        if origin is not None:
            return origin.matrix_world.translation.copy()
        return self.sketch.target_object.matrix_world.translation.copy()

    def _view_plane_normal(self, context):
        center = Vector((context.region.width * 0.5, context.region.height * 0.5))
        _origin, direction = view.get_picking_origin_dir(context, center)
        return Vector(direction).normalized()

    def state_func(self, context, coords):
        anchor = self._anchor_world(context)
        ray_origin, ray_end = view.get_picking_origin_end(context, coords)

        snap = view.get_blender_snap_info(context, coords)
        self._snap = snap
        if snap and "world_point" in snap:
            world = Vector(snap["world_point"])
            self.state_data["snapped_external"] = True
        else:
            self.state_data["snapped_external"] = False
            normal = self._view_plane_normal(context)
            world = intersect_line_plane(ray_origin, ray_end, anchor, normal)
            if world is None:
                world = anchor.copy()

        world = resolve_locked_position(
            world,
            anchor,
            axis_lock=self._axis_lock,
            plane_lock=self._plane_lock,
            ray_origin=ray_origin,
            ray_end=ray_end,
        )
        local = self.sketch.target_object.matrix_world.inverted_safe() @ world
        return Vector(local).to_3d()

    def create_element(self, context, values, state, state_data):
        location = Vector(values[0]).to_3d()
        fixed = bool(state_data.get("snapped_external", False))
        ref = create_point_3d(self.sketch, location, fixed=fixed)
        if ref is None:
            return None

        ignore_hover(ref.curve_id)
        state_data["type"] = PointRef
        state_data["curve_id"] = ref.curve_id
        return ref.curve_id

    def get_point(self, context, index):
        data = self._state_data.get(index, {})
        dtype = data.get("type")
        cid = data.get("curve_id", "")
        if cid and dtype and isinstance(dtype, type) and issubclass(dtype, CurveRef):
            return dtype(self.sketch, cid)
        if cid:
            return PointRef(self.sketch, cid)
        return super().get_point(context, index)
