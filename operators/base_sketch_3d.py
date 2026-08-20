"""Stateful placement helpers for native free-3D sketches (#607).

Free-3D placement is anchored in world space: the origin Empty provides the
fallback view-plane depth until a real previous point exists, while native curve
coordinates remain local to that origin frame.
"""

import mathutils  # noqa: I001 - Blender module + relative addon imports
import mathutils.geometry

from ..model import curve_ref, native_3d
from ..utilities import view
from . import base_2d, utilities


_AXIS = (
    mathutils.Vector((1.0, 0.0, 0.0)),
    mathutils.Vector((0.0, 1.0, 0.0)),
    mathutils.Vector((0.0, 0.0, 1.0)),
)


def _project_to_axis(point, anchor, axis_index):
    axis = _AXIS[axis_index]
    return anchor + axis * (point - anchor).dot(axis)


def _project_to_plane(point, anchor, normal_index):
    normal = _AXIS[normal_index]
    return point - normal * (point - anchor).dot(normal)


def view_plane_intersection(ray_origin, ray_end, anchor, normal):
    """Intersect a view ray with the temporary placement plane.

    ``anchor`` is the depth reference: the 3D-sketch origin for the first point
    (or whenever no previous point exists), and the previous point afterwards.
    A parallel ray falls back to the anchor itself so placement remains stable.
    This is kept as a pure helper so the origin-depth contract is testable without
    a live viewport.
    """
    anchor = mathutils.Vector(anchor).to_3d()
    world = mathutils.geometry.intersect_line_plane(
        mathutils.Vector(ray_origin).to_3d(),
        mathutils.Vector(ray_end).to_3d(),
        anchor,
        mathutils.Vector(normal).to_3d().normalized(),
    )
    return mathutils.Vector(world).to_3d() if world is not None else anchor.copy()


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
    point = mathutils.Vector(point).to_3d()
    anchor = mathutils.Vector(anchor).to_3d()

    if plane_lock is not None:
        return _project_to_plane(point, anchor, plane_lock)

    if axis_lock is None:
        return point

    if ray_origin is not None and ray_end is not None:
        axis = _AXIS[axis_lock]
        result = mathutils.geometry.intersect_line_line(
            mathutils.Vector(ray_origin).to_3d(),
            mathutils.Vector(ray_end).to_3d(),
            anchor,
            anchor + axis,
        )
        if result is not None:
            return mathutils.Vector(result[1])

    return _project_to_axis(point, anchor, axis_lock)


def restore_native_3d_segments(sketch):
    """Restore XYZ segment geometry from native 3D endpoint curves.

    The 3D draw tools intentionally reuse the mature 2D stateful framework. A
    late generic rebuild in that framework can still touch segment geometry and
    project it to XY even though the native endpoint curves retain their XYZ
    coordinates. Re-sync after stateful finalization so the committed segment is
    always derived from the authoritative 3D point curves.
    """
    if sketch is None or not native_3d.is_3d_sketch(sketch):
        return
    native_3d.rebuild_3d_lines(sketch)


class OperatorSketch3d(base_2d.Operator2d):
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

    def _end(self, context, succeede, *args, **kwargs):
        # Let the shared stateful framework complete first. Any legacy 2D segment
        # rebuild it performs during teardown has then already happened, so the
        # final operation here can safely restore the authoritative endpoint XYZ.
        result = super()._end(context, succeede, *args, **kwargs)
        if succeede:
            restore_native_3d_segments(self.sketch)
        return result

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
        # Mirror the 2D chaining model: once a previous point really exists it
        # becomes the temporary-plane depth. For deferred point creation the
        # previous state's placed coordinate is the authoritative anchor until
        # its PointRef becomes resolvable; only then fall back to the origin.
        if self.state_index > 0:
            previous = self.get_point(context, self.state_index - 1)
            if isinstance(previous, curve_ref.PointRef) and previous.valid:
                return previous.location.copy()

            # Points are created deferred in redo_states(), so the immediately
            # preceding state can have a valid placed coordinate before it has a
            # resolvable PointRef. Use that coordinate so a line's second point
            # chains from the first point rather than flattening to origin depth.
            prev_state = self.get_states_definition()[self.state_index - 1]
            prop = getattr(prev_state, "property", None)
            if prop and getattr(self, prop, None) is not None:
                frame = self.sketch.target_object.parent or self.sketch.target_object
                return (
                    frame.matrix_world @ mathutils.Vector(getattr(self, prop)).to_3d()
                ).copy()

        origin = self.sketch.target_object.parent
        if origin is not None:
            return origin.matrix_world.translation.copy()
        return self.sketch.target_object.matrix_world.translation.copy()

    def _view_plane_normal(self, context):
        center = mathutils.Vector(
            (context.region.width * 0.5, context.region.height * 0.5)
        )
        _origin, direction = view.get_picking_origin_dir(context, center)
        return mathutils.Vector(direction).normalized()

    def state_func_3d(self, context, coords):
        """Resolve placement on the native 3D temporary view-aligned plane.

        3D pointer states explicitly bind this callback instead of relying on
        the generic state callback fallback. That prevents line endpoints from
        ever being routed through ``Operator2d.state_func`` (which projects onto
        the sketch workplane/XY plane).
        """
        anchor = self._anchor_world(context)
        ray_origin, ray_end = view.get_picking_origin_end(context, coords)

        snap = view.get_blender_snap_info(context, coords)
        self._snap = snap
        if snap and "world_point" in snap:
            world = mathutils.Vector(snap["world_point"])
            self.state_data["snapped_external"] = True
        else:
            self.state_data["snapped_external"] = False
            world = view_plane_intersection(
                ray_origin,
                ray_end,
                anchor,
                self._view_plane_normal(context),
            )

        world = resolve_locked_position(
            world,
            anchor,
            axis_lock=self._axis_lock,
            plane_lock=self._plane_lock,
            ray_origin=ray_origin,
            ray_end=ray_end,
        )
        # The free-3D Curves child is identity-parented to the origin Empty. Use
        # that frame directly so interactive origin transforms cannot leave a
        # stale child matrix between depsgraph updates while placing new points.
        frame = self.sketch.target_object.parent
        matrix = (
            frame.matrix_world
            if frame is not None
            else self.sketch.target_object.matrix_world
        )
        local = matrix.inverted_safe() @ world
        return mathutils.Vector(local).to_3d()

    def state_func(self, context, coords):
        """Compatibility fallback for 3D operators without an explicit callback."""
        return self.state_func_3d(context, coords)

    def create_element_3d(self, context, values, state, state_data):
        """Create an XYZ native point for a 3D pointer state."""
        location = mathutils.Vector(values[0]).to_3d()
        fixed = bool(state_data.get("snapped_external", False))
        ref = native_3d.create_point_3d(self.sketch, location, fixed=fixed)
        if ref is None:
            return None

        utilities.ignore_hover(ref.curve_id)
        state_data["type"] = curve_ref.PointRef
        state_data["curve_id"] = ref.curve_id
        return ref.curve_id

    def create_element(self, context, values, state, state_data):
        """Compatibility fallback for 3D pointer creation."""
        return self.create_element_3d(context, values, state, state_data)

    def get_point(self, context, index):
        data = self._state_data.get(index, {})
        dtype = data.get("type")
        cid = data.get("curve_id", "")
        if (
            cid
            and dtype
            and isinstance(dtype, type)
            and issubclass(dtype, curve_ref.CurveRef)
        ):
            return dtype(self.sketch, cid)
        if cid:
            return curve_ref.PointRef(self.sketch, cid)
        return super().get_point(context, index)
