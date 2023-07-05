import logging
from typing import List

import bpy
from bpy.types import PropertyGroup
from gpu_extras.batch import batch_for_shader
from bpy.utils import register_classes_factory

from ..solver import Solver
from .base_entity import SlvsGenericEntity
from .utilities import slvs_entity_pointer
from ..utilities.geometry import nearest_point_line_line

logger = logging.getLogger(__name__)


class SlvsLine3D(SlvsGenericEntity, PropertyGroup):
    """Representation of a line in 3D Space.

    Arguments:
        p1 (SlvsPoint3D): Line's startpoint
        p2 (SlvsPoint3D): Line's endpoint
    """

    @classmethod
    def is_path(cls):
        return True

    @classmethod
    def is_line(cls):
        return True

    @classmethod
    def is_segment(cls):
        return True

    def dependencies(self) -> List[SlvsGenericEntity]:
        return [self.p1, self.p2]

    def is_dashed(self):
        return self.construction

    def update(self):
        if bpy.app.background:
            return

        p1, p2 = self.p1.location, self.p2.location
        coords = (p1, p2)

        kwargs = {"pos": coords}
        self._batch = batch_for_shader(self._shader, "LINES", kwargs)

        self.is_dirty = False

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        handle = solvesys.addLineSegment(self.p1.py_data, self.p2.py_data, group=group)
        self.py_data = handle

    def closest_picking_point(self, origin, view_vector):
        """Returns the point on this entity which is closest to the picking ray"""
        p1 = self.p1.location
        d1 = self.p2.location - p1  # normalize?
        return nearest_point_line_line(p1, d1, origin, view_vector)

    def placement(self):
        return (self.p1.location + self.p2.location) / 2

    def orientation(self):
        return (self.p2.location - self.p1.location).normalized()

    @property
    def length(self):
        return (self.p2.location - self.p1.location).length


slvs_entity_pointer(SlvsLine3D, "p1")
slvs_entity_pointer(SlvsLine3D, "p2")

register, unregister = register_classes_factory((SlvsLine3D,))
