import logging

from bpy.types import PropertyGroup, Context
from bpy.props import FloatVectorProperty
from bpy.utils import register_classes_factory

from ..solver import Solver
from .base_entity import SlvsGenericEntity


logger = logging.getLogger(__name__)


class Normal3D(SlvsGenericEntity):
    def update(self):
        self.is_dirty = False

    def draw(self, context: Context):
        pass

    def draw_id(self, context: Context):
        pass

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        quat = self.orientation
        handle = solvesys.addNormal3dV(quat.w, quat.x, quat.y, quat.z, group=group)
        self.py_data = handle


class SlvsNormal3D(Normal3D, PropertyGroup):
    """Representation of a normal in 3D Space which is used to
    store a direction.

    This entity isn't currently exposed to the user and gets created
    implicitly when needed.

    Arguments:
        orientation (Quaternion): A quaternion which describes the rotation
    """

    orientation: FloatVectorProperty(
        name="Orientation",
        description="Quaternion which describes the orientation of the normal",
        subtype="QUATERNION",
        size=4,
        update=SlvsGenericEntity.tag_update,
    )
    pass


register, unregister = register_classes_factory((SlvsNormal3D,))
