"""Trimming logic for splitting segments at intersection points."""

import logging

from mathutils import Vector

from ..model.curve_ref import ArcRef, CircleRef, LineRef, PointRef
from .curve_data import get_uuid, has_uuid_field

logger = logging.getLogger(__name__)

# Two trim points closer than this (sketch units) are treated as the same
# location, so a piece bounded by them is a fully-trimmed (degenerate) segment.
COINCIDENT_EPS = 1e-4


def _points_coincident(p1, p2) -> bool:
    if p1 is None or p2 is None:
        return True
    if getattr(p1, "curve_id", None) and p1.curve_id == getattr(p2, "curve_id", None):
        return True
    return (Vector(p1.co) - Vector(p2.co)).length < COINCIDENT_EPS


class Intersection:
    """An intersection point on the segment being trimmed."""

    def __init__(
        self,
        co,
        source_cid="",
        is_endpoint=False,
        constraint_index=-1,
        constraint_type="",
    ):
        self.co = Vector(co[:2])
        self.source_cid = source_cid  # curve_id of intersecting segment (0 if endpoint)
        self.is_endpoint = is_endpoint
        self.constraint_index = constraint_index
        self.constraint_type = constraint_type
        self.index = -1
        self._point_ref = None

    def get_or_create_point(self, sketch):
        """Get existing point or create one at this intersection."""
        if self._point_ref:
            return self._point_ref
        self._point_ref = PointRef.create(sketch, self.co)
        return self._point_ref

    def __str__(self):
        return (
            f"Intersection(idx={self.index}, co={self.co}, endpoint={self.is_endpoint})"
        )


class TrimSegment:
    """Manages trimming a segment at intersection points."""

    def __init__(self, sketch, segment_ref, mouse_pos, topo):
        self.sketch = sketch
        self.segment = segment_ref
        self.pos = Vector(mouse_pos[:2])
        self.topo = topo
        self._intersections = []
        self._is_closed = isinstance(segment_ref, CircleRef)
        self.obsolete_intersections = []
        self._original_endpoint_cids = set()

        # Add connection points as endpoint intersections
        if not self._is_closed:
            conn_pts = topo.connection_points(segment_ref)
            for pt in conn_pts:
                self._original_endpoint_cids.add(pt.curve_id)
                intr = Intersection(pt.co, is_endpoint=True)
                intr._point_ref = pt
                self._intersections.append(intr)

    def add(self, co, source_cid="", constraint_index=-1, constraint_type=""):
        """Add an intersection point."""
        intr = Intersection(
            co,
            source_cid,
            constraint_index=constraint_index,
            constraint_type=constraint_type,
        )
        self._intersections.append(intr)
        return intr

    def check(self):
        """Validate that trimming is possible."""
        relevant = self._relevant_intersections()
        return len(relevant) in (2, 4)

    def _parametric_t(self, co):
        """Get parametric position (0-1) of a point along the segment."""
        import math

        seg = self.segment
        if isinstance(seg, LineRef):
            p1, p2 = seg.p1.co, seg.p2.co
            line_vec = p2 - p1
            if line_vec.length == 0:
                return 0.0
            return (Vector(co[:2]) - p1).dot(line_vec) / line_vec.length_squared
        elif isinstance(seg, (ArcRef, CircleRef)):
            from ..utilities.math import range_2pi

            center = seg.ct.co
            if isinstance(seg, ArcRef) and seg.start:
                start_co = seg.start.co
            else:
                start_co = Vector(
                    self.topo._sketch.target_object.data.points[
                        self.topo._sketch.target_object.data.curves[0].points[0].index
                    ].position[:2]
                )
            s_angle = math.atan2((start_co - center).y, (start_co - center).x)
            p_angle = math.atan2(
                (Vector(co[:2]) - center).y, (Vector(co[:2]) - center).x
            )
            total = seg.angle if isinstance(seg, ArcRef) else math.tau
            if total == 0:
                return 0.0
            return range_2pi(p_angle - s_angle) / total
        return 0.0

    def _relevant_intersections(self):
        """Get the intersections that bound the trimmed region.

        Finds the two intersections immediately on either side of the mouse
        position along the segment. The part between them (containing the mouse)
        is the trim region to remove.
        """
        if len(self._intersections) < 2:
            return []

        # Compute parametric position for each intersection and the mouse
        mouse_t = self._parametric_t(self.pos)
        for intr in self._intersections:
            intr._t = self._parametric_t(intr.co)

        # Sort by parametric position
        ordered = sorted(self._intersections, key=lambda intr: intr._t)
        for i, intr in enumerate(ordered):
            intr.index = i

        # Find the two intersections surrounding the mouse
        lower = None  # highest t below mouse
        upper = None  # lowest t above mouse
        for intr in ordered:
            if intr._t <= mouse_t:
                lower = intr
            if intr._t >= mouse_t and upper is None:
                upper = intr

        # Handle wrap-around for closed segments
        if self._is_closed:
            if lower is None:
                lower = ordered[-1]
            if upper is None:
                upper = ordered[0]

        if lower is None or upper is None:
            return []
        if lower == upper and len(ordered) > 1:
            # Mouse exactly on an intersection — pick neighbors
            idx = ordered.index(lower)
            lower = ordered[idx - 1] if idx > 0 else ordered[-1]

        # The trim region is between lower and upper (this gets removed)
        # The KEPT segments are: [start..lower] and [upper..end]
        # Mark lower and upper as the trim boundaries
        trim_indices = {lower.index, upper.index}

        relevant = []
        for intr in ordered:
            if intr.index in trim_indices:
                # This is a trim boundary — kept
                if intr.is_endpoint:
                    # Endpoint at trim boundary — will be deleted
                    if intr not in self.obsolete_intersections:
                        self.obsolete_intersections.append(intr)
                    continue
                if intr.constraint_index >= 0:
                    if intr not in self.obsolete_intersections:
                        self.obsolete_intersections.append(intr)
                relevant.append(intr)
            else:
                # Not a trim boundary
                if not intr.is_endpoint:
                    continue
                # Endpoint outside trim region — kept as part of remaining segment
                relevant.append(intr)

        return relevant

    def _cleanup_orphan_points(self, sketch):
        """Remove endpoints of the original segment that are no longer referenced."""
        from ..model.constants import SketchCurveType
        from ..utilities.curve_data import remove_native_curve_by_id

        # Check all original endpoints of the trimmed segment
        candidates = set(self._original_endpoint_cids)

        if not candidates:
            return

        cd = sketch.data
        if not cd:
            return

        n = len(cd.curves)
        type_attr = cd.attributes.get("sketch_type")
        if not has_uuid_field(cd, "curve_id") or not type_attr:
            return

        # Check which candidates are still referenced by any segment
        referenced = set()
        for i in range(n):
            ctype = type_attr.data[i].value
            if ctype == SketchCurveType.POINT:
                continue
            referenced.add(get_uuid(cd, "start_point_id", i))
            referenced.add(get_uuid(cd, "end_point_id", i))
            referenced.add(get_uuid(cd, "center_point_id", i))

        orphan_cids = {cid for cid in candidates if cid not in referenced}
        if not orphan_cids:
            return

        sc = sketch.constraints
        for data_coll in sc.get_lists():
            to_remove = []
            for j, c in enumerate(data_coll):
                if (
                    getattr(c, "curve_id_1", "") in orphan_cids
                    or getattr(c, "curve_id_2", "") in orphan_cids
                ):
                    to_remove.append(j)
            for j in reversed(to_remove):
                data_coll.remove(j)

        for cid in orphan_cids:
            remove_native_curve_by_id(sketch, cid)

    def execute(self, context):
        """Perform the trim operation."""
        relevant = self._relevant_intersections()
        if not relevant:
            return

        sketch = self.sketch
        topo = self.topo

        # Ensure all intersection points exist
        for intr in relevant:
            intr.get_or_create_point(sketch)

        # Create new segments between pairs of relevant intersections
        segment_count = len(relevant) // 2
        new_segments = []
        reused = False

        for i in range(segment_count):
            intr_1 = relevant[i * 2]
            intr_2 = relevant[i * 2 + 1]
            p1 = intr_1.get_or_create_point(sketch)
            p2 = intr_2.get_or_create_point(sketch)

            # A piece whose two boundaries collapse onto the same location is
            # fully trimmed away -- creating a segment there yields a zero-length
            # line or a zero-sweep arc (whose bezier degenerates into a stray
            # sliver). Skip it; its now-orphan points are cleaned up below.
            if _points_coincident(p1, p2):
                continue

            if i == 0 and not self._is_closed:
                # Reuse original segment for first piece
                conn = topo.connection_points(self.segment)
                if len(conn) >= 2:
                    topo.replace_point(self.segment, conn[0].curve_id, p1.curve_id)
                    topo.replace_point(self.segment, conn[1].curve_id, p2.curve_id)
                    reused = True
                    new_segments.append(self.segment)
                    continue

            if self._is_closed:
                # For circles: create arc on the OPPOSITE side of the mouse
                # Swap p1/p2 so the arc goes the long way around (away from mouse)
                new_seg = topo.create_like(self.segment, p2, p1)
            else:
                new_seg = topo.create_like(self.segment, p1, p2)
            if new_seg:
                new_segments.append(new_seg)

        # Remove obsolete constraints at trim cut boundaries
        sc = sketch.constraints
        for intr in self.obsolete_intersections:
            if intr.constraint_index >= 0 and intr.constraint_type:
                try:
                    coll = sc.get_list(intr.constraint_type)
                    if intr.constraint_index < len(coll):
                        coll.remove(intr.constraint_index)
                except Exception:
                    pass

        orig_cid = self.segment.curve_id
        retained_seg = new_segments[0] if new_segments else None
        new_cid = retained_seg.curve_id if retained_seg else None

        if retained_seg is not None:
            # 1. Orientation constraints on primary segment (H/V, parallel, perpendicular, tangent, angle)
            if not reused:
                for name in (
                    "horizontal",
                    "vertical",
                    "parallel",
                    "perpendicular",
                    "tangent",
                    "angle",
                ):
                    coll = getattr(sc, name, None)
                    if coll:
                        for c in coll:
                            if getattr(c, "curve_id_1", "") == orig_cid:
                                c.curve_id_1 = new_cid
                            if getattr(c, "curve_id_2", "") == orig_cid:
                                c.curve_id_2 = new_cid

                # 2. Diameter constraints (circle trimmed to arc retains its radius)
                diam_coll = getattr(sc, "diameter", None)
                if diam_coll:
                    for c in diam_coll:
                        if getattr(c, "curve_id_1", "") == orig_cid:
                            c.curve_id_1 = new_cid

            # Constrain additional surviving sub-segments generically:
            # - Line sub-segments end up collinear with the primary segment (parallel + point-on-line)
            # - Arc/circle sub-segments end up concentric & equal radius with the primary segment
            is_line = (
                isinstance(self.segment, LineRef)
                or getattr(self.segment, "is_line", lambda: False)()
            )
            is_curved = (
                isinstance(self.segment, (ArcRef, CircleRef))
                or getattr(self.segment, "is_arc", lambda: False)()
                or getattr(self.segment, "is_circle", lambda: False)()
            )
            for extra_seg in new_segments[1:]:
                extra_cid = extra_seg.curve_id
                if is_line:
                    sc.add_parallel(curve_id_1=extra_cid, curve_id_2=new_cid)
                    p = getattr(extra_seg, "p1", None)
                    if p and getattr(p, "curve_id", ""):
                        sc.add_coincident(curve_id_1=p.curve_id, curve_id_2=new_cid)
                elif is_curved:
                    sc.add_equal(curve_id_1=extra_cid, curve_id_2=new_cid)
                    extra_ct = getattr(extra_seg, "ct", None)
                    retained_ct = getattr(retained_seg, "ct", None)
                    if (
                        extra_ct
                        and retained_ct
                        and getattr(extra_ct, "curve_id", "")
                        and getattr(retained_ct, "curve_id", "")
                        and extra_ct.curve_id != retained_ct.curve_id
                    ):
                        sc.add_coincident(
                            curve_id_1=extra_ct.curve_id,
                            curve_id_2=retained_ct.curve_id,
                        )

            # 3. Distance / length constraints (both reused and newly created segments)
            dist_coll = getattr(sc, "distance", None)
            if dist_coll:
                for c in dist_coll:
                    c1 = getattr(c, "curve_id_1", "")
                    c2 = getattr(c, "curve_id_2", "")

                    # Line length constraint (single entity dimension on the trimmed segment)
                    if c1 == orig_cid and not c2:
                        if not reused:
                            c.curve_id_1 = new_cid
                        try:
                            c.assign_init_props()
                        except Exception:
                            pass
                    elif c2 == orig_cid and not c1:
                        if not reused:
                            c.curve_id_2 = new_cid
                        try:
                            c.assign_init_props()
                        except Exception:
                            pass

                    # Point-to-line distance constraint (external point to trimmed line)
                    elif (
                        c2 == orig_cid
                        and c1
                        and c1 != orig_cid
                        and c1 not in self._original_endpoint_cids
                    ):
                        if not reused:
                            c.curve_id_2 = new_cid
                    elif (
                        c1 == orig_cid
                        and c2
                        and c2 != orig_cid
                        and c2 not in self._original_endpoint_cids
                    ):
                        if not reused:
                            c.curve_id_1 = new_cid

                    # Distance between original endpoints of trimmed segment
                    elif (
                        c1 in self._original_endpoint_cids
                        and c2 in self._original_endpoint_cids
                    ):
                        new_conn = topo.connection_points(retained_seg)
                        if len(new_conn) >= 2:
                            c.curve_id_1 = new_conn[0].curve_id
                            c.curve_id_2 = new_conn[1].curve_id
                            try:
                                c.assign_init_props()
                            except Exception:
                                pass

        if not reused:
            # Remove any remaining constraints referencing original segment that were not transferred
            for data_coll in sc.get_lists():
                to_remove = []
                for j, c in enumerate(data_coll):
                    if (
                        getattr(c, "curve_id_1", "") == orig_cid
                        or getattr(c, "curve_id_2", "") == orig_cid
                    ):
                        to_remove.append(j)
                for j in reversed(to_remove):
                    data_coll.remove(j)

            self.segment.remove()
        else:
            # Reused segment: length changed, so drop length-equality constraints that are now invalid
            for name in ("equal", "ratio", "symmetry"):
                coll = getattr(sc, name, None)
                if coll:
                    to_remove = []
                    for j, c in enumerate(coll):
                        if (
                            getattr(c, "curve_id_1", "") == orig_cid
                            or getattr(c, "curve_id_2", "") == orig_cid
                        ):
                            to_remove.append(j)
                    for j in reversed(to_remove):
                        coll.remove(j)

        # Add coincident constraints between new points and intersecting segments
        for intr in relevant:
            if intr.is_endpoint or not intr.source_cid:
                continue
            pt = intr.get_or_create_point(sketch)
            if pt:
                sc.add_coincident(
                    curve_id_1=pt.curve_id,
                    curve_id_2=intr.source_cid,
                )

        # Remove orphan points (endpoints of removed piece with no segments left)
        self._cleanup_orphan_points(sketch)
