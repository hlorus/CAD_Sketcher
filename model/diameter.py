import logging

import math
from bpy.types import PropertyGroup
from bpy.props import BoolProperty, FloatProperty
from bpy.utils import register_classes_factory
from mathutils import Vector, Matrix

from ..solver import Solver
from ..global_data import WpReq
from ..functions import location_3d_to_region_2d
from ..utilities.math import range_2pi, pol2cart
from .base_constraint import GenericConstraint
from .utilities import slvs_entity_pointer
from .categories import CURVE


logger = logging.getLogger(__name__)


class SlvsDiameter(GenericConstraint, PropertyGroup):
    """Sets the diameter of an arc or a circle."""

    def use_radius_getter(self):
        return self.get("setting", self.bl_rna.properties["setting"].default)

    def use_radius_setter(self, setting):
        old_setting = self.get("setting", self.bl_rna.properties["setting"].default)
        self["setting"] = setting

        distance = None
        if old_setting and not setting:
            distance = self.value * 2
        elif not old_setting and setting:
            distance = self.value / 2

        if distance is not None:
            # Avoid triggering the property's update callback
            self["value"] = distance

    @property
    def label(self):
        return "Radius" if self.setting else "Diameter"

    value: FloatProperty(
        name="Size",
        subtype="DISTANCE",
        unit="LENGTH",
        update=GenericConstraint.update_system_cb,
    )
    setting: BoolProperty(
        name="Use Radius", get=use_radius_getter, set=use_radius_setter
    )
    leader_angle: FloatProperty(name="Leader Angle", default=45, subtype="ANGLE")
    draw_offset: FloatProperty(name="Draw Offset", default=0)
    type = "DIAMETER"
    signature = (CURVE,)
    props = ("value",)

    @property
    def diameter(self):
        value = self.value
        if self.setting:
            return value * 2
        return value

    @property
    def radius(self):
        value = self.value
        if self.setting:
            return value
        return value / 2

    def needs_wp(self):
        return WpReq.OPTIONAL

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        return solvesys.addDiameter(self.diameter, self.entity1.py_data, group=group)

    def init_props(self, **kwargs):
        # Get operators setting value
        setting = kwargs.get("setting")

        value = self.entity1.radius
        if setting is None and self.entity1.bl_rna.name == "SlvsArc":
            self["setting"] = True

        if not setting:
            value = value * 2

        return value, None

    def matrix_basis(self):
        if self.sketch_i == -1:
            return Matrix()
        sketch = self.sketch
        origin = self.entity1.ct.co
        rotation = range_2pi(math.radians(self.leader_angle))
        mat_local = Matrix.Translation(origin.to_3d())
        return sketch.wp.matrix_basis @ mat_local

    def text_inside(self):
        return self.draw_offset < self.radius

    def update_draw_offset(self, pos, ui_scale):
        self.draw_offset = pos.length
        self.leader_angle = math.atan2(pos.y, pos.x)

    def draw_props(self, layout):
        sub = super().draw_props(layout)

        sub.prop(self, "value")

        row = sub.row()
        row.prop(self, "setting")
        return sub

    def value_placement(self, context):
        """location to display the constraint value"""
        region = context.region
        rv3d = context.space_data.region_3d
        offset = self.draw_offset
        coords = pol2cart(offset, self.leader_angle)
        coords2 = self.matrix_basis() @ Vector((coords[0], coords[1], 0.0))
        return location_3d_to_region_2d(region, rv3d, coords2)


slvs_entity_pointer(SlvsDiameter, "entity1")
slvs_entity_pointer(SlvsDiameter, "sketch")

register, unregister = register_classes_factory((SlvsDiameter,))
