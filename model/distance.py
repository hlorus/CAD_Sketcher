import logging
import math

from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    StringProperty,
)
from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory
from mathutils import Matrix, Vector
from mathutils.geometry import intersect_point_line

from ..curve_solver import Solver
from ..global_data import WpReq
from ..utilities import preferences
from ..utilities.bpy import bpyEnum
from ..utilities.math import range_2pi
from ..utilities.solver import update_system_cb
from ..utilities.view import location_3d_to_region_2d
from .arc import SlvsArc
from .base_constraint import DimensionalConstraint
from .categories import CURVE, LINE, POINT, POINT2D
from .circle import SlvsCircle
from .line_2d import SlvsLine2D
from .line_3d import SlvsLine3D
from .point_2d import SlvsPoint2D
from .point_3d import SlvsPoint3D
from .utilities import slvs_entity_pointer
from .workplane import SlvsWorkplane

logger = logging.getLogger(__name__)


def get_side_of_line(line_start, line_end, point):
    line_end = line_end - line_start
    point = point - line_start
    return -(
        (line_end.x - line_start.x) * (point.y - line_start.y)
        - (line_end.y - line_start.y) * (point.x - line_start.x)
    )


def _get_aligned_distance(p_1, p_2, alignment):
    if alignment == "HORIZONTAL":
        return abs(p_2.co.x - p_1.co.x)
    if alignment == "VERTICAL":
        return abs(p_2.co.y - p_1.co.y)
    return (p_2.co - p_1.co).length


align_items = [
    ("NONE", "None", "", 0),
    ("HORIZONTAL", "Horizontal", "", 1),
    ("VERTICAL", "Vertical", "", 2),
]


def _get_value(self):
    if self.is_reference:
        val = self.init_props(align=self.align)["value"]
        return self.to_displayed_value(val)
    import bpy

    scene = bpy.context.scene
    uid = getattr(self, "constraint_uid", "")
    if scene is not None and uid:
        key = f"slvs:c:{uid}"
        if key in scene:
            return self.to_displayed_value(float(scene[key]))
    val = self.init_props(align=self.align).get("value", 0.0)
    return self.to_displayed_value(val)


class SlvsDistance(DimensionalConstraint, PropertyGroup):
    """Sets the distance between a point and some other entity (point/line/Workplane)."""

    def _set_value_force(self, value):
        DimensionalConstraint._set_value_force(self, abs(value))

    def _set_align(self, value):
        if isinstance(value, str):
            alignment = value
        else:
            alignment = bpyEnum(align_items, value).identifier
        self.align_store = alignment
        r1, r2 = self.ref(1), self.ref(2)
        if r1 and r2:
            self._set_value_force(_get_aligned_distance(r1, r2, alignment))

    def _get_align(self) -> int:
        if not self.is_property_set("align_store"):
            return 0
        return bpyEnum(align_items, identifier=self.align_store).index

    label = "Distance"
    value_store: FloatProperty(
        name="Value Storage",
        subtype="DISTANCE",
        unit="LENGTH",
        precision=6,
    )
    align_store: EnumProperty(
        name="Align Storage",
        items=align_items,
    )
    value: FloatProperty(
        name=label,
        subtype="DISTANCE",
        unit="LENGTH",
        precision=6,
        update=update_system_cb,
        get=_get_value,
        set=DimensionalConstraint._set_value,
    )
    flip: BoolProperty(name="Flip", update=update_system_cb)
    align: EnumProperty(
        name="Align",
        items=align_items,
        update=update_system_cb,
        get=_get_align,
        set=_set_align,
    )
    draw_offset: FloatProperty(name="Draw Offset", default=0.3)
    draw_outset: FloatProperty(name="Draw Outset", default=0.0)
    type = "DISTANCE"
    signature = ((*POINT, *LINE, SlvsCircle, SlvsArc), (*POINT, *LINE, SlvsWorkplane))
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
            return (POINT2D, (*POINT2D, SlvsLine2D))[index]
        return cls.signature[index]

    curve_id_1: StringProperty(name="Curve ID 1", default="")
    curve_id_2: StringProperty(name="Curve ID 2", default="")

    def create_slvs_data_from_curves(self, solvesys, handle_map, wp, group):

        from ..model.constants import SketchCurveType
        from ..utilities.curve_data import get_curve_data, get_curve_position, get_uuid

        h1 = handle_map.get(self.curve_id_1)
        h2 = handle_map.get(self.curve_id_2)
        if h1 is None or h2 is None:
            return None

        sketch = self._get_sketch()
        cd, idx1, _ = get_curve_data(sketch, self.curve_id_1)
        _, idx2, _ = get_curve_data(sketch, self.curve_id_2)
        if cd is None:
            return None

        type_attr = cd.attributes.get("sketch_type")

        t1 = type_attr.data[idx1].value
        t2 = type_attr.data[idx2].value if idx2 is not None else -1

        value = self.get_value()

        # Line entity1 → use start point as e1
        if t1 == SketchCurveType.LINE:
            sp_id = get_uuid(cd, "start_point_id", idx1)
            h1 = handle_map.get(sp_id)
            if h1 is None:
                return None

        # Curve/arc entity1 → measure from its edge, i.e. constrain the centre a
        # radius further out. A curve entity2 adds its own radius too, so the
        # value is the edge-to-edge gap along the line of centres.
        if t1 in (SketchCurveType.ARC, SketchCurveType.CIRCLE):
            from mathutils import Vector

            def _center_radius(index):
                cid = get_uuid(cd, "center_point_id", index)
                handle = handle_map.get(cid)
                pos = get_curve_position(sketch, cid)
                if not handle or not pos:
                    return None, 0.0
                slice_ = cd.curves[index]
                edge = Vector(cd.points[slice_.points[0].index].position)
                return handle, (edge - Vector(pos)).length

            ct1_handle, r1 = _center_radius(idx1)
            if ct1_handle is None:
                return None

            if t2 in (SketchCurveType.ARC, SketchCurveType.CIRCLE):
                ct2_handle, r2 = _center_radius(idx2)
                if ct2_handle is None:
                    return None
                return solvesys.distance(
                    group, ct1_handle, ct2_handle, value + r1 + r2, wp
                )

            return solvesys.distance(group, ct1_handle, h2, value + r1, wp)

        # Point-to-line or point-to-point
        if t2 == SketchCurveType.LINE:
            return solvesys.distance(group, h1, h2, value, wp)

        if t2 == SketchCurveType.POINT:
            alignment = self.align
            if self.use_align() and alignment != "NONE":
                p1_pos = get_curve_position(sketch, self.curve_id_1)
                p2_pos = get_curve_position(sketch, self.curve_id_2)
                if p1_pos and p2_pos:
                    p = solvesys.add_point_2d(group, p2_pos[0], p1_pos[1], wp)
                    handles = []
                    handles.append(solvesys.horizontal(group, p, wp, entityB=h2))
                    handles.append(solvesys.vertical(group, p, wp, entityB=h1))
                    base = h1 if alignment == "VERTICAL" else h2
                    handles.append(solvesys.distance(group, p, base, value, wp))
                    return handles

            return solvesys.distance(group, h1, h2, value, wp)

        return solvesys.distance(group, h1, h2, value, wp)

    def needs_wp(self):
        if isinstance(self.entity2, SlvsWorkplane):
            return WpReq.FREE
        return WpReq.OPTIONAL

    def use_flipping(self):
        # Only use flipping for constraint between point and line/workplane
        r1, r2 = self.ref(1), self.ref(2)
        if not r1 or not r2:
            return False
        if r1.is_curve():
            return False
        return r2.is_line()

    def use_align(self):
        """Returns True if constraint's entities allow distance to be aligned"""
        r1, r2 = self.ref(1), self.ref(2)
        if not r1 or not r2:
            return False
        if r2.is_line():
            return False
        if r1.is_curve():
            return False
        return True

    def is_align(self):
        """Returns True if constraint is aligned"""
        return self.use_align() and self.align != "NONE"

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
        align = self.is_align()
        handles = []

        value = self.get_value()

        # circle/arc -> line/point
        if type(e1) in CURVE:
            # TODO: make Horizontal and Vertical alignment work
            if type(e2) in LINE:
                return solvesys.distance(
                    group, e1.ct.py_data, e2.py_data, value + e1.radius, wp
                )
            else:
                assert isinstance(e2, SlvsPoint2D)
                return solvesys.distance(
                    group, e1.ct.py_data, e2.py_data, value + e1.radius, wp
                )

        elif type(e2) in LINE:
            func = solvesys.distance
            set_wp = True
        elif isinstance(e2, SlvsWorkplane):
            func = solvesys.distance
        elif type(e2) in POINT:
            if align and all([e.is_2d() for e in (e1, e2)]):
                # Get Point in between
                p1, p2 = e1.co, e2.co
                coords = (p2.x, p1.y)

                p = solvesys.add_point_2d(group, *coords, wp)

                handles.append(solvesys.horizontal(group, p, wp, entityB=e2.py_data))
                handles.append(solvesys.vertical(group, p, wp, entityB=e1.py_data))

                base_point = e1 if alignment == "VERTICAL" else e2
                handles.append(
                    solvesys.distance(group, p, base_point.py_data, value, wp)
                )
                return handles
            else:
                func = solvesys.distance
            set_wp = True

        args = []
        if set_wp:
            args.append(self.get_workplane())

        return func(group, e1.py_data, e2.py_data, value, *args)

    def matrix_basis(self):
        r1, r2 = self.ref(1), self.ref(2)
        if not r1 or not r1.valid:
            return Matrix()
        return self._compute_matrix_basis(r1, r2, r1.wp_matrix)

    def _compute_matrix_basis(self, e1, e2, wp_mat):
        """Compute matrix_basis from geometry accessors (CurveRef or entity)."""
        x_axis = Vector((1, 0))
        alignment = self.align
        align = self.is_align()
        angle = 0

        # Curve-to-curve: the gap is measured edge-to-edge along the line of
        # centres, so place the label between the two facing edge points.
        if e1.is_curve() and e2 is not None and e2.is_curve():
            c1, c2 = e1.ct.co, e2.ct.co
            axis = c2 - c1
            axis = axis.normalized() if axis.length else x_axis
            edge1 = c1 + e1.radius * axis
            edge2 = c2 - e2.radius * axis
            rot = axis.angle_signed(x_axis) if axis.length else 0.0
            mat_rot = Matrix.Rotation(rot, 2, "Z")
            v_translation = (edge1 + edge2) / 2
            mat_local = Matrix.Translation(v_translation.to_3d()) @ mat_rot.to_4x4()
            return wp_mat @ mat_local

        # Resolve p1 and p2 as 2D positions
        if e1.is_curve():
            centerpoint = e1.ct.co
            if e2.is_line():
                p2, _ = intersect_point_line(centerpoint, e2.p1.co, e2.p2.co)
            else:
                p2 = e2.co
            if (p2 - centerpoint).length > 0:
                vec = (p2 - centerpoint) / (p2 - centerpoint).length
                p1 = centerpoint + (e1.radius * Vector(vec))
            else:
                p1 = e2.p1.co
        elif e1.is_line():
            p1, p2 = e1.p1.co, e1.p2.co
            # For the type check below, treat as point-point
            e1, e2 = e1.p1, e1.p2
        else:
            p1 = e1.co

        if e2.is_point():
            p2 = e2.co
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
            mat_rot = Matrix.Rotation(angle, 2, "Z")
            v_translation = (p2 + p1) / 2

        elif e2.is_line():
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
                mat_rot = Matrix.Rotation(angle, 2, "Z")
                v_translation = (p2 + p1) / 2
            else:
                orig = e2.p1.co
                end = e2.p2.co
                vec = end - orig
                angle = (math.tau / 4) + range_2pi(math.atan2(vec[1], vec[0]))
                mat_rot = Matrix.Rotation(angle, 2, "Z")
                p1 = p1 - orig
                v_translation = orig + (p1 + p1.project(vec)) / 2

        mat_local = Matrix.Translation(v_translation.to_3d()) @ mat_rot.to_4x4()
        return wp_mat @ mat_local

    def _get_init_value(self, alignment):
        r1, r2 = self.ref(1), self.ref(2)
        if not r1:
            if self.is_property_set("value_store"):
                return self.value_store
            return 0.0

        if r1.is_line():
            return _get_aligned_distance(r1.p1, r1.p2, alignment)
        if r1.is_curve():
            centerpoint = r1.ct.co
            # Curve-to-curve: edge-to-edge gap along the line of centres.
            if r2 and r2.is_curve():
                return (centerpoint - r2.ct.co).length - r1.radius - r2.radius
            if r2 and r2.is_line():
                endpoint, _ = intersect_point_line(centerpoint, r2.p1.co, r2.p2.co)
            elif r2 and r2.is_point():
                endpoint = r2.co
            else:
                return 0.0
            return (centerpoint - endpoint).length - r1.radius
        if r2 and r2.is_line():
            orig = r2.p1.co
            end = r2.p2.co - orig
            p1 = r1.co - orig
            return math.copysign(
                (p1 - p1.project(end)).length,
                get_side_of_line(r2.p1.co, r2.p2.co, r1.co),
            )
        if r2 and r2.is_point():
            return _get_aligned_distance(r1, r2, alignment)
        return 0.0

    def init_props(self, **kwargs):

        # NOTE: Flip is currently ignored when passed in kwargs
        alignment = kwargs.get("align")
        retval = {}

        value = kwargs.get("value", self._get_init_value(alignment))

        if self.use_flipping() and value < 0:
            value = abs(value)
            retval["flip"] = not self.flip

        retval["value"] = value
        retval["align"] = alignment
        return retval

    def text_inside(self, ui_scale):
        return (ui_scale * abs(self.draw_outset)) < self.value / 2

    def update_draw_offset(self, pos, ui_scale):
        self.draw_offset = pos[1] / ui_scale
        self.draw_outset = pos[0] / ui_scale

    def draw_props(self, layout):
        sub = super().draw_props(layout)

        if self.use_flipping():
            sub.prop(self, "flip")

        sub.label(text="Alignment:")
        row = sub.row()
        row.enabled = self.use_align()
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

register, unregister = register_classes_factory((SlvsDistance,))
