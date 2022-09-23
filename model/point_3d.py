import logging

import bpy
from bpy.types import PropertyGroup
from bpy.props import FloatVectorProperty
from gpu_extras.batch import batch_for_shader
from bpy.utils import register_classes_factory

from ..utilities.draw import draw_cube_3d
from ..solver import Solver
from .base_entity import SlvsGenericEntity


logger = logging.getLogger(__name__)


class Point3D(SlvsGenericEntity):
    @classmethod
    def is_point(cls):
        return True

    def update(self):
        if bpy.app.background:
            return

        coords, indices = draw_cube_3d(*self.location, 0.05)
        self._batch = batch_for_shader(
            self._shader, "POINTS", {"pos": (self.location[:],)}
        )
        self.is_dirty = False

    # TODO: maybe rename -> pivot_point, midpoint
    def placement(self):
        return self.location

    def create_slvs_data(self, solvesys, coords=None, group=Solver.group_fixed):
        if not coords:
            coords = self.location

        self.params = [solvesys.addParamV(v, group) for v in coords]

        handle = solvesys.addPoint3d(*self.params, group=group)
        self.py_data = handle

    def update_from_slvs(self, solvesys):
        coords = [solvesys.getParam(i).val for i in self.params]
        self.location = coords

    def closest_picking_point(self, origin, view_vector):
        """Returns the point on this entity which is closest to the picking ray"""
        return self.location


class SlvsPoint3D(Point3D, PropertyGroup):
    """Representation of a point in 3D Space.

    Arguments:
        location (FloatVectorProperty): Point's location in the form (x, y, z)
    """

    location: FloatVectorProperty(
        name="Location",
        description="The location of the point",
        subtype="XYZ",
        unit="LENGTH",
        update=SlvsGenericEntity.tag_update,
    )
    props = ("location",)

    def draw_props(self, layout):
        sub = super().draw_props(layout)
        sub.prop(self, "location")
        return sub


register, unregister = register_classes_factory((SlvsPoint3D,))
