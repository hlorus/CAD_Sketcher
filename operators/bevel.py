import logging
import math

from bpy.props import BoolProperty, FloatProperty
from bpy.types import Operator
from mathutils import Vector

from ..curve_solver import solve_system
from ..declarations import Operators
from ..drawing import selection
from ..model.categories import POINT2D, SEGMENT
from ..model.curve_ref import ArcRef, CircleRef, CurveRef, LineRef, PointRef, curve_ref
from ..stateful_operator.state import state_from_args
from ..stateful_operator.utilities.register import register_stateops_factory
from ..utilities.intersect import ElementTypes, get_intersections
from ..utilities.view import get_pos_2d, refresh
from .base_2d import Operator2d

logger = logging.getLogger(__name__)


def _get_offset_elements(topo, ref, offset):
    """Get offset geometry for intersection."""
    if isinstance(ref, LineRef):
        normal = topo.normal_at(ref)
        offset_vec = normal * offset
        return (ElementTypes.Line, (ref.p1.co + offset_vec, ref.p2.co + offset_vec))
    elif isinstance(ref, (ArcRef, CircleRef)):
        return (ElementTypes.Sphere, (ref.ct.co, ref.radius + offset))
    return None


# Joints closer than this to a straight continuation have no corner to round off.
_SMOOTH_JOINT_TOLERANCE = math.radians(1.0)


def _corner_segments(topo, point_cid):
    """The two segments meeting at a bevelable corner, or None.

    A corner needs exactly two non-construction segments that actually turn:
    at a tangent joint (e.g. a line running into an arc) or between collinear
    lines the directions leaving the point are opposite, so there is nothing
    to bevel.
    """
    segs = [
        ref for ref, _ in topo.get_connected_segments(point_cid) if not ref.construction
    ]
    if len(segs) != 2:
        return None
    angle = topo.connection_angle(segs[0], segs[1], point_cid)
    if angle is None or math.pi - abs(angle) < _SMOOTH_JOINT_TOLERANCE:
        return None
    return segs


def _get_bevel_points(sketch, topo):
    """Collect all eligible bevel points from selection.

    Includes:
    - Directly selected points that are a corner (see _corner_segments)
    - Endpoints of selected segments that are a corner
    """
    candidates = set()

    for cid in selection.selected:
        ref = curve_ref(sketch, cid)
        if not ref.valid:
            continue

        if isinstance(ref, PointRef):
            candidates.add(cid)
        else:
            # Add endpoints of selected segments
            for attr in ("start_point_id", "end_point_id"):
                pt_cid = ref._get_attr_value(attr, 0)
                if pt_cid:
                    candidates.add(pt_cid)

    # Filter: only real corners
    eligible = []
    for pt_cid in candidates:
        if _corner_segments(topo, pt_cid):
            eligible.append(pt_cid)

    return eligible


def _bevel_point(sketch, topo, point_cid, radius):
    """Bevel a single point. Returns (arc, connected, bevel_points, point) or None."""
    point = PointRef(sketch, point_cid)
    if not point.valid:
        return None

    segs = _corner_segments(topo, point_cid)
    if not segs:
        return None

    l1, l2 = segs

    # Find center of bevel arc
    intersections = sorted(
        get_intersections(
            _get_offset_elements(topo, l1, radius),
            _get_offset_elements(topo, l1, -radius),
            _get_offset_elements(topo, l2, radius),
            _get_offset_elements(topo, l2, -radius),
            segment=True,
        ),
        key=lambda i: (i - point.co).length,
    )

    coords = None
    for intr in intersections:
        if not topo.is_inside(l1, intr):
            continue
        if not topo.is_inside(l2, intr):
            continue
        coords = intr
        break

    if not coords:
        return None

    ct = PointRef.create(sketch, coords)

    # Tangent points
    p1_co = topo.project_point(l1, coords)
    p2_co = topo.project_point(l2, coords)
    if p1_co is None or p2_co is None:
        return None

    bp1 = PointRef.create(sketch, p1_co)
    bp2 = PointRef.create(sketch, p2_co)

    # Arc direction
    angle = topo.connection_angle(l1, l2, point_cid)
    invert = angle is not None and angle < 0
    start, end = (bp2, bp1) if invert else (bp1, bp2)

    # Construction while the radius is dragged: the corner lines are only trimmed
    # in fini(), so a solid arc would overlap them and break the fill preview.
    arc = ArcRef.create(sketch, ct, start, end, construction=True)
    if not arc:
        return None

    return {
        "arc": arc,
        "connected": (l1, l2),
        "bevel_points": (bp1, bp2),
        "point": point,
    }


def _max_radius(sketch, topo, point_ids):
    """Largest radius every line/line corner in ``point_ids`` can take, or None.

    At a corner of interior angle ``a`` the tangent points sit ``r / tan(a / 2)``
    from the corner, so ``r`` is capped by the shorter line. A line beveled at
    both ends shares its length between the two (equal radii). Corners touching
    an arc are not capped.
    """
    corners = set(point_ids)
    best = None
    for pt_cid in point_ids:
        point = PointRef(sketch, pt_cid)
        segs = _corner_segments(topo, pt_cid)
        if not segs or not all(isinstance(ref, LineRef) for ref in segs):
            continue
        dirs, avail = [], []
        for line in segs:
            other = line.p2 if line.p1.curve_id == pt_cid else line.p1
            vec = other.co - point.co
            dirs.append(vec)
            share = 2.0 if other.curve_id in corners else 1.0
            avail.append(vec.length / share)
        if min(v.length for v in dirs) == 0.0:
            continue
        angle = dirs[0].angle(dirs[1])
        if angle <= 1e-6 or angle >= math.pi - 1e-6:
            continue
        limit = min(avail) * math.tan(angle / 2)
        best = limit if best is None else min(best, limit)
    return best


class View3D_OT_slvs_bevel(Operator, Operator2d):
    """Add a tangential arc between the two segments of selected points"""

    bl_idname = Operators.Bevel
    bl_label = "Sketch Bevel"
    bl_options = {"REGISTER", "UNDO"}

    radius: FloatProperty(name="Radius", subtype="DISTANCE", unit="LENGTH")
    dimension_radius: BoolProperty(
        name="Dimension Radius",
        description="Add a radius dimension to the bevel (on when the radius is typed)",
    )

    states = (
        state_from_args(
            "Point",
            description="Point to bevel",
            pointer="p1",
            types=(*POINT2D, *SEGMENT),
            # Bevel only acts on existing corners: a click on empty space must
            # never place a new point there.
            use_create=False,
            # Selected corners are enough to bevel; main() gathers them.
            optional=True,
        ),
        state_from_args(
            "Radius",
            description="Radius of the bevel",
            property="radius",
            interactive=True,
        ),
    )

    def _has_selected_corners(self) -> bool:
        """Whether the selection alone gives points to bevel (cached per run)."""
        cached = getattr(self, "_selected_corners", None)
        if cached is None:
            sketch = self.sketch
            cached = bool(sketch and _get_bevel_points(sketch, sketch.topology))
            self._selected_corners = cached
        return cached

    def evaluate_state(self, context, event, triggered):
        # With corners already selected, a click that hits nothing starts the
        # radius drag. The base would cancel it for lack of a picked target (an
        # optional state can't help: it only skips once the radius is set too).
        if triggered and self.state_index == 0 and self._has_selected_corners():
            coords = Vector((event.mouse_region_x, event.mouse_region_y))
            if self.pick_element(context, coords) is None:
                self.next_state(context)
                return {"RUNNING_MODAL"}
        # A typed radius is a deliberate value, so keep it as a dimension; a free
        # drag is not.
        if self.state_index == 1 and self._numeric.is_active:
            self.dimension_radius = True
        return super().evaluate_state(context, event, triggered)

    def state_func(self, context, coords):
        # The radius follows the cursor's distance to the nearest beveled corner,
        # not the base's horizontal screen delta.
        if self.state.property != "radius":
            return super().state_func(context, coords)
        sketch = self.sketch
        corners = self._corner_ids(sketch, sketch.topology)
        if not corners:
            return super().state_func(context, coords)
        pos = get_pos_2d(context, self._get_wp(), coords)
        return min((pos - PointRef(sketch, cid).co).length for cid in corners)

    def main(self, context):
        sketch = self.sketch
        topo = sketch.topology
        points = self._corner_ids(sketch, topo)

        if not points:
            self.report({"WARNING"}, "No valid points to bevel")
            return False

        # A radius that doesn't fit would make the corner fail silently; use the
        # biggest one that still leaves every trimmed line a length.
        limit = _max_radius(sketch, topo, points)
        if limit is not None and self.radius > limit:
            self.radius = limit * (1.0 - 1e-4)
        radius = self.radius

        # Bevel each point
        self._results = []
        for pt_cid in points:
            result = _bevel_point(sketch, topo, pt_cid, radius)
            if result:
                self._results.append(result)

        if not self._results:
            return False

        refresh(context)
        return True

    def _corner_ids(self, sketch, topo) -> list:
        """Corner point ids to bevel: the selection plus the picked element."""
        points = _get_bevel_points(sketch, topo)

        # Also include the directly picked element
        picked = self.p1
        if picked and isinstance(picked, CurveRef):
            if isinstance(picked, PointRef):
                # Picked a point directly
                if picked.curve_id not in points:
                    if _corner_segments(topo, picked.curve_id):
                        points.append(picked.curve_id)
            else:
                # Picked a segment — add its endpoints
                for attr in ("start_point_id", "end_point_id"):
                    pt_cid = picked._get_attr_value(attr, 0)
                    if pt_cid and pt_cid not in points:
                        if _corner_segments(topo, pt_cid):
                            points.append(pt_cid)
        return points

    def fini(self, context, succeede):
        if not succeede:
            return

        sketch = self.sketch
        sc = sketch.constraints

        for result in self._results:
            topo = sketch.topology  # Rebuild after each modification
            arc = result["arc"]
            l1, l2 = result["connected"]
            bp1, bp2 = result["bevel_points"]
            point = result["point"]

            arc.construction = False

            # Replace endpoints
            topo.replace_point(l1, point.curve_id, bp1.curve_id)
            topo.replace_point(l2, point.curve_id, bp2.curve_id)

            # Add tangent constraints
            sc.add_tangent(curve_id_1=arc.curve_id, curve_id_2=l1.curve_id)
            sc.add_tangent(curve_id_1=arc.curve_id, curve_id_2=l2.curve_id)

            # Keep the corner as a construction "virtual sharp" held on both
            # segments, so constraints and dimensions that used it stay valid.
            point.construction = True
            sc.add_coincident(curve_id_1=point.curve_id, curve_id_2=l1.curve_id)
            sc.add_coincident(curve_id_1=point.curve_id, curve_id_2=l2.curve_id)

        # Add equal constraints between all arcs
        arcs = [r["arc"] for r in self._results if r["arc"]]
        if len(arcs) > 1:
            first = arcs[0]
            for arc in arcs[1:]:
                sc.add_equal(curve_id_1=first.curve_id, curve_id_2=arc.curve_id)

        # The equal constraints carry the radius to every other arc.
        if arcs and self.dimension_radius:
            sc.add_diameter(
                init=True,
                curve_id_1=arcs[0].curve_id,
                setting=True,
                value=self.radius,
            )

        refresh(context)
        sketch.geometry_solved = False
        solve_system(context, sketch)


register, unregister = register_stateops_factory((View3D_OT_slvs_bevel,))
