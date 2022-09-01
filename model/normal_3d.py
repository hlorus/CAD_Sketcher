import logging

from bpy.types import PropertyGroup, Context
from bpy.props import FloatVectorProperty
from bpy.utils import register_classes_factory
from mathutils import Euler

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

    def get_orientation(self):
        return getattr(self, "orientation").to_euler()

    def set_orientation(self, value):
        self["orientation"] = Euler(value).to_quaternion()

    orientation: FloatVectorProperty(
        name="Orientation",
        description="Quaternion which describes the orientation of the normal",
        subtype="QUATERNION",
        size=4,
        update=SlvsGenericEntity.tag_update,
    )

    ui_orientation: FloatVectorProperty(
        name="Orientation",
        subtype="EULER",
        size=3,
        get=get_orientation,
        set=set_orientation,
        options={"SKIP_SAVE"},
        update=SlvsGenericEntity.tag_update,
    )
    props = ("ui_orientation",)

    def draw_props(self, layout):
        sub = super().draw_props(layout)
        sub.prop(self, "ui_orientation")
        return sub


register, unregister = register_classes_factory((SlvsNormal3D,))
