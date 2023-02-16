import math

from bpy.types import Gizmo, GizmoGroup
from mathutils import Matrix

from ..declarations import Gizmos, GizmoGroups
from ..model.types import SlvsAngle
from ..utilities.constants import QUARTER_TURN
from ..utilities.draw import coords_arc_2d
from ..utilities.math import pol2cart
from ..utilities.view import get_scale_from_pos
from .base import ConstraintGenericGGT, ConstraintGizmoGeneric
from .utilities import draw_arrow_shape, get_arrow_size, get_overshoot


class VIEW3D_GGT_slvs_angle(GizmoGroup, ConstraintGenericGGT):
    bl_idname = GizmoGroups.Angle
    bl_label = "Angle Constraint Gizmo Group"

    type = SlvsAngle.type
    gizmo_type = Gizmos.Angle


class VIEW3D_GT_slvs_angle(Gizmo, ConstraintGizmoGeneric):
    bl_idname = Gizmos.Angle
    type = SlvsAngle.type

    bl_target_properties = ({
        "id": "offset",
        "type": "FLOAT",
        "array_length": 1,
    },)

    __slots__ = (
        "custom_shape",
        "index",
    )

    def _get_helplines(self, context, constr, scale_1, scale_2):
        angle = abs(constr.value)
        radius = self.target_get_value("offset")

        overshoot_1 = get_overshoot(scale_1, radius)
        overshoot_2 = get_overshoot(scale_2, radius)
        return (
            (0.0, 0.0),
            pol2cart(radius - overshoot_1, angle / 2),
            (0.0, 0.0),
            pol2cart(radius - overshoot_2, -angle / 2),
        )

    def _create_shape(self, context, constr, select=False):
        def get_arrow_angle():
            # The arrowheads are placed on an arc spanning between the
            #     witness lines, and we want them to point "along" this arc.
            # So we rotate the arrowhead by a quarter-turn plus (or minus)
            #     half the amount the arc segment underneath it rotates.
            segment = length / abs(radius)
            rotation = (
                (QUARTER_TURN + segment / 2)
                if constr.text_inside()
                else (QUARTER_TURN - segment / 2)
            )
            return rotation

        rv3d = context.region_data

        # note: radius is signed value, but
        # angle, length, lengths[], widths[] are all absolute values
        radius = self.target_get_value("offset")
        angle = abs(constr.value)
        half_angle = angle / 2
        p1 = pol2cart(radius, -half_angle)
        p2 = pol2cart(radius, half_angle)

        scales = []
        # Length is limited to no more than 1/3 the span
        lengths, widths = [], []
        for p in (p1, p2):
            scale = get_scale_from_pos(self.matrix_world @ p.to_3d(), rv3d)
            scales.append(scale)

            length = min(
                abs(get_arrow_size(radius, scale)[0]),
                abs(radius * (angle / 3)),
            )
            lengths.append(length)
            widths.append(length * 0.4)

        arrow_angle = get_arrow_angle()

        p1_s = p1.copy()
        p1_s.rotate(Matrix.Rotation(arrow_angle, 2, "Z"))
        p1_s.length = lengths[0]

        p2_s = p2.copy()
        p2_s.rotate(Matrix.Rotation(-arrow_angle, 2, "Z"))
        p2_s.length = lengths[1]

        if constr.text_inside():
            coords = (
                *draw_arrow_shape(p1, p1 + p1_s, widths[0]),
                *coords_arc_2d(
                    0,
                    0,
                    radius,
                    32,
                    angle=angle,
                    offset=-half_angle,
                    type="LINES",
                ),
                *draw_arrow_shape(p2, p2 + p2_s, widths[1]),
                *(
                    self._get_helplines(context, constr, *scales)
                    if not select
                    else ()
                ),
            )
        else:
            leader_end = (
                constr.draw_outset
            )  # signed angle, measured from the Constrained Angle's bisector
            leader_start = math.copysign(half_angle, -leader_end)
            leader_length = leader_end - leader_start
            coords = (
                *draw_arrow_shape(p1, p1 - p1_s, widths[0]),
                *coords_arc_2d(
                    0,
                    0,
                    radius,
                    16,
                    angle=leader_length,
                    offset=leader_start,
                    type="LINES",
                ),
                *draw_arrow_shape(p2, p2 - p2_s, widths[1]),
                *(
                    self._get_helplines(context, constr, *scales)
                    if not select
                    else ()
                ),
            )

        self.custom_shape = self.new_custom_shape("LINES", coords)
