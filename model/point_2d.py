import logging
from typing import List

from bpy.types import PropertyGroup
from bpy.props import FloatVectorProperty
from mathutils import Matrix, Vector
from bpy.utils import register_classes_factory

from ..solver import Solver
from .base_entity import SlvsGenericEntity, Entity2D, tag_update
from .utilities import slvs_entity_pointer, make_coincident
from .line_2d import SlvsLine2D
from .vulkan_compat import BillboardPointRenderer

logger = logging.getLogger(__name__)


class Point2D(Entity2D, BillboardPointRenderer):
    @classmethod
    def is_point(cls):
        return True

    def get_point_location_3d(self):
        """Get the 3D location for point rendering."""
        u, v = self.co
        mat_local = Matrix.Translation(Vector((u, v, 0)))
        mat = self.wp.matrix_basis @ mat_local
        return mat @ Vector((0, 0, 0))

    def update(self):
        """Update screen-space point geometry."""
        return self.update_billboard_point()

    def draw(self, context):
        """Draw billboard point with camera-facing geometry."""
        return self.draw_billboard_point(context)

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

        handle = solvesys.add_point_2d(group, *coords, self.wp.py_data)
        self.py_data = handle

    def update_from_slvs(self, solvesys):
        coords = [solvesys.get_param_value(self.py_data['param'][i]) for i in range(2)]
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
        update=tag_update,
    )
    props = ("co",)

    def dependencies(self) -> List[SlvsGenericEntity]:
        return [
            self.sketch,
        ]

    # def tweak(self, solvesys, pos, group):
    #     wrkpln = self.sketch.wp
    #     u, v, _ = wrkpln.matrix_basis.inverted() @ pos

    #     self.create_slvs_data(solvesys, group=group)

    #     p = solvesys.add_point_2d(group, u, v, wrkpln.py_data)
    #     make_coincident(solvesys, p, self, wrkpln.py_data, group, entity_type=SlvsPoint2D)
    #     solvesys.dragged(group, p, wrkpln.py_data)
    #     return

    def draw_props(self, layout):
        sub = super().draw_props(layout)
        sub.prop(self, "co")
        return sub


slvs_entity_pointer(Point2D, "sketch")

register, unregister = register_classes_factory((SlvsPoint2D,))
