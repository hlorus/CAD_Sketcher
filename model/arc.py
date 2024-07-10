import logging
from typing import List

import bpy
from bpy.types import PropertyGroup, Context
from bpy.props import BoolProperty
from gpu_extras.batch import batch_for_shader
import math
from mathutils import Vector, Matrix
from mathutils.geometry import intersect_line_sphere_2d, intersect_sphere_sphere_2d
from bpy.utils import register_classes_factory

from ..solver import Solver
from .base_entity import SlvsGenericEntity
from .base_entity import Entity2D
from .utilities import slvs_entity_pointer, tag_update
from .constants import CURVE_RESOLUTION
from ..utilities.constants import HALF_TURN, FULL_TURN, QUARTER_TURN
from ..utilities.math import range_2pi, pol2cart
from ..utilities.draw import coords_arc_2d
from .utilities import (
    get_connection_point,
    get_bezier_curve_midpoint_positions,
    create_bezier_curve,
    round_v,
)
from ..utilities.math import range_2pi, pol2cart

logger = logging.getLogger(__name__)


def _get_angle(start, end):
    return range_2pi(math.atan2(end[1], end[0]) - math.atan2(start[1], start[0]))


class SlvsArc(Entity2D, PropertyGroup):
    """Representation of an arc in 2D space around the centerpoint ct. Connects
    p2 to p3 or (vice-versa if the option invert_direction is true) with a
    circle segment that is resolution independent. The arc lies on the sketche's workplane.

    Arguments:
        p1 (SlvsPoint2D): Arc's centerpoint
        p2 (SlvsPoint2D): Arc's startpoint
        p2 (SlvsPoint2D): Arc's endpoint
        nm (SlvsNormal3D): Orientation
        sketch (SlvsSketch): The sketch this entity belongs to
    """

    invert_direction: BoolProperty(
        name="Invert direction",
        description="Connect the points in the inverted order",
        update=tag_update,
    )

    @classmethod
    def is_path(cls):
        return True

    @classmethod
    def is_curve(cls):
        return True

    @classmethod
    def is_segment(cls):
        return True

    @property
    def start(self):
        return self.p2 if self.invert_direction else self.p1

    @property
    def end(self):
        return self.p1 if self.invert_direction else self.p2

    def dependencies(self) -> List[SlvsGenericEntity]:
        return [self.nm, self.ct, self.start, self.end, self.sketch]

    def is_dashed(self):
        return self.construction

    def update(self):
        if bpy.app.background:
            return

        ct = self.ct.co
        p1 = self.start.co - ct
        p2 = self.end.co - ct

        radius = p1.length

        coords = []
        if radius and p2.length:
            offset = p1.angle_signed(Vector((1, 0)))
            angle = range_2pi(p2.angle_signed(p1))

            # TODO: resolution should depend on segment length?!
            segments = round(CURVE_RESOLUTION * (angle / FULL_TURN))

            coords = coords_arc_2d(0, 0, radius, segments, angle=angle, offset=offset)

            mat_local = Matrix.Translation(self.ct.co.to_3d())
            mat = self.wp.matrix_basis @ mat_local
            coords = [(mat @ Vector((*co, 0)))[:] for co in coords]

        kwargs = {"pos": coords}
        self._batch = batch_for_shader(self._shader, "LINE_STRIP", kwargs)
        self.is_dirty = False

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        handle = solvesys.addArcOfCircle(
            self.wp.py_data,
            self.ct.py_data,
            self.start.py_data,
            self.end.py_data,
            group=group,
        )
        self.py_data = handle

    @property
    def radius(self):
        return (self.ct.co - self.start.co).length

    @property
    def angle(self):
        """Returns an angle in radians from zero to 2*PI"""
        center = self.ct.co
        start, end = self.start.co - center, self.end.co - center
        return _get_angle(start, end)

    @property
    def start_angle(self):
        center, start = self.ct.co, self.start.co
        return math.atan2((start - center)[1], (start - center)[0])

    def normal(self, position: Vector = None):
        """Return the normal vector at a given position"""

        normal = position - self.ct.co
        return normal.normalized()

    def placement(self):
        coords = self.ct.co + pol2cart(self.radius, self.start_angle + self.angle / 2)

        return self.wp.matrix_basis @ coords.to_3d()

    def connection_points(self, direction: bool = False):
        points = [self.start, self.end]
        if direction:
            return list(reversed(points))
        return points

    def direction(self, point, is_endpoint=False):
        """Returns the direction of the arc, true if inverted"""
        if is_endpoint:
            return point == self.start
        return point == self.end

    @staticmethod
    def _direction(start, end, center):
        pass

    def bezier_segment_count(self):
        max_angle = QUARTER_TURN
        return math.ceil(self.angle / max_angle)

    def bezier_point_count(self):
        return self.bezier_segment_count() + 1

    def point_on_curve(self, angle, relative=True):
        start_angle = self.start_angle if relative else 0
        return pol2cart(self.radius, start_angle + angle) + self.ct.co

    def project_point(self, coords):
        """Projects a point onto the arc"""
        local_co = coords - self.ct.co
        angle = range_2pi(math.atan2(local_co[1], local_co[0]))
        return self.point_on_curve(angle, relative=False)

    def connection_angle(self, other, connection_point=None, **kwargs):
        """Returns the angle at the connection point between the two entities
        or None if they're either not connected or not in 2d space

        You may use `connection_point` in order to remove ambiguity in case
        multiple intersections point exist with other entity.

        `kwargs` key values are propagated to other `get_connection_point` functions
        """

        point = connection_point or get_connection_point(self, other)

        if not point:
            return None
        if self.is_3d() or other.is_3d():
            return None

        def _get_tangent(arc, point):
            local_co = point.co - arc.ct.co
            angle = range_2pi(math.atan2(local_co.y, local_co.x))
            mat_rot = Matrix.Rotation(angle, 2, "Z")
            tangent = Vector((0, 1))
            tangent.rotate(mat_rot)
            invert = arc.direction(point)
            if invert:
                tangent *= -1
            return tangent

        # Get directions
        directions = []
        for entity in (self, other):
            if entity.is_curve():
                directions.append(_get_tangent(entity, point))
            else:
                directions.append(
                    entity.direction_vec()
                    if entity.direction(point)
                    else entity.direction_vec() * (-1)
                )

        dir1, dir2 = directions
        return dir1.angle_signed(dir2)

    def to_bezier(
        self,
        spline,
        startpoint,
        endpoint,
        invert_direction,
        set_startpoint=False,
        midpoints=[],
    ):
        # Get midpoint positions
        segment_count = len(midpoints) + 1
        curve_angle = self.angle
        radius, center, start = self.radius, self.ct.co, self.start.co

        midpoint_positions = get_bezier_curve_midpoint_positions(
            self, segment_count, midpoints, curve_angle
        )

        angle = curve_angle / segment_count

        locations = [self.start.co, *midpoint_positions, self.end.co]
        bezier_points = [startpoint, *midpoints, endpoint]

        if invert_direction:
            locations.reverse()

        if set_startpoint:
            startpoint.co = locations[0].to_3d()

        n = FULL_TURN / angle if angle != 0.0 else 0
        q = (4 / 3) * math.tan(HALF_TURN / (2 * n))
        base_offset = Vector((radius, q * radius))

        create_bezier_curve(
            segment_count,
            bezier_points,
            locations,
            center,
            base_offset,
            invert=invert_direction,
        )

        return endpoint

    def draw_props(self, layout):
        sub = super().draw_props(layout)
        sub.prop(self, "invert_direction")
        return sub

    def is_inside(self, coords):
        # Checks if a position is inside the arcs angle range
        ct = self.ct.co
        p = coords - ct
        p1 = self.start.co - ct
        p2 = self.end.co - ct

        x_axis = Vector((1, 0))

        # angle_signed interprets clockwise as positive, so invert..
        a1 = range_2pi(p.angle_signed(p1))
        a2 = range_2pi(p2.angle_signed(p))

        angle = self.angle

        if not p.length or not p1.length or not p2.length:
            return False

        if a1 < angle > a2:
            return True
        return False

    def overlaps_endpoint(self, co):
        precision = 5
        co_rounded = round_v(co, ndigits=precision)
        if any(
            [
                co_rounded == round_v(v, ndigits=precision)
                for v in (self.p1.co, self.p2.co)
            ]
        ):
            return True
        return False

    def intersect(self, other):
        def parse_retval(retval):
            # Intersect might return None, (value, value) or (value, None)
            values = []
            if hasattr(retval, "__len__"):
                for val in retval:
                    if val is None:
                        continue
                    if not self.is_inside(val):
                        continue
                    if isinstance(other, SlvsArc) and not other.is_inside(val):
                        continue
                    if self.overlaps_endpoint(val) or other.overlaps_endpoint(val):
                        continue

                    values.append(val)
            elif retval is not None:
                if self.overlaps_endpoint(retval) or other.overlaps_endpoint(retval):
                    return ()
                values.append(retval)

            return tuple(values)

        if other.is_line():
            return parse_retval(
                intersect_line_sphere_2d(
                    other.p1.co, other.p2.co, self.ct.co, self.radius
                )
            )
        elif other.is_curve():
            return parse_retval(
                intersect_sphere_sphere_2d(
                    self.ct.co, self.radius, other.ct.co, other.radius
                )
            )

    def distance_along_segment(self, p1, p2):
        ct = self.ct.co
        start, end = self.start.co - ct, self.end.co - ct
        points = (p1, p2) if self.invert_direction else (p2, p1)

        len_1 = range_2pi(end.angle_signed(points[1] - ct))
        len_2 = range_2pi((points[0] - ct).angle_signed(start))

        threshold = 0.000001
        retval = (len_1 + len_2) % (self.angle + threshold)

        return retval

    def replace(self, context, p1, p2, use_self=False):
        if use_self:
            self.p1 = p1
            self.p2 = p2
            return self

        sketch = context.scene.sketcher.active_sketch
        arc = context.scene.sketcher.entities.add_arc(
            sketch.wp.nm, self.ct, p1, p2, sketch
        )
        arc.construction = self.construction
        arc.invert_direction = self.invert_direction
        return arc

    def replace_point(self, old, new):
        for ptr in ("ct", "p1", "p2"):
            if old != getattr(self, ptr):
                continue
            setattr(self, ptr, new)
            break

    def new(self, context: Context, **kwargs) -> SlvsGenericEntity:
        kwargs.setdefault("p1", self.p1)
        kwargs.setdefault("p2", self.p2)
        kwargs.setdefault("sketch", self.sketch)
        kwargs.setdefault("nm", self.nm)
        kwargs.setdefault("ct", self.ct)
        kwargs.setdefault("invert", self.invert_direction)
        kwargs.setdefault("construction", self.construction)
        return context.scene.sketcher.entities.add_arc(**kwargs)


slvs_entity_pointer(SlvsArc, "nm")
slvs_entity_pointer(SlvsArc, "ct")
slvs_entity_pointer(SlvsArc, "p1")
slvs_entity_pointer(SlvsArc, "p2")
slvs_entity_pointer(SlvsArc, "sketch")

register, unregister = register_classes_factory((SlvsArc,))
