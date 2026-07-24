import logging

import math
from bpy.types import PropertyGroup, Context
from bpy.props import BoolProperty, FloatProperty, IntProperty, StringProperty
from bpy.utils import register_classes_factory
from mathutils import Vector, Matrix

from ..utilities.math import pol2cart
from ..utilities.constants import HALF_TURN, QUARTER_TURN
from ..utilities.math import range_2pi
from ..curve_solver import Solver
from ..global_data import WpReq
from ..utilities.view import location_3d_to_region_2d
from .base_constraint import DimensionalConstraint
from .line_2d import SlvsLine2D
from .utilities import slvs_entity_pointer
from ..utilities.geometry import line_abc_form, get_line_intersection
from ..utilities.solver import update_system_cb


logger = logging.getLogger(__name__)


class SlvsAngle(DimensionalConstraint, PropertyGroup):
    """Sets the angle between two lines, applies in 2D only.

    The constraint's setting can be used to to constrain the supplementary angle.
    """

    def assign_init_props(self, context: Context = None, **kwargs):
        # Updating self.setting will create recursion loop

        super().assign_init_props(context)

        r1, r2 = self.ref(1), self.ref(2)
        # Unresolved references (e.g. legacy files before migration) — skip the
        # draw-offset computation rather than dereferencing None.
        if r1 is None or r2 is None:
            return
        origin = get_line_intersection(
            *line_abc_form(r1.p1.co, r1.p2.co),
            *line_abc_form(r2.p1.co, r2.p2.co),
        )
        dist = max(
            (r1.midpoint() - origin).length, (r2.midpoint() - origin).length, 0.5
        )
        self.draw_offset = dist if not self.setting else -dist

    label = "Angle"
    value_store: FloatProperty(
        name="Angle Storage",
        subtype="ANGLE",
        unit="ROTATION",
        precision=6,
    )
    value: FloatProperty(
        name=label,
        subtype="ANGLE",
        unit="ROTATION",
        precision=6,
        update=update_system_cb,
        get=DimensionalConstraint._get_value,
        set=DimensionalConstraint._set_value,
    )
    setting: BoolProperty(
        name="Measure supplementary angle",
        update=DimensionalConstraint.assign_init_props,
    )
    draw_offset: FloatProperty(name="Draw Offset", default=1)
    draw_outset: FloatProperty(name="Draw Outset", default=0)
    type = "ANGLE"
    signature = ((SlvsLine2D,), (SlvsLine2D,))
    props = ("value",)

    curve_id_1: StringProperty(name="Curve ID 1", default="")
    curve_id_2: StringProperty(name="Curve ID 2", default="")

    def create_slvs_data_from_curves(self, solvesys, handle_map, wp, group):
        h1 = handle_map.get(self.curve_id_1)
        h2 = handle_map.get(self.curve_id_2)
        if h1 is None or h2 is None:
            return None
        return solvesys.angle(group, h1, h2, math.degrees(self.value), wp, self.setting)

    def needs_wp(self):
        return WpReq.NOT_FREE

    def to_displayed_value(self, value):
        return HALF_TURN - value if self.setting else value

    def from_displayed_value(self, value):
        return HALF_TURN - value if self.setting else value

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        wp = self.get_workplane()

        return solvesys.angle(
            group,
            self.entity1.py_data,
            self.entity2.py_data,
            math.degrees(self.value),
            wp,
            self.setting,
        )

    def matrix_basis(self):
        r1, r2 = self.ref(1), self.ref(2)
        if not r1 or not r2:
            return Matrix()
        origin = get_line_intersection(
            *line_abc_form(r1.p1.co, r1.p2.co),
            *line_abc_form(r2.p1.co, r2.p2.co),
        )
        rotation = range_2pi(
            (self.orientation(r2) + self.orientation(r1)) / 2
        )
        wp_mat = r1.wp_matrix

        if self.setting:
            rotation = rotation - QUARTER_TURN

        mat_rot = Matrix.Rotation(rotation, 2, "Z")
        mat_local = Matrix.Translation(origin.to_3d()) @ mat_rot.to_4x4()
        return wp_mat @ mat_local

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

    def _get_init_value(self, setting):
        r1, r2 = self.ref(1), self.ref(2)
        # Guard against unresolved references (e.g. legacy files before
        # migration remaps entity pointers to curve ids).
        if r1 is None or r2 is None:
            return 0.0
        return self._get_angle(r1.direction_vec(), r2.direction_vec())

    def init_props(self, **kwargs):
        """
        initializes value (angle, in radians),
            setting ("measure supplimentary angle")
            and distance to dimension text (draw_offset)
        """

        setting = kwargs.get("setting", self.setting)
        angle = kwargs.get("value", self._get_init_value(setting))

        return {
            "value": math.radians(angle),
            "setting": setting,
        }

    def text_inside(self):
        return abs(self.draw_outset) < (self.value / 2)

    def update_draw_offset(self, pos, ui_scale):
        self.draw_offset = math.copysign(pos.length / ui_scale, pos.x)
        self.draw_outset = math.atan(pos.y / pos.x)

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
