import logging
from typing import List

import bpy
from bpy.types import PropertyGroup
from bpy.props import FloatVectorProperty
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector
from bpy.utils import register_classes_factory

from ..utilities.draw import draw_rect_2d
from ..solver import Solver
from .base_entity import SlvsGenericEntity
from .base_entity import Entity2D
from .utilities import slvs_entity_pointer, make_coincident
from .line_2d import SlvsLine2D

logger = logging.getLogger(__name__)


class Point2D(Entity2D):
    @classmethod
    def is_point(cls):
        return True

    def update(self):
        if bpy.app.background:
            return

        u, v = self.co
        mat_local = Matrix.Translation(Vector((u, v, 0)))

        mat = self.wp.matrix_basis @ mat_local
        size = 0.1
        coords = draw_rect_2d(0, 0, size, size)
        coords = [(mat @ Vector(co))[:] for co in coords]
        indices = ((0, 1, 2), (0, 2, 3))
        pos = self.location
        self._batch = batch_for_shader(self._shader, "POINTS", {"pos": (pos[:],)})
        self.is_dirty = False

    @property
    def location(self):
        u, v = self.co
        mat_local = Matrix.Translation(Vector((u, v, 0)))
        mat = self.wp.matrix_basis @ mat_local
        return mat @ Vector((0, 0, 0))

    def placement(self):
        return self.location

    def create_slvs_data(self, solvesys, coords=None, group=Solver.group_fixed):
        if not coords:
            coords = self.co

        self.params = [solvesys.addParamV(v, group) for v in coords]

        handle = solvesys.addPoint2d(self.wp.py_data, *self.params, group=group)
        self.py_data = handle

    def update_from_slvs(self, solvesys):
        coords = [solvesys.getParam(i).val for i in self.params]
        self.co = coords

    def closest_picking_point(self, origin, view_vector):
        """Returns the point on this entity which is closest to the picking ray"""
        return self.location


class SlvsPoint2D(Point2D, PropertyGroup):
    """Representation of a point in 2D space.

    Arguments:
        co (FloatVectorProperty): The coordinates of the point on the worpkplane in the form (U, V)
        sketch (SlvsSketch): The sketch this entity belongs to
    """

    co: FloatVectorProperty(
        name="Coordinates",
        description="The coordinates of the point on its sketch",
        subtype="XYZ",
        size=2,
        unit="LENGTH",
        update=SlvsGenericEntity.tag_update,
    )

    def dependencies(self) -> List[SlvsGenericEntity]:
        return [
            self.sketch,
        ]

    def tweak(self, solvesys, pos, group):
        wrkpln = self.sketch.wp
        u, v, _ = wrkpln.matrix_basis.inverted() @ pos

        self.create_slvs_data(solvesys, group=group)

        # NOTE: When simply initializing the point on the tweaking positions
        # the solver fails regularly, addWhereDragged fixes a point and might
        # overconstrain a system. When not using addWhereDragged the tweak point
        # might just jump to the tweaked geometry. Bypass this by creating a line
        # perpendicular to move vector and constrain that.

        orig_pos = self.co
        tweak_pos = Vector((u, v))
        tweak_vec = tweak_pos - orig_pos
        perpendicular_vec = Vector((tweak_vec[1], -tweak_vec[0]))

        params = [solvesys.addParamV(val, group) for val in (u, v)]
        startpoint = solvesys.addPoint2d(wrkpln.py_data, *params, group=group)

        p2 = tweak_pos + perpendicular_vec
        params = [solvesys.addParamV(val, group) for val in (p2.x, p2.y)]
        endpoint = solvesys.addPoint2d(wrkpln.py_data, *params, group=group)

        edge = solvesys.addLineSegment(startpoint, endpoint, group=group)
        make_coincident(
            solvesys, self.py_data, edge, wrkpln.py_data, group, entity_type=SlvsLine2D
        )

    def draw_props(self, layout):
        sub = super().draw_props(layout)
        sub.prop(self, "co")
        return sub


slvs_entity_pointer(Point2D, "sketch")

register, unregister = register_classes_factory((SlvsPoint2D,))
