import logging

from bpy.types import Operator, Context
from bpy.props import FloatProperty
from mathutils import Vector

from .. import global_data
from ..model.curve_ref import PointRef, LineRef, ArcRef, CircleRef, CurveRef, curve_ref
from ..utilities.view import refresh
from ..curve_solver import solve_system
from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from ..stateful_operator.state import state_from_args
from ..utilities.intersect import get_intersections, ElementTypes
from .base_2d import Operator2d
from ..model.categories import POINT2D, SEGMENT

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


def _get_bevel_points(sketch, topo):
    """Collect all eligible bevel points from selection.

    Includes:
    - Directly selected points with exactly 2 connected non-construction segments
    - Endpoints of selected segments with exactly 2 connected non-construction segments
    """
    candidates = set()

    for cid in global_data.selected:
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

    # Filter: must have exactly 2 connected non-construction segments
    eligible = []
    for pt_cid in candidates:
        connected = topo.get_connected_segments(pt_cid)
        segs = [ref for ref, _ in connected if not ref.construction]
        if len(segs) == 2:
            eligible.append(pt_cid)

    return eligible


def _bevel_point(sketch, topo, point_cid, radius):
    """Bevel a single point. Returns (arc, connected, bevel_points, point) or None."""
    point = PointRef(sketch, point_cid)
    if not point.valid:
        return None

    connected = topo.get_connected_segments(point_cid)
    segs = [(ref, end) for ref, end in connected if not ref.construction]
    if len(segs) != 2:
        return None

    l1, l2 = segs[0][0], segs[1][0]

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

    arc = ArcRef.create(sketch, ct, start, end)
    if not arc:
        return None

    return {
        "arc": arc,
        "connected": (l1, l2),
        "bevel_points": (bp1, bp2),
        "point": point,
    }


class View3D_OT_slvs_bevel(Operator, Operator2d):
    """Add a tangential arc between the two segments of selected points"""

    bl_idname = Operators.Bevel
    bl_label = "Sketch Bevel"
    bl_options = {"REGISTER", "UNDO"}

    radius: FloatProperty(name="Radius")

    states = (
        state_from_args(
            "Point",
            description="Point to bevel",
            pointer="p1",
            types=(*POINT2D, *SEGMENT),
        ),
        state_from_args(
            "Radius",
            description="Radius of the bevel",
            property="radius",
            interactive=True,
        ),
    )

    def main(self, context):
        sketch = self.sketch
        radius = self.radius
        topo = sketch.topology

        # Collect eligible points from selection + picked element
        points = _get_bevel_points(sketch, topo)

        # Also include the directly picked element
        picked = self.p1
        if picked and isinstance(picked, CurveRef):
            if isinstance(picked, PointRef):
                # Picked a point directly
                if picked.curve_id not in points:
                    connected = topo.get_connected_segments(picked.curve_id)
                    segs = [ref for ref, _ in connected if not ref.construction]
                    if len(segs) == 2:
                        points.append(picked.curve_id)
            else:
                # Picked a segment — add its endpoints
                for attr in ("start_point_id", "end_point_id"):
                    pt_cid = picked._get_attr_value(attr, 0)
                    if pt_cid and pt_cid not in points:
                        connected = topo.get_connected_segments(pt_cid)
                        segs = [ref for ref, _ in connected if not ref.construction]
                        if len(segs) == 2:
                            points.append(pt_cid)

        if not points:
            self.report({"WARNING"}, "No eligible points to bevel")
            return False

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

            # Replace endpoints
            topo.replace_point(l1, point.curve_id, bp1.curve_id)
            topo.replace_point(l2, point.curve_id, bp2.curve_id)

            # Add tangent constraints
            sc.add_tangent(curve_id_1=arc.curve_id, curve_id_2=l1.curve_id)
            sc.add_tangent(curve_id_1=arc.curve_id, curve_id_2=l2.curve_id)

            # Remove original point
            point.remove()

        # Add equal constraints between all arcs
        arcs = [r["arc"] for r in self._results if r["arc"]]
        if len(arcs) > 1:
            first = arcs[0]
            for arc in arcs[1:]:
                sc.add_equal(curve_id_1=first.curve_id, curve_id_2=arc.curve_id)

        refresh(context)
        sketch.geometry_solved = False
        solve_system(context, sketch)


register, unregister = register_stateops_factory((View3D_OT_slvs_bevel,))
