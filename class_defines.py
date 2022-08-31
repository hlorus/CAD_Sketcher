from typing import Generator, List, Union
import logging
import math


import bpy
from bpy.types import PropertyGroup, Context, UILayout
from bpy.props import (
    CollectionProperty,
    PointerProperty,
    FloatProperty,
    IntProperty,
    BoolProperty,
    IntVectorProperty,
    EnumProperty,
    StringProperty,
)
from bpy_extras.view3d_utils import location_3d_to_region_2d
import math
from mathutils import Vector, Matrix
from mathutils.geometry import (
    distance_point_to_plane,
    intersect_point_line,
)

from . import global_data, functions
from .utilities import preferences
from .solver import solve_system, Solver
from .functions import pol2cart
from .declarations import Operators
from .global_data import WpReq
from .utilities.constants import HALF_TURN, QUARTER_TURN

logger = logging.getLogger(__name__)


from .model.base_entity import SlvsGenericEntity

# Drawing a point might not include points coord itself but rather a series of virtual points around it
# so a Entity might refer another point entity and/or add a set of coords
#
# Different shaders are needed:
# - faces shader
# - outlines shader
# each needs a matching batch


from .model.utilities import slvs_entity_pointer

from .model.point_3d import SlvsPoint3D
from .model.line_3d import SlvsLine3D
from .model.normal_3d import SlvsNormal3D
from .model.workplane import SlvsWorkplane
from .model.sketch import SlvsSketch
from .model.point_2d import SlvsPoint2D
from .model.line_2d import SlvsLine2D
from .model.normal_2d import SlvsNormal2D
from .model.arc import SlvsArc
from .model.circle import SlvsCircle
from .model.group_entities import SlvsEntities
from .model.base_constraint import GenericConstraint

from .model.categories import *

from .model.utilities import *


### Constraints


class SlvsCoincident(GenericConstraint, PropertyGroup):
    """Forces two points to be coincident,
    or a point to lie on a curve, or a point to lie on a plane.

    The point-coincident constraint is available in both 3d and projected versions.
    The 3d point-coincident constraint restricts three degrees of freedom;
    the projected version restricts only two. If two points are drawn in a workplane,
    and then constrained coincident in 3d, then an error will result–they are already
    coincident in one dimension (the dimension normal to the plane),
    so the third constraint equation is redundant.
    """

    type = "COINCIDENT"
    label = "Coincident"
    signature = (point, (*point, *line, SlvsWorkplane, SlvsCircle, SlvsArc))
    # NOTE: Coincident between 3dPoint and Workplane currently doesn't seem to work

    def needs_wp(self):
        if isinstance(self.entity2, SlvsWorkplane):
            return WpReq.FREE
        return WpReq.OPTIONAL

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        return make_coincident(
            solvesys, self.entity1.py_data, self.entity2, self.get_workplane(), group
        )

    def placements(self):
        return (self.entity1,)


slvs_entity_pointer(SlvsCoincident, "entity1")
slvs_entity_pointer(SlvsCoincident, "entity2")
slvs_entity_pointer(SlvsCoincident, "sketch")


line_arc_circle = (*line, *curve)


class SlvsEqual(GenericConstraint, PropertyGroup):
    """Forces two lengths, or radiuses to be equal.

    If a line and an arc of a circle are selected, then the length of the line is
    forced equal to the length (not the radius) of the arc.
    """

    # TODO: Also supports equal angle

    type = "EQUAL"
    label = "Equal"
    signature = (line_arc_circle, line_arc_circle)

    @classmethod
    def get_types(cls, index, entities):
        e = entities[1] if index == 0 else entities[0]
        if e:
            if type(e) in (SlvsLine2D, SlvsArc):
                return (SlvsLine2D, SlvsArc)
            elif type(e) == SlvsCircle:
                return curve
            return (type(e),)
        return cls.signature[index]

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        # TODO: Don't allow to add Equal between Line and Circle
        e1, e2 = self.entity1, self.entity2

        func = None
        set_wp = False

        if all([type(e) in line for e in (e1, e2)]):
            func = solvesys.addEqualLength
            set_wp = True
        elif all([type(e) in curve for e in (e1, e2)]):
            func = solvesys.addEqualRadius
        else:
            # TODO: Do a proper check to see if there's really one Arc and one Line
            func = solvesys.addEqualLineArcLength
            set_wp = True

        kwargs = {
            "group": group,
        }

        if set_wp:
            kwargs["wrkpln"] = self.get_workplane()

        return func(e1.py_data, e2.py_data, **kwargs)

    def placements(self):
        return (self.entity1, self.entity2)


slvs_entity_pointer(SlvsEqual, "entity1")
slvs_entity_pointer(SlvsEqual, "entity2")
slvs_entity_pointer(SlvsEqual, "sketch")


def get_side_of_line(line_start, line_end, point):
    line_end = line_end - line_start
    point = point - line_start
    return -(
        (line_end.x - line_start.x) * (point.y - line_start.y)
        - (line_end.y - line_start.y) * (point.x - line_start.x)
    )


align_items = [
    ("NONE", "None", "", 0),
    ("HORIZONTAL", "Horizontal", "", 1),
    ("VERTICAL", "Vertical", "", 2),
]


class SlvsDistance(GenericConstraint, PropertyGroup):
    """Sets the distance between a point and some other entity (point/line/Workplane)."""

    def get_distance_value(self):
        return self.get("value", self.rna_type.properties["value"].default)

    def set_distance_value(self, value):
        self["value"] = abs(value)

    label = "Distance"
    value: FloatProperty(
        name=label,
        subtype="DISTANCE",
        unit="LENGTH",
        update=GenericConstraint.update_system_cb,
        get=get_distance_value,
        set=set_distance_value,
    )
    flip: BoolProperty(name="Flip", update=GenericConstraint.update_system_cb)
    align: EnumProperty(
        name="Align",
        items=align_items,
        update=GenericConstraint.update_system_cb,
    )
    draw_offset: FloatProperty(name="Draw Offset", default=0.3)
    draw_outset: FloatProperty(name="Draw Outset", default=0.0)
    type = "DISTANCE"
    signature = ((*point, *line, SlvsCircle, SlvsArc), (*point, *line, SlvsWorkplane))
    props = ("value",)

    @classmethod
    def get_types(cls, index, entities):
        e = entities[1] if index == 0 else entities[0]

        if e:
            if index == 1 and e.is_line():
                # Allow constraining a single line
                return None
            if e.is_3d():
                return ((SlvsPoint3D,), (SlvsPoint3D, SlvsLine3D, SlvsWorkplane))[index]
            return (point_2d, (*point_2d, SlvsLine2D))[index]
        return cls.signature[index]

    def needs_wp(self):
        if isinstance(self.entity2, SlvsWorkplane):
            return WpReq.FREE
        return WpReq.OPTIONAL

    def use_flipping(self):
        # Only use flipping for constraint between point and line/workplane
        if self.entity1.is_curve():
            return False
        return type(self.entity2) in (*line, SlvsWorkplane)

    def use_align(self):
        if type(self.entity2) in (*line, SlvsWorkplane):
            return False
        if self.entity1.is_curve():
            return False
        return True

    def get_value(self):
        value = self.value
        if self.use_flipping() and self.flip:
            return value * -1
        return value

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        if self.entity1 == self.entity2:
            raise AttributeError("Cannot create constraint between one entity itself")
        # TODO: don't allow Distance if Point -> Line if (Point in Line)

        e1, e2 = self.entity1, self.entity2
        if e1.is_line():
            e1, e2 = e1.p1, e1.p2

        func = None
        set_wp = False
        wp = self.get_workplane()
        alignment = self.align
        align = self.use_align() and alignment != "NONE"
        handles = []

        value = self.get_value()

        # circle/arc -> line/point
        if type(e1) in curve:
            # TODO: make Horizontal and Vertical alignment work
            if type(e2) in line:
                return solvesys.addPointLineDistance(
                    value + e1.radius, e1.ct.py_data, e2.py_data, wp, group
                )
            else:
                assert isinstance(e2, SlvsPoint2D)
                return solvesys.addPointsDistance(
                    value + e1.radius, e1.ct.py_data, e2.py_data, wp, group
                )

        elif type(e2) in line:
            func = solvesys.addPointLineDistance
            set_wp = True
        elif isinstance(e2, SlvsWorkplane):
            func = solvesys.addPointPlaneDistance
        elif type(e2) in point:
            if align and all([e.is_2d() for e in (e1, e2)]):
                # Get Point in between
                p1, p2 = e1.co, e2.co
                coords = (p2.x, p1.y)

                params = [solvesys.addParamV(v, group) for v in coords]
                p = solvesys.addPoint2d(wp, *params, group=group)

                handles.append(
                    solvesys.addPointsHorizontal(p, e2.py_data, wp, group=group)
                )
                handles.append(
                    solvesys.addPointsVertical(p, e1.py_data, wp, group=group)
                )

                base_point = e1 if alignment == "VERTICAL" else e2
                handles.append(
                    solvesys.addPointsDistance(
                        value, p, base_point.py_data, wrkpln=wp, group=group
                    )
                )
                return handles
            else:
                func = solvesys.addPointsDistance
            set_wp = True

        kwargs = {
            "group": group,
        }

        if set_wp:
            kwargs["wrkpln"] = self.get_workplane()

        return func(value, e1.py_data, e2.py_data, **kwargs)

    def matrix_basis(self):
        if self.sketch_i == -1 or not self.entity1.is_2d():
            # TODO: Support distance in 3d
            return Matrix()

        sketch = self.sketch
        x_axis = Vector((1, 0))
        alignment = self.align
        align = self.use_align() and alignment != "NONE"

        e1, e2 = self.entity1, self.entity2
        #   e1       e2
        #   ----------------
        #   line     [none]
        #   point    point
        #   point    line
        #   arc      point
        #   arc      line
        #   circle   point
        #   circle   line

        # set p1 and p2
        if e1.is_curve():
            # reframe as point->point and continue
            centerpoint = e1.ct.co
            if e2.is_line():
                p2, _ = intersect_point_line(centerpoint, e2.p1.co, e2.p2.co)
            else:
                assert isinstance(e2, SlvsPoint2D)
                p2 = e2.co
            if (p2 - centerpoint).length > 0:
                vec = (p2 - centerpoint) / (p2 - centerpoint).length
                p1 = centerpoint + (e1.radius * Vector(vec))
            else:
                # This is a curve->line where the centerpoint of the curve is
                # coincident with the line.  By reassigning p1 to an endpoint
                # of the line, we avoid p1=p2 errors and the result is
                # (correctly) an invalid constraint
                p1 = e2.p1.co
        elif e1.is_line():
            # reframe as point->point and continue
            e1, e2 = e1.p1, e1.p2
            p1, p2 = e1.co, e2.co
        else:
            assert isinstance(e1, SlvsPoint2D)
            p1 = e1.co

        if type(e2) in point_2d:
            # this includes "Line Length" (now point->point)
            # and curve -> point
            p2 = e2.co
            if not align:
                v_rotation = p2 - p1
            else:
                v_rotation = (
                    Vector((1.0, 0.0))
                    if alignment == "HORIZONTAL"
                    else Vector((0.0, 1.0))
                )
            angle = v_rotation.angle_signed(x_axis)
            mat_rot = Matrix.Rotation(angle, 2, "Z")
            v_translation = (p2 + p1) / 2

        elif e2.is_line():
            # curve -> line
            # or point -> line
            if e1.is_curve():
                if not align:
                    v_rotation = p2 - p1
                else:
                    v_rotation = (
                        Vector((1.0, 0.0))
                        if alignment == "HORIZONTAL"
                        else Vector((0.0, 1.0))
                    )
                if v_rotation.length != 0:
                    angle = v_rotation.angle_signed(x_axis)
                else:
                    angle = 0
                mat_rot = Matrix.Rotation(angle, 2, "Z")
                v_translation = (p2 + p1) / 2
            else:
                assert isinstance(e1, SlvsPoint2D)
                orig = e2.p1.co
                end = e2.p2.co
                vec = end - orig
                angle = (math.tau / 4) + functions.range_2pi(math.atan2(vec[1], vec[0]))
                mat_rot = Matrix.Rotation(angle, 2, "Z")
                p1 = p1 - orig
                v_translation = orig + (p1 + p1.project(vec)) / 2

        mat_local = Matrix.Translation(v_translation.to_3d()) @ mat_rot.to_4x4()
        return sketch.wp.matrix_basis @ mat_local

    def init_props(self, **kwargs):
        # Set initial distance value to the current spacing
        e1, e2 = self.entity1, self.entity2
        if e1.is_line():
            value = e1.length
        elif type(e1) in curve:
            centerpoint = e1.ct.co
            if isinstance(e2, SlvsLine2D):
                endpoint, _ = intersect_point_line(centerpoint, e2.p1.co, e2.p2.co)
            else:
                assert isinstance(e2, SlvsPoint2D)
                endpoint = e2.co
            value = (centerpoint - endpoint).length - e1.radius
        elif isinstance(e2, SlvsWorkplane):
            # Returns the signed distance to the plane
            value = distance_point_to_plane(e1.location, e2.p1.location, e2.normal)
        elif type(e2) in line:
            orig = e2.p1.location
            end = e2.p2.location - orig
            p1 = e1.location - orig
            value = (p1 - (p1).project(end)).length

            # NOTE: Comment from solvespace documentation:
            # When constraining the distance between a point and a plane,
            # or a point and a plane face, or a point and a line in a workplane,
            # the distance is signed. The distance may be positive or negative,
            # depending on whether the point is above or below the plane.
            # The distance is always shown positive on the sketch;
            # to flip to the other side, enter a negative value.
            value = math.copysign(
                value,
                get_side_of_line(e2.p1.location, e2.p2.location, e1.location),
            )
        else:
            value = (e1.location - e2.location).length

        if self.use_flipping() and value < 0:
            value = abs(value)
            self.flip = not self.flip

        self.value = value
        return value, None

    def text_inside(self, ui_scale):
        return (ui_scale * abs(self.draw_outset)) < self.value / 2

    def update_draw_offset(self, pos, ui_scale):
        self.draw_offset = pos[1] / ui_scale
        self.draw_outset = pos[0] / ui_scale

    def draw_props(self, layout):
        sub = super().draw_props(layout)

        sub.prop(self, "value")

        row = sub.row()
        row.active = self.use_flipping()
        row.prop(self, "flip")

        sub.label(text="Alignment:")
        row = sub.row()
        row.active = self.use_align()
        row.prop(self, "align", text="")

        if preferences.is_experimental():
            sub.prop(self, "draw_offset")

        return sub

    def value_placement(self, context):
        """location to display the constraint value"""
        region = context.region
        rv3d = context.space_data.region_3d
        ui_scale = context.preferences.system.ui_scale

        offset = ui_scale * self.draw_offset
        outset = ui_scale * self.draw_outset
        coords = self.matrix_basis() @ Vector((outset, offset, 0))
        return location_3d_to_region_2d(region, rv3d, coords)


slvs_entity_pointer(SlvsDistance, "entity1")
slvs_entity_pointer(SlvsDistance, "entity2")
slvs_entity_pointer(SlvsDistance, "sketch")


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
    signature = (curve,)
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
        rotation = functions.range_2pi(math.radians(self.leader_angle))
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
        coords = functions.pol2cart(offset, self.leader_angle)
        coords2 = self.matrix_basis() @ Vector((coords[0], coords[1], 0.0))
        return location_3d_to_region_2d(region, rv3d, coords2)


slvs_entity_pointer(SlvsDiameter, "entity1")
slvs_entity_pointer(SlvsDiameter, "sketch")


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

        origin = functions.get_line_intersection(
            *functions.line_abc_form(line1.p1.co, line1.p2.co),
            *functions.line_abc_form(line2.p1.co, line2.p2.co),
        )

        rotation = functions.range_2pi(
            (self.orientation(line2) + self.orientation(line1)) / 2
        )

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

        origin = functions.get_line_intersection(
            *functions.line_abc_form(line1.p1.co, line1.p2.co),
            *functions.line_abc_form(line2.p1.co, line2.p2.co),
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


class SlvsParallel(GenericConstraint, PropertyGroup):
    """Forces two lines to be parallel. Applies only in 2D."""

    type = "PARALLEL"
    label = "Parallel"
    signature = ((SlvsLine2D,), (SlvsLine2D,))

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        return solvesys.addParallel(
            self.entity1.py_data,
            self.entity2.py_data,
            wrkpln=self.get_workplane(),
            group=group,
        )

    def placements(self):
        return (self.entity1, self.entity2)


slvs_entity_pointer(SlvsParallel, "entity1")
slvs_entity_pointer(SlvsParallel, "entity2")
slvs_entity_pointer(SlvsParallel, "sketch")


# NOTE: this could also support constraining two points
class SlvsHorizontal(GenericConstraint, PropertyGroup):
    """Forces a line segment to be horizontal. It applies in 2D Space only because
    the meaning of horizontal or vertical is defined by the workplane.
    """

    type = "HORIZONTAL"
    label = "Horizontal"
    signature = ((SlvsLine2D, SlvsPoint2D), (SlvsPoint2D,))

    @classmethod
    def get_types(cls, index, entities):
        if index == 1:
            # return None if first entity is line
            if entities[0] and entities[0].is_line():
                return None

        return cls.signature[index]

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        wp = self.get_workplane()
        if self.entity1.is_point():
            return solvesys.addPointsHorizontal(
                self.entity1.py_data, self.entity2.py_data, wp, group=group
            )
        return solvesys.addLineHorizontal(self.entity1.py_data, wrkpln=wp, group=group)

    def placements(self):
        return (self.entity1,)


slvs_entity_pointer(SlvsHorizontal, "entity1")
slvs_entity_pointer(SlvsHorizontal, "entity2")
slvs_entity_pointer(SlvsHorizontal, "sketch")


class SlvsVertical(GenericConstraint, PropertyGroup):
    """Forces a line segment to be vertical. It applies in 2D Space only because
    the meaning of horizontal or vertical is defined by the workplane.
    """

    type = "VERTICAL"
    label = "Vertical"
    signature = ((SlvsLine2D, SlvsPoint2D), (SlvsPoint2D,))

    @classmethod
    def get_types(cls, index, entities):
        if index == 1:
            # return None if first entity is line
            if entities[0] and entities[0].is_line():
                return None

        return cls.signature[index]

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        wp = self.get_workplane()
        if self.entity1.is_point():
            return solvesys.addPointsVertical(
                self.entity1.py_data, self.entity2.py_data, wp, group=group
            )
        return solvesys.addLineVertical(self.entity1.py_data, wrkpln=wp, group=group)

    def placements(self):
        return (self.entity1,)


slvs_entity_pointer(SlvsVertical, "entity1")
slvs_entity_pointer(SlvsVertical, "entity2")
slvs_entity_pointer(SlvsVertical, "sketch")


class SlvsPerpendicular(GenericConstraint, PropertyGroup):
    """Forces two lines to be perpendicular, applies only in 2D. This constraint
    is equivalent to an angle constraint for ninety degrees.
    """

    type = "PERPENDICULAR"
    label = "Perpendicular"
    signature = ((SlvsLine2D,), (SlvsLine2D,))

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        return solvesys.addPerpendicular(
            self.entity1.py_data,
            self.entity2.py_data,
            wrkpln=self.get_workplane(),
            group=group,
        )

    def placements(self):
        point = get_connection_point(self.entity1, self.entity2)
        if point:
            return (point,)
        return (self.entity1, self.entity2)


slvs_entity_pointer(SlvsPerpendicular, "entity1")
slvs_entity_pointer(SlvsPerpendicular, "entity2")
slvs_entity_pointer(SlvsPerpendicular, "sketch")


class SlvsTangent(GenericConstraint, PropertyGroup):
    """Forces two curves (arc/circle) or a curve and a line to be tangent."""

    type = "TANGENT"
    label = "Tangent"
    signature = (curve, (SlvsLine2D, *curve))

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        e1, e2 = self.entity1, self.entity2
        wp = self.get_workplane()

        # check if entities share a point
        point = get_connection_point(e1, e2)
        if point and not isinstance(e2, SlvsCircle):
            if isinstance(e2, SlvsLine2D):
                return solvesys.addArcLineTangent(
                    e1.direction(point),
                    e1.py_data,
                    e2.py_data,
                    group=group,
                )
            elif isinstance(e2, SlvsArc):
                return solvesys.addCurvesTangent(
                    e1.direction(point),
                    e2.direction(point),
                    e1.py_data,
                    e2.py_data,
                    wrkpln=wp,
                    group=group,
                )

        elif isinstance(e2, SlvsLine2D):
            orig = e2.p1.co
            coords = (e1.ct.co - orig).project(e2.p2.co - orig) + orig
            params = [solvesys.addParamV(v, group) for v in coords]
            p = solvesys.addPoint2d(wp, *params, group=group)
            l = solvesys.addLineSegment(e1.ct.py_data, p, group=group)

            return (
                make_coincident(solvesys, p, e1, wp, group),
                make_coincident(solvesys, p, e2, wp, group),
                solvesys.addPerpendicular(e2.py_data, l, wrkpln=wp, group=group),
            )

        elif type(e2) in curve:
            coords = (e1.ct.co + e2.ct.co) / 2
            params = [solvesys.addParamV(v, group) for v in coords]
            p = solvesys.addPoint2d(wp, *params, group=group)
            l = solvesys.addLineSegment(e1.ct.py_data, e2.ct.py_data, group=group)

            return (
                make_coincident(solvesys, p, e1, wp, group),
                make_coincident(solvesys, p, e2, wp, group),
                solvesys.addPointOnLine(p, l, group=group, wrkpln=wp),
            )

    def placements(self):
        point = get_connection_point(self.entity1, self.entity2)
        return (point,)


slvs_entity_pointer(SlvsTangent, "entity1")
slvs_entity_pointer(SlvsTangent, "entity2")
slvs_entity_pointer(SlvsTangent, "sketch")


class SlvsMidpoint(GenericConstraint, PropertyGroup):
    """Forces a point to lie on the midpoint of a line."""

    type = "MIDPOINT"
    label = "Midpoint"
    signature = (point, line)

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        kwargs = {
            "group": group,
        }

        wp = self.get_workplane()
        if wp:
            kwargs["wrkpln"] = wp

        return solvesys.addMidPoint(
            self.entity1.py_data,
            self.entity2.py_data,
            **kwargs,
        )

    def placements(self):
        return (self.entity2,)


slvs_entity_pointer(SlvsMidpoint, "entity1")
slvs_entity_pointer(SlvsMidpoint, "entity2")
slvs_entity_pointer(SlvsMidpoint, "sketch")


class SlvsSymmetric(GenericConstraint, PropertyGroup):
    """Forces two points to be symmetric about a plane.

    The symmetry plane may be a workplane when used in 3D. Or, the symmetry plane
    may be specified as a line in a workplane; the symmetry plane is then through
    that line, and normal to the workplane.

    """

    type = "SYMMETRIC"
    label = "Symmetric"

    # TODO: not all combinations are possible!
    signature = (
        point,
        point,
        (SlvsLine2D, SlvsWorkplane),
    )

    def needs_wp(self):
        if isinstance(self.entity3, SlvsLine2D):
            return WpReq.NOT_FREE
        return WpReq.FREE

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        e1, e2, e3 = self.entity1, self.entity2, self.entity3

        # NOTE: this doesn't seem to work correctly, acts like addSymmetricVertical
        if isinstance(e3, SlvsLine2D):
            return solvesys.addSymmetricLine(
                e1.py_data,
                e2.py_data,
                e3.py_data,
                self.get_workplane(),
                group=group,
            )

        elif isinstance(e3, SlvsWorkplane):
            return solvesys.addSymmetric(
                e1.py_data,
                e2.py_data,
                e3.py_data,
                wrkpln=self.get_workplane(),
                group=group,
            )

    def placements(self):
        return (self.entity1, self.entity2, self.entity3)


slvs_entity_pointer(SlvsSymmetric, "entity1")
slvs_entity_pointer(SlvsSymmetric, "entity2")
slvs_entity_pointer(SlvsSymmetric, "entity3")
slvs_entity_pointer(SlvsSymmetric, "sketch")


class SlvsRatio(GenericConstraint, PropertyGroup):
    """Defines the ratio between the lengths of two line segments.

    The order matters; the ratio is defined as length of entity1 : length of entity2.
    """

    type = "RATIO"
    label = "Ratio"

    value: FloatProperty(
        name=label,
        subtype="UNSIGNED",
        update=GenericConstraint.update_system_cb,
        min=0.0,
    )

    signature = (
        line,
        line,
    )

    def needs_wp(self):
        if isinstance(self.entity1, SlvsLine2D) or isinstance(self.entity2, SlvsLine2D):
            return WpReq.NOT_FREE
        return WpReq.FREE

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        e1, e2 = self.entity1, self.entity2

        return solvesys.addLengthRatio(
            self.value,
            e1.py_data,
            e2.py_data,
            self.get_workplane(),
            group=group,
        )

    def init_props(self, **kwargs):
        line1, line2 = self.entity1, self.entity2

        value = line1.length / line2.length
        return value, None

    def draw_props(self, layout):
        sub = super().draw_props(layout)
        sub.prop(self, "value")
        return sub

    def placements(self):
        return (self.entity1, self.entity2)


slvs_entity_pointer(SlvsRatio, "entity1")
slvs_entity_pointer(SlvsRatio, "entity2")
slvs_entity_pointer(SlvsRatio, "sketch")

# TODO: Support advanced constraint types
# - symmetric_h
# - symmetric_v
# - ratio
# - same orientation
# - distance projected


# class SlvsDistanceProj(GenericConstraint, PropertyGroup):
#     value: FloatProperty()
#     type = 'DISTANCE_PROJ'
#     name = 'Projected Distance'
#     signature = ((SlvsPoint3D, ), (SlvsPoint3D, ))
##
#     def needs_wp(self):
#         return WpReq.OPTIONAL
#
#     def create_slvs_data(self, solvesys):
#         return solvesys.distance_proj(self.entity1.py_data, self.entity2.py_data, self.value)
#
# slvs_entity_pointer(SlvsDistanceProj, "entity1")
# slvs_entity_pointer(SlvsDistanceProj, "entity1")
# slvs_entity_pointer(SlvsDistanceProj, "sketch")


class SlvsConstraints(PropertyGroup):

    _dimensional_constraints = (
        SlvsDistance,
        SlvsAngle,
        SlvsDiameter,
    )

    _geometric_constraints = (
        SlvsCoincident,
        SlvsEqual,
        SlvsParallel,
        SlvsHorizontal,
        SlvsVertical,
        SlvsTangent,
        SlvsMidpoint,
        SlvsPerpendicular,
        SlvsRatio,
    )

    _constraints = (
        SlvsCoincident,
        SlvsEqual,
        SlvsDistance,
        SlvsAngle,
        SlvsDiameter,
        SlvsParallel,
        SlvsHorizontal,
        SlvsVertical,
        SlvsTangent,
        SlvsMidpoint,
        SlvsPerpendicular,
        SlvsRatio,
        # SlvsSymmetric,
    )

    __annotations__ = {
        cls.type.lower(): CollectionProperty(type=cls) for cls in _constraints
    }

    @classmethod
    def cls_from_type(cls, type: str):
        for constraint in cls._constraints:
            if type == constraint.type:
                return constraint
        return None

    def new_from_type(self, type: str) -> GenericConstraint:
        """Create a constraint by type.

        Arguments:
            type: Type of the constraint to be created.
        """
        name = type.lower()
        constraint_list = getattr(self, name)
        return constraint_list.add()

    def get_lists(self):
        lists = []
        for entity_list in self.rna_type.properties:
            name = entity_list.identifier
            if name in ("name", "rna_type"):
                continue
            lists.append(getattr(self, name))
        return lists

    def get_list(self, type: str):
        return getattr(self, type.lower())

    def get_from_type_index(self, type: str, index: int) -> GenericConstraint:
        """Get constraint by type and local index.

        Arguments:
            type: Constraint's type.
            index: Constraint's local index.

        Returns:
            GenericConstraint: Constraint with the given type and index or None if not found.
        """
        list = getattr(self, type.lower())
        if not list or index >= len(list):
            return None
        return list[index]

    def get_index(self, constr: GenericConstraint) -> int:
        """Get the index of a constraint in its collection.

        Arguments:
            constr: Constraint to get the index for.

        Returns:
            int: Index of the constraint or -1 if not found.
        """
        list = getattr(self, constr.type.lower())
        for i, item in enumerate(list):
            if item == constr:
                return i
        return -1

    def remove(self, constr: GenericConstraint):
        """Remove a constraint.

        Arguments:
            constr: Constraint to be removed.
        """
        i = self.get_index(constr)
        self.get_list(constr.type).remove(i)

    @property
    def dimensional(self):
        for constraint_type in self._dimensional_constraints:
            for entity in self.get_list(constraint_type.type):
                yield entity

    @property
    def geometric(self):
        for constraint_type in self._geometric_constraints:
            for entity in self.get_list(constraint_type.type):
                yield entity

    @property
    def all(self):
        for entity_list in self.get_lists():
            for entity in entity_list:
                yield entity

    def add_coincident(
        self,
        entity1: SlvsGenericEntity,
        entity2: SlvsGenericEntity,
        sketch: SlvsSketch = None,
    ) -> SlvsCoincident:
        """Add a coincident constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.

        Returns:
            SlvsCoincident: The created constraint.
        """

        if all([type(e) in point for e in (entity1, entity2)]):
            # TODO: Implicitly merge points
            return

        c = self.coincident.add()
        c.entity1 = entity1
        c.entity2 = entity2
        if sketch:
            c.sketch = sketch
        return c

    def add_equal(
        self,
        entity1: SlvsGenericEntity,
        entity2: SlvsGenericEntity,
        sketch: Union[SlvsSketch, None] = None,
    ) -> SlvsEqual:
        """Add an equal constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.

        Returns:
            SlvsEqual: The created constraint.
        """
        c = self.equal.add()
        c.entity1 = entity1
        c.entity2 = entity2
        if sketch is not None:
            c.sketch = sketch
        return c

    def add_distance(
        self,
        entity1: SlvsGenericEntity,
        entity2: SlvsGenericEntity,
        sketch: Union[SlvsSketch, None] = None,
        init: bool = False,
    ) -> SlvsDistance:
        """Add a distance constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.
            init: Initialize the constraint based on the given entities.

        Returns:
            SlvsDistance: The created constraint.
        """
        c = self.distance.add()
        c.entity1 = entity1
        c.entity2 = entity2
        if sketch is not None:
            c.sketch = sketch
        if init:
            c.init_props()
        return c

    def add_angle(
        self,
        entity1: SlvsGenericEntity,
        entity2: SlvsGenericEntity,
        sketch: SlvsSketch = None,
        init: bool = False,
    ) -> SlvsAngle:
        """Add an angle constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.
            init: Initialize the constraint based on the given entities.

        Returns:
            SlvsAngle: The created constraint.
        """
        c = self.angle.add()
        c.entity1 = entity1
        c.entity2 = entity2
        if sketch is not None:
            c.sketch = sketch
        if init:
            c.init_props()
        return c

    def add_diameter(
        self, entity1: SlvsGenericEntity, sketch: SlvsSketch = None, init: bool = False
    ) -> SlvsDiameter:
        """Add a diameter constraint.

        Arguments:
            entity1: -
            sketch: The sketch this constraint belongs to.
            init: Initialize the constraint based on the given entities.

        Returns:
            SlvsDiameter: The created constraint.
        """
        c = self.diameter.add()
        c.entity1 = entity1
        if sketch:
            c.sketch = sketch
        if init:
            c.init_props()
        return c

    def add_parallel(
        self,
        entity1: SlvsGenericEntity,
        entity2: SlvsGenericEntity,
        sketch: Union[SlvsSketch, None] = None,
    ) -> SlvsParallel:
        """Add a parallel constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.

        Returns:
            SlvsParallel: The created constraint.
        """
        c = self.parallel.add()
        c.entity1 = entity1
        c.entity2 = entity2
        if sketch is not None:
            c.sketch = sketch
        return c

    def add_horizontal(
        self, entity1: SlvsGenericEntity, sketch: Union[SlvsSketch, None] = None
    ) -> SlvsHorizontal:
        """Add a horizontal constraint.

        Arguments:
            entity1: -
            sketch: The sketch this constraint belongs to.

        Returns:
            SlvsHorizontal: The created constraint.
        """
        c = self.horizontal.add()
        c.entity1 = entity1
        if sketch is not None:
            c.sketch = sketch
        return c

    def add_vertical(
        self, entity1: SlvsGenericEntity, sketch: Union[SlvsSketch, None] = None
    ) -> SlvsVertical:
        """Add a vertical constraint.

        Arguments:
            entity1: -
            sketch: The sketch this constraint belongs to.

        Returns:
            SlvsVertical: The created constraint.
        """
        c = self.vertical.add()
        c.entity1 = entity1
        if sketch is not None:
            c.sketch = sketch
        return c

    def add_tangent(
        self,
        entity1: SlvsGenericEntity,
        entity2: SlvsGenericEntity,
        sketch: Union[SlvsSketch, None] = None,
    ) -> SlvsTangent:
        """Add a tangent constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.

        Returns:
            SlvsTangent: The created constraint.
        """
        c = self.tangent.add()
        c.entity1 = entity1
        c.entity2 = entity2
        if sketch is not None:
            c.sketch = sketch
        return c

    def add_midpoint(
        self,
        entity1: SlvsGenericEntity,
        entity2: SlvsGenericEntity,
        sketch: Union[SlvsSketch, None] = None,
    ) -> SlvsMidpoint:
        """Add a midpoint constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.

        Returns:
            SlvsMidpoint: The created constraint.
        """
        c = self.midpoint.add()
        c.entity1 = entity1
        c.entity2 = entity2
        if sketch is not None:
            c.sketch = sketch
        return c

    def add_perpendicular(
        self,
        entity1: SlvsGenericEntity,
        entity2: SlvsGenericEntity,
        sketch: Union[SlvsSketch, None] = None,
    ) -> SlvsPerpendicular:
        """Add a perpendicular constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.

        Returns:
            SlvsPerpendicular: The created constraint.
        """
        c = self.perpendicular.add()
        c.entity1 = entity1
        c.entity2 = entity2
        if sketch is not None:
            c.sketch = sketch
        return c

    def add_ratio(
        self,
        entity1: SlvsGenericEntity,
        entity2: SlvsGenericEntity,
        sketch: Union[SlvsSketch, None] = None,
        init: bool = False,
    ) -> SlvsRatio:
        """Add a ratio constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.
            init: Initialize the constraint based on the given entities.

        Returns:
            SlvsRatio: The created constraint.
        """
        c = self.ratio.add()
        c.entity1 = entity1
        c.entity2 = entity2
        if sketch is not None:
            c.sketch = sketch
        if init:
            c.init_props()
        return c


for cls in SlvsConstraints._constraints:
    name = cls.type.lower()
    func_name = "add_" + name

    # Create constraint collections
    annotations = {}
    if hasattr(SlvsConstraints, "__annotations__"):
        annotations = SlvsConstraints.__annotations__.copy()


class SketcherProps(PropertyGroup):
    """The base structure for CAD Sketcher"""

    entities: PointerProperty(type=SlvsEntities)
    constraints: PointerProperty(type=SlvsConstraints)
    show_origin: BoolProperty(name="Show Origin Entities")
    selectable_constraints: BoolProperty(
        name="Constraints Selectability",
        default=True,
        options={"SKIP_SAVE"},
        update=functions.update_cb,
    )

    version: IntVectorProperty(
        name="Addon Version",
        description="CAD Sketcher addon version this scene was saved with",
    )

    # This is needed for the sketches ui list
    ui_active_sketch: IntProperty()

    @property
    def all(self) -> Generator[Union[SlvsGenericEntity, SlvsConstraints], None, None]:
        """Iterate over entities and constraints of every type"""
        for entity in self.entities.all:
            yield entity
        for constraint in self.constraints.all:
            yield constraint

    def solve(self, context: Context):
        return solve_system(context)

    def purge_stale_data(self):
        global_data.hover = -1
        global_data.selected.clear()
        global_data.batches.clear()
        for e in self.entities.all:
            e.dirty = True


slvs_entity_pointer(SketcherProps, "active_sketch", update=functions.update_cb)


classes = (
    *SlvsConstraints._constraints,
    SlvsConstraints,
    SketcherProps,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.sketcher = PointerProperty(type=SketcherProps)
    bpy.types.Object.sketch_index = IntProperty(name="Parent Sketch", default=-1)


def unregister():
    del bpy.types.Object.sketch_index
    del bpy.types.Scene.sketcher

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
