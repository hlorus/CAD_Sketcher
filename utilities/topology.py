"""Topology and geometry query layer for sketch curve data.

Builds a connectivity index from curve attributes and provides
queries for connected segments, path walking, intersection,
projection, and modification.
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .curve_data import get_uuid, has_uuid_field

from mathutils import Vector, Matrix
from mathutils.geometry import intersect_line_sphere_2d, intersect_sphere_sphere_2d

from ..model.constants import SketchCurveType
from ..model.curve_ref import (
    CurveRef, PointRef, LineRef, ArcRef, CircleRef, curve_ref,
)
from ..utilities.math import range_2pi


@dataclass
class PathResult:
    """Result of a path walk."""
    segments: List[CurveRef] = field(default_factory=list)
    directions: List[bool] = field(default_factory=list)  # True = inverted

    @property
    def is_cyclic(self):
        if len(self.segments) < 3:
            return False
        first = self.segments[0]
        last = self.segments[-1]
        # Cyclic if last connects back to first (not via the middle chain)
        first_pts = _get_point_ids(first)
        last_pts = _get_point_ids(last)
        # Exclude the point shared between first and second segment
        if len(self.segments) > 1:
            second_pts = _get_point_ids(self.segments[1])
            first_pts = first_pts - (first_pts & second_pts)
        return bool(first_pts & last_pts)


def _get_point_ids(ref):
    """Get set of point curve_ids referenced by a segment."""
    ids = set()
    sp = ref._get_attr_value("start_point_id", "")
    ep = ref._get_attr_value("end_point_id", "")
    if sp: ids.add(sp)
    if ep: ids.add(ep)
    return ids


class SketchTopology:
    """Topology and geometric query layer for a sketch's curve data."""

    def __init__(self, sketch):
        self._sketch = sketch
        self._connections = {}  # point_id → [(segment_cid, "start"|"end")]
        self._refs = {}
        self._build()

    def _build(self):
        """Build connectivity index from curve attributes."""
        obj = self._sketch.target_object
        if not obj or not obj.data:
            return

        cd = obj.data
        n = len(cd.curves)
        type_attr = cd.attributes.get("sketch_type")

        if not has_uuid_field(cd, "curve_id") or not type_attr:
            return

        for i in range(n):
            ctype = type_attr.data[i].value
            if ctype == SketchCurveType.POINT:
                continue

            cid = get_uuid(cd, "curve_id", i)
            sp = get_uuid(cd, "start_point_id", i)
            ep = get_uuid(cd, "end_point_id", i)

            if sp:
                self._connections.setdefault(sp, []).append((cid, "start"))
            if ep:
                self._connections.setdefault(ep, []).append((cid, "end"))

    def _ref(self, cid):
        """Get or create a CurveRef for a curve_id."""
        if cid not in self._refs:
            self._refs[cid] = curve_ref(self._sketch, cid)
        return self._refs[cid]

    def invalidate(self):
        """Clear cached data. Call after mutations."""
        self._connections.clear()
        self._refs.clear()
        self._build()

    # -----------------------------------------------------------------------
    # Connectivity
    # -----------------------------------------------------------------------

    def get_connected_segments(self, point_id):
        """Return segments connected to a point.

        Returns list of (segment_ref, which_end) where which_end is "start" or "end".
        """
        result = []
        for cid, end in self._connections.get(point_id, []):
            ref = self._ref(cid)
            if ref.valid:
                result.append((ref, end))
        return result

    def get_connection_point(self, seg_a, seg_b):
        """Return the shared PointRef between two segments, or None."""
        a_pts = _get_point_ids(seg_a)
        b_pts = _get_point_ids(seg_b)
        shared = a_pts & b_pts
        if shared:
            pid = next(iter(shared))
            return PointRef(self._sketch, pid)
        return None

    def connection_points(self, ref):
        """Return connection points of a segment.

        Lines/arcs: [start_point, end_point]. Circles: [].
        """
        if isinstance(ref, CircleRef):
            return []
        pts = []
        sp = ref._get_attr_value("start_point_id", "")
        ep = ref._get_attr_value("end_point_id", "")
        if sp:
            pts.append(PointRef(self._sketch, sp))
        if ep:
            pts.append(PointRef(self._sketch, ep))
        return pts

    # -----------------------------------------------------------------------
    # Direction / Tangent
    # -----------------------------------------------------------------------

    def direction_at_point(self, ref, point_id):
        """Tangent vector at a connection point, pointing away from the point."""
        if isinstance(ref, LineRef):
            p1, p2 = ref.p1, ref.p2
            if not p1 or not p2:
                return Vector((1, 0))
            sp_id = ref._get_attr_value("start_point_id", "")
            if point_id == sp_id:
                return (p2.co - p1.co).normalized()
            else:
                return (p1.co - p2.co).normalized()

        elif isinstance(ref, (ArcRef, CircleRef)):
            ct = ref.ct
            if not ct:
                return Vector((1, 0))
            point = PointRef(self._sketch, point_id)
            local = point.co - ct.co
            angle = math.atan2(local.y, local.x)

            # Tangent is perpendicular to radius
            sp_id = ref._get_attr_value("start_point_id", "")
            if point_id == sp_id:
                # At start: tangent in arc direction (CCW)
                return Vector((-math.sin(angle), math.cos(angle)))
            else:
                # At end: tangent against arc direction
                return Vector((math.sin(angle), -math.cos(angle)))

        return Vector((1, 0))

    def connection_angle(self, seg_a, seg_b, point_id=None):
        """Signed angle between tangent vectors at shared connection point."""
        if point_id is None:
            pt = self.get_connection_point(seg_a, seg_b)
            if not pt:
                return None
            point_id = pt.curve_id

        d_a = self.direction_at_point(seg_a, point_id)
        d_b = self.direction_at_point(seg_b, point_id)

        if d_a.length == 0 or d_b.length == 0:
            return None

        return d_a.angle_signed(d_b)

    # -----------------------------------------------------------------------
    # Geometric Queries
    # -----------------------------------------------------------------------

    def intersect(self, ref_a, ref_b):
        """All intersection points between two segments."""
        if isinstance(ref_a, LineRef) and isinstance(ref_b, LineRef):
            return self._intersect_line_line(ref_a, ref_b)
        elif isinstance(ref_a, LineRef) and isinstance(ref_b, (ArcRef, CircleRef)):
            return self._intersect_line_curve(ref_a, ref_b)
        elif isinstance(ref_a, (ArcRef, CircleRef)) and isinstance(ref_b, LineRef):
            return self._intersect_line_curve(ref_b, ref_a)
        elif isinstance(ref_a, (ArcRef, CircleRef)) and isinstance(ref_b, (ArcRef, CircleRef)):
            return self._intersect_curve_curve(ref_a, ref_b)
        return []

    def _intersect_line_line(self, a, b):
        from .geometry import intersect_line_line_2d
        p1a, p2a = a.p1.co, a.p2.co
        p1b, p2b = b.p1.co, b.p2.co
        result = intersect_line_line_2d(p1a, p2a, p1b, p2b)
        if result is None or not all(math.isfinite(v) for v in result):
            return []
        return [result]

    def _intersect_line_curve(self, line, curve):
        p1, p2 = line.p1.co, line.p2.co
        center = curve.ct.co
        radius = curve.radius
        results = intersect_line_sphere_2d(p1, p2, center, radius)
        points = [r for r in results if r is not None]
        # Filter by arc range if arc
        if isinstance(curve, ArcRef):
            points = [p for p in points if self.is_inside(curve, p)]
        return points

    def _intersect_curve_curve(self, a, b):
        ca, cb = a.ct.co, b.ct.co
        ra, rb = a.radius, b.radius
        results = intersect_sphere_sphere_2d(ca, ra, cb, rb)
        points = [r for r in results if r is not None]
        # Filter by arc ranges
        if isinstance(a, ArcRef):
            points = [p for p in points if self.is_inside(a, p)]
        if isinstance(b, ArcRef):
            points = [p for p in points if self.is_inside(b, p)]
        return points

    def project_point(self, ref, co):
        """Project a coordinate onto a segment."""
        co = Vector(co[:2])
        if isinstance(ref, LineRef):
            p1, p2 = ref.p1.co, ref.p2.co
            line_vec = p2 - p1
            if line_vec.length == 0:
                return p1.copy()
            t = (co - p1).dot(line_vec) / line_vec.length_squared
            return p1 + line_vec * t

        elif isinstance(ref, (ArcRef, CircleRef)):
            center = ref.ct.co
            diff = co - center
            if diff.length == 0:
                return center + Vector((ref.radius, 0))
            return center + diff.normalized() * ref.radius

        return co.copy()

    def distance_along(self, ref, co1, co2):
        """Arc-length distance between two points on a segment."""
        co1, co2 = Vector(co1[:2]), Vector(co2[:2])
        if isinstance(ref, LineRef):
            return (co2 - co1).length

        elif isinstance(ref, (ArcRef, CircleRef)):
            center = ref.ct.co
            a1 = math.atan2((co1 - center).y, (co1 - center).x)
            a2 = math.atan2((co2 - center).y, (co2 - center).x)
            angle = abs(range_2pi(a2 - a1))
            return angle * ref.radius

        return 0.0

    def normal_at(self, ref, position=None):
        """Normal vector at a position on the segment."""
        if isinstance(ref, LineRef):
            return ref.normal()

        elif isinstance(ref, (ArcRef, CircleRef)):
            if position is None:
                return Vector((0, 1))
            center = ref.ct.co
            diff = Vector(position[:2]) - center
            if diff.length == 0:
                return Vector((1, 0))
            return diff.normalized()

        return Vector((0, 1))

    def is_inside(self, ref, co):
        """Check if a coordinate lies within an arc's angular range."""
        if isinstance(ref, (LineRef, CircleRef)):
            return True
        if not isinstance(ref, ArcRef):
            return False

        ct = ref.ct
        start = ref.start
        end = ref.end
        if not ct or not start or not end:
            return False

        center = ct.co
        s_angle = math.atan2((start.co - center).y, (start.co - center).x)
        e_angle = math.atan2((end.co - center).y, (end.co - center).x)
        p_angle = math.atan2((Vector(co[:2]) - center).y, (Vector(co[:2]) - center).x)

        arc_angle = range_2pi(e_angle - s_angle)
        test_angle = range_2pi(p_angle - s_angle)
        return test_angle <= arc_angle + 1e-6

    # -----------------------------------------------------------------------
    # Path Walking
    # -----------------------------------------------------------------------

    def walk_path(self, start_ref, exclude_construction=True):
        """Walk connected segments in linear order from start_ref.

        Walks in one direction first, then the other, producing a properly
        ordered path suitable for offset/bevel operations.
        """
        if exclude_construction and start_ref.construction:
            return PathResult()

        visited = {start_ref.curve_id}

        def _walk_direction(ref, from_point_id):
            """Walk one direction, returning (segments, directions) in order."""
            segs = []
            dirs = []
            current = ref
            current_from = from_point_id

            while True:
                # Find the exit point (the point we didn't come from)
                pts = _get_point_ids(current)
                exit_pts = [p for p in pts if p != current_from]
                if not exit_pts:
                    break

                exit_pid = exit_pts[0]

                # Find next unvisited segment at exit point
                next_seg = None
                for next_ref, _ in self.get_connected_segments(exit_pid):
                    if next_ref.curve_id in visited:
                        continue
                    if exclude_construction and next_ref.construction:
                        continue
                    next_seg = next_ref
                    break

                if not next_seg:
                    break

                visited.add(next_seg.curve_id)

                # Determine direction: inverted if we enter from the end point
                sp_id = next_seg._get_attr_value("start_point_id", "")
                inverted = (exit_pid != sp_id)
                segs.append(next_seg)
                dirs.append(inverted)

                # Continue from the other end of next_seg
                current = next_seg
                current_from = exit_pid

            return segs, dirs

        # Start segment direction
        sp_id = start_ref._get_attr_value("start_point_id", "")
        ep_id = start_ref._get_attr_value("end_point_id", "")

        # Walk forward (from end point)
        fwd_segs, fwd_dirs = _walk_direction(start_ref, sp_id)

        # Walk backward (from start point)
        bwd_segs, bwd_dirs = _walk_direction(start_ref, ep_id)

        # Combine: backward(reversed) + start + forward
        bwd_segs.reverse()
        bwd_dirs.reverse()
        # Flip backward directions since we reversed the order
        bwd_dirs = [not d for d in bwd_dirs]

        result = PathResult()
        result.segments = bwd_segs + [start_ref] + fwd_segs
        result.directions = bwd_dirs + [False] + fwd_dirs

        return result

    def walk_all_paths(self, exclude_construction=True):
        """Find all connected paths in the sketch."""
        visited = set()
        paths = []

        obj = self._sketch.target_object
        if not obj or not obj.data:
            return paths

        cd = obj.data
        type_attr = cd.attributes.get("sketch_type")
        if not has_uuid_field(cd, "curve_id") or not type_attr:
            return paths

        for i in range(len(cd.curves)):
            ctype = type_attr.data[i].value
            if ctype == SketchCurveType.POINT:
                continue
            cid = get_uuid(cd, "curve_id", i)
            if cid in visited:
                continue

            ref = self._ref(cid)
            if not ref.valid:
                continue
            if exclude_construction and ref.construction:
                continue

            path = self.walk_path(ref, exclude_construction)
            for seg in path.segments:
                visited.add(seg.curve_id)
            if path.segments:
                paths.append(path)

        return paths

    def get_limit_points(self, path):
        """Start and end points of a non-cyclic path. None if cyclic."""
        if path.is_cyclic or not path.segments:
            return None

        first = path.segments[0]
        last = path.segments[-1]

        # Start point: the point of first segment NOT shared with second
        if len(path.segments) > 1:
            shared_start = _get_point_ids(first) & _get_point_ids(path.segments[1])
            first_pts = _get_point_ids(first) - shared_start
            shared_end = _get_point_ids(last) & _get_point_ids(path.segments[-2])
            last_pts = _get_point_ids(last) - shared_end
        else:
            first_pts = _get_point_ids(first)
            last_pts = first_pts

        start = PointRef(self._sketch, next(iter(first_pts))) if first_pts else None
        end = PointRef(self._sketch, next(iter(last_pts))) if last_pts else None
        return (start, end)

    # -----------------------------------------------------------------------
    # Modification
    # -----------------------------------------------------------------------

    def replace_point(self, ref, old_point_id, new_point_id):
        """Update a segment's relationship attribute to reference a new point."""
        for attr_name in ("start_point_id", "end_point_id", "center_point_id"):
            val = ref._get_attr_value(attr_name, "")
            if val == old_point_id:
                ref._set_attr_value(attr_name, new_point_id)

        from .curve_data import rebuild_segments
        rebuild_segments(self._sketch)
        self.invalidate()

    def create_like(self, ref, p1, p2, construction=False):
        """Create a new segment of the same type as ref, with new endpoints.

        For circles, creates an arc using the circle's center point.
        """
        if isinstance(ref, LineRef):
            return LineRef.create(self._sketch, p1, p2, construction=construction)
        elif isinstance(ref, ArcRef):
            return ArcRef.create(self._sketch, ref.ct, p1, p2, construction=construction)
        elif isinstance(ref, CircleRef):
            # Circle trimmed to arc
            return ArcRef.create(self._sketch, ref.ct, p1, p2, construction=construction)
        return None

    def split_segment(self, ref, split_points):
        """Split a segment at the given points, creating new segments.

        Returns list of new CurveRefs (excluding the original).
        The original segment is modified to span only the first sub-segment.
        """
        if not split_points:
            return []

        # Sort split points by distance from segment start
        pts = list(split_points)
        if isinstance(ref, LineRef):
            start_co = ref.p1.co
            pts.sort(key=lambda p: (p.co - start_co).length)
        elif isinstance(ref, ArcRef):
            pts.sort(key=lambda p: self.distance_along(ref, ref.start.co, p.co))

        # Build ordered point list: [start, *splits, end]
        conn = self.connection_points(ref)
        if len(conn) < 2:
            return []

        all_points = [conn[0]] + pts + [conn[1]]

        # Modify original to span first sub-segment
        self.replace_point(ref, conn[1].curve_id, all_points[1].curve_id)

        # Create new segments for remaining spans
        new_refs = []
        for i in range(1, len(all_points) - 1):
            new_ref = self.create_like(ref, all_points[i], all_points[i + 1])
            if new_ref:
                new_refs.append(new_ref)

        self.invalidate()
        return new_refs
