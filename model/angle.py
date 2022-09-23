import logging

import math
from bpy.types import PropertyGroup
from bpy.props import BoolProperty, FloatProperty
from bpy.utils import register_classes_factory
from mathutils import Vector, Matrix

from ..utilities.math import pol2cart
from ..utilities.constants import HALF_TURN, QUARTER_TURN
from ..utilities.math import range_2pi
from ..solver import Solver
from ..global_data import WpReq
from ..functions import location_3d_to_region_2d
from .base_constraint import GenericConstraint
from .line_2d import SlvsLine2D
from .utilities import slvs_entity_pointer
from ..utilities.geometry import line_abc_form, get_line_intersection


logger = logging.getLogger(__name__)


class SlvsAngle(GenericConstraint, PropertyGroup):
    """Sets the angle between two lines, applies in 2D only.

    The constraint's setting can be used to to constrain the supplementary angle.
    """

    def invert_angle_getter(self):
        return self.get("setting", self.bl_rna.properties["setting"].default)

    def invert_angle_setter(self, setting):
        self["value"] = HALF_TURN - self.value
        self["setting"] = setting

    label = "Angle"
    value: FloatProperty(
        name=label,
        subtype="ANGLE",
        unit="ROTATION",
        update=GenericConstraint.update_system_cb,
    )
    setting: BoolProperty(
        name="Measure supplementary angle",
        get=invert_angle_getter,
        set=invert_angle_setter,
    )
    draw_offset: FloatProperty(name="Draw Offset", default=1)
    draw_outset: FloatProperty(name="Draw Outset", default=0)
    type = "ANGLE"
    signature = ((SlvsLine2D,), (SlvsLine2D,))
    props = ("value",)

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        kwargs = {
            "group": group,
        }

        wp = self.get_workplane()
        if wp:
            kwargs["wrkpln"] = wp

        return solvesys.addAngle(
            math.degrees(self.value),
            self.setting,
            self.entity1.py_data,
            self.entity2.py_data,
            **kwargs,
        )

    def matrix_basis(self):
        if self.sketch_i == -1:
            return Matrix()

        sketch = self.sketch

        line1 = self.entity1
        line2 = self.entity2

        origin = get_line_intersection(
            *line_abc_form(line1.p1.co, line1.p2.co),
            *line_abc_form(line2.p1.co, line2.p2.co),
        )

        rotation = range_2pi((self.orientation(line2) + self.orientation(line1)) / 2)

        if self.setting:
            rotation = rotation - QUARTER_TURN

        mat_rot = Matrix.Rotation(rotation, 2, "Z")
        mat_local = Matrix.Translation(origin.to_3d()) @ mat_rot.to_4x4()
        return sketch.wp.matrix_basis @ mat_local

    @staticmethod
    def orientation(line):
        pos = line.p2.co - line.p1.co
        return math.atan2(pos[1], pos[0])

    @staticmethod
    def _get_angle(A, B):
        # (A dot B)/(|A||B|) = cos(valA)
        divisor = A.length * B.length
        if not divisor:
            return 0.0

        x = A.dot(B) / divisor
        x = max(-1, min(x, 1))

        return math.degrees(math.acos(x))

    def init_props(self, **kwargs):
        """
        initializes value (angle, in radians),
            setting ("measure supplimentary angle")
            and distance to dimension text (draw_offset)
        """

        line1, line2 = self.entity1, self.entity2
        vec1, vec2 = line1.direction_vec(), line2.direction_vec()
        angle = self._get_angle(vec1, vec2)
        setting = angle > 90
        if not setting:
            angle = 180 - angle

        origin = get_line_intersection(
            *line_abc_form(line1.p1.co, line1.p2.co),
            *line_abc_form(line2.p1.co, line2.p2.co),
        )
        dist = max(
            (line1.midpoint() - origin).length, (line2.midpoint() - origin).length, 0.5
        )
        self.draw_offset = dist if not setting else -dist
        return math.radians(angle), setting

    def text_inside(self):
        return abs(self.draw_outset) < (self.value / 2)

    def update_draw_offset(self, pos, ui_scale):
        self.draw_offset = math.copysign(pos.length / ui_scale, pos.x)
        self.draw_outset = math.atan(pos.y / pos.x)

    def draw_props(self, layout):
        sub = super().draw_props(layout)
        sub.prop(self, "value")
        sub.prop(self, "setting")
        return sub

    def value_placement(self, context):
        """location to display the constraint value"""
        region = context.region
        rv3d = context.space_data.region_3d
        ui_scale = context.preferences.system.ui_scale

        offset = ui_scale * self.draw_offset
        outset = self.draw_outset
        co = pol2cart(offset, outset)
        coords = self.matrix_basis() @ Vector((co[0], co[1], 0))
        return location_3d_to_region_2d(region, rv3d, coords)


slvs_entity_pointer(SlvsAngle, "entity1")
slvs_entity_pointer(SlvsAngle, "entity2")
slvs_entity_pointer(SlvsAngle, "sketch")

register, unregister = register_classes_factory((SlvsAngle,))
