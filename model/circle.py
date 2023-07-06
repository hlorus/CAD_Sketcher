import logging
import math
from typing import List

import bpy
from bpy.types import PropertyGroup
from bpy.props import FloatProperty
from gpu_extras.batch import batch_for_shader
from mathutils import Vector, Matrix
from mathutils.geometry import intersect_line_sphere_2d, intersect_sphere_sphere_2d
from bpy.utils import register_classes_factory

from ..solver import Solver
from ..utilities.math import range_2pi, pol2cart
from .base_entity import SlvsGenericEntity
from .base_entity import Entity2D
from .utilities import slvs_entity_pointer, tag_update
from .constants import CURVE_RESOLUTION
from ..utilities.constants import HALF_TURN, FULL_TURN
from ..utilities.draw import coords_arc_2d
from .utilities import (
    get_bezier_curve_midpoint_positions,
    create_bezier_curve,
)

logger = logging.getLogger(__name__)


class SlvsCircle(Entity2D, PropertyGroup):
    """Representation of a circle in 2D space. The circle is centered at ct with
    its size defined by the radius and is resoulution independent.

    Arguments:
        ct (SlvsPoint2D): Circle's centerpoint
        radius (FloatProperty): The radius of the circle
        nm (SlvsNormal2D):
        sketch (SlvsSketch): The sketch this entity belongs to
    """

    radius: FloatProperty(
        name="Radius",
        description="The radius of the circle",
        subtype="DISTANCE",
        min=0.0,
        unit="LENGTH",
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

    def dependencies(self) -> List[SlvsGenericEntity]:
        return [self.nm, self.ct, self.sketch]

    def is_dashed(self):
        return self.construction

    def update(self):
        if bpy.app.background:
            return

        coords = coords_arc_2d(0, 0, self.radius, CURVE_RESOLUTION)

        u, v = self.ct.co

        mat_local = Matrix.Translation(Vector((u, v, 0)))
        mat = self.wp.matrix_basis @ mat_local
        coords = [(mat @ Vector((*co, 0)))[:] for co in coords]

        kwargs = {"pos": coords}
        self._batch = batch_for_shader(self._shader, "LINE_STRIP", kwargs)
        self.is_dirty = False

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        self.param = solvesys.addParamV(self.radius, group)

        nm = None
        if self.nm != -1:
            nm = self.nm
        else:
            nm = self.wp.nm

        handle = solvesys.addCircle(
            self.ct.py_data,
            self.nm.py_data,
            solvesys.addDistance(self.param),
            group=group,
        )
        self.py_data = handle

    def update_from_slvs(self, solvesys):
        self.radius = solvesys.getParam(self.param).val

    def point_on_curve(self, angle):
        return pol2cart(self.radius, angle) + self.ct.co

    def placement(self):
        return self.wp.matrix_basis @ self.point_on_curve(45).to_3d()

    @classmethod
    def is_closed(cls):
        return True

    def connection_points(self):
        # NOTE: it should probably be possible to lookup coincident points on circle
        return []

    def direction(self, point, is_endpoint=False):
        return False

    def bezier_segment_count(self):
        return 4

    def bezier_point_count(self):
        return self.bezier_segment_count()

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
        radius, center = self.radius, self.ct.co

        bezier_points = [startpoint, *midpoints]

        locations = get_bezier_curve_midpoint_positions(
            self, segment_count, bezier_points, FULL_TURN, cyclic=True
        )
        angle = FULL_TURN / segment_count

        n = FULL_TURN / angle
        q = (4 / 3) * math.tan(HALF_TURN / (2 * n))
        base_offset = Vector((radius, q * radius))

        create_bezier_curve(
            segment_count,
            bezier_points,
            locations,
            center,
            base_offset,
            invert=invert_direction,
            cyclic=True,
        )
        return endpoint

    def overlaps_endpoint(self, co):
        return False

    def intersect(self, other):
        def parse_retval(retval):
            # Intersect might return None, (value, value) or (value, None)
            values = []
            if hasattr(retval, "__len__"):
                for val in retval:
                    if val is None:
                        continue
                    if other.overlaps_endpoint(val):
                        continue
                    values.append(val)
            elif retval is not None:
                if other.overlaps_endpoint(retval):
                    return ()
                values.append(retval)

            return tuple(values)

        if other.is_line():
            return parse_retval(
                intersect_line_sphere_2d(
                    other.p1.co, other.p2.co, self.ct.co, self.radius
                )
            )
        elif isinstance(other, SlvsCircle):
            return parse_retval(
                intersect_sphere_sphere_2d(
                    self.ct.co, self.radius, other.ct.co, other.radius
                )
            )
        else:
            return other.intersect(self)

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
        return arc

    def distance_along_segment(self, p1, p2):
        ct = self.ct.co
        start, end = p1 - ct, p2 - ct
        angle = range_2pi(math.atan2(*end.yx) - math.atan2(*start.yx))
        retval = self.radius * angle
        return retval


    def new(self, context, **kwargs) -> SlvsGenericEntity:
        kwargs.setdefault("ct", self.ct)
        kwargs.setdefault("nm", self.nm)
        kwargs.setdefault("radius", self.radius)
        kwargs.setdefault("sketch", self.sketch)
        kwargs.setdefault("construction", self.construction)
        return context.scene.sketcher.entities.add_circle(**kwargs)


slvs_entity_pointer(SlvsCircle, "nm")
slvs_entity_pointer(SlvsCircle, "ct")
slvs_entity_pointer(SlvsCircle, "sketch")

register, unregister = register_classes_factory((SlvsCircle,))
