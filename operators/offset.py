import logging
import math

from bpy.types import Operator, Context
from bpy.props import FloatProperty
from mathutils import Vector

from ..model.curve_ref import CurveRef, PointRef, LineRef, ArcRef, CircleRef
from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from ..stateful_operator.state import state_from_args
from ..utilities.view import refresh
from ..utilities.intersect import get_intersections, ElementTypes
from .base_2d import Operator2d
from .utilities import ignore_hover

logger = logging.getLogger(__name__)


def _get_offset_co(point_co, normal, distance):
    return Vector(point_co[:2]) + normal * distance


def _bool_to_signed_int(invert):
    return -1 if invert else 1


def _inverted_dist(invert, distance):
    sign = _bool_to_signed_int(invert) * _bool_to_signed_int(distance < 0)
    return math.copysign(distance, sign)


def _get_offset_elements(topo, ref, offset):
    """Get offset geometry description for intersection calculations."""
    if isinstance(ref, LineRef):
        normal = topo.normal_at(ref)
        offset_vec = normal * offset
        return (ElementTypes.Line, (ref.p1.co + offset_vec, ref.p2.co + offset_vec))
    elif isinstance(ref, (ArcRef, CircleRef)):
        return (ElementTypes.Sphere, (ref.ct.co, ref.radius + offset))
    return None


# State types: accept any segment CurveRef or legacy entity type
from ..model.categories import SEGMENT
_segment_types = SEGMENT


class View3D_OT_slvs_add_offset(Operator, Operator2d):
    """Copy and offset selected entities along with their constraints by the distance value"""

    bl_idname = Operators.Offset
    bl_label = "Offset"
    bl_options = {"REGISTER", "UNDO"}

    distance: FloatProperty(name="Distance")

    states = (
        state_from_args(
            "Entity",
            description="Base entity to get path from",
            pointer="entity",
            use_create=False,
            types=_segment_types,
        ),
        state_from_args(
            "Distance",
            description="Distance to offset the created entities",
            property="distance",
            interactive=True,
        ),
    )

    def main(self, context: Context):
        sketch = self.sketch
        entity = self.entity
        distance = self.distance

        if not entity or not isinstance(entity, CurveRef):
            return False

        ignore_hover(entity.curve_id)

        # Circle: just create a new circle with adjusted radius
        if isinstance(entity, CircleRef):
            new_ct = entity.ct
            new_circle = CircleRef.create(sketch, new_ct, entity.radius + distance)
            if new_circle:
                ignore_hover(new_circle.curve_id)
            refresh(context)
            return True

        # Build topology and walk path
        topo = sketch.topology
        path = topo.walk_path(entity)

        if not path.segments:
            return False

        segments = path.segments
        directions = path.directions
        is_cyclic = path.is_cyclic

        # Get intersections and create points
        intersection_count = len(segments) if is_cyclic else len(segments) - 1
        point_coords = []

        for i in range(intersection_count):
            seg = segments[i]
            seg_dir = directions[i]
            neighbour_i = (i + 1) % len(segments)
            neighbour = segments[neighbour_i]
            neighbour_dir = directions[neighbour_i]

            conn_pt = topo.get_connection_point(seg, neighbour)
            if not conn_pt:
                return False

            offset_a = _get_offset_elements(topo, seg, _inverted_dist(seg_dir, distance))
            offset_b = _get_offset_elements(topo, neighbour, _inverted_dist(neighbour_dir, distance))

            if not offset_a or not offset_b:
                return False

            intersections = sorted(
                get_intersections(offset_a, offset_b),
                key=lambda pt: (pt - conn_pt.co).length,
            )

            if not intersections:
                return False

            point_coords.append(intersections[0])

        # Create points
        points = [PointRef.create(sketch, co) for co in point_coords]

        # Add start/endpoint if not cyclic
        if not is_cyclic:
            limits = topo.get_limit_points(path)
            if limits:
                start_pt, end_pt = limits
                start_co = _get_offset_co(
                    start_pt.co,
                    topo.normal_at(segments[0], start_pt.co),
                    _inverted_dist(directions[0], distance),
                )
                end_co = _get_offset_co(
                    end_pt.co,
                    topo.normal_at(segments[-1], end_pt.co),
                    _inverted_dist(directions[-1], distance),
                )
                points.insert(0, PointRef.create(sketch, start_co))
                points.append(PointRef.create(sketch, end_co))

        for p in points:
            ignore_hover(p.curve_id)

        # Create segments
        use_construction = context.scene.sketcher.use_construction
        self._new_path = []
        for i, seg in enumerate(segments):
            i_start = (i - 1 if is_cyclic else i) % len(segments)
            i_end = (i_start + 1) % len(points)
            p1 = points[i_start]
            p2 = points[i_end]

            new_seg = topo.create_like(seg, p1, p2, construction=use_construction)
            if new_seg:
                ignore_hover(new_seg.curve_id)
                self._new_path.append(new_seg)

        refresh(context)
        return True

    def fini(self, context: Context, succeede: bool):
        pass


register, unregister = register_stateops_factory((View3D_OT_slvs_add_offset,))
