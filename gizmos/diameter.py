from bpy.types import Gizmo, GizmoGroup

from ..declarations import Gizmos, GizmoGroups
from ..model.types import SlvsDiameter
from ..utilities.constants import HALF_TURN
from ..utilities.math import pol2cart
from ..utilities.view import get_scale_from_pos
from .base import ConstraintGenericGGT, ConstraintGizmoGeneric
from .utilities import draw_arrow_shape, get_arrow_size


class VIEW3D_GGT_slvs_diameter(GizmoGroup, ConstraintGenericGGT):
    bl_idname = GizmoGroups.Diameter
    bl_label = "Diameter Gizmo Group"

    type = SlvsDiameter.type
    gizmo_type = Gizmos.Diameter


class VIEW3D_GT_slvs_diameter(Gizmo, ConstraintGizmoGeneric):
    bl_idname = Gizmos.Diameter
    type = SlvsDiameter.type

    bl_target_properties = ({
        "id": "offset",
        "type": "FLOAT",
        "array_length": 1,
    },)

    __slots__ = (
        "custom_shape",
        "index",
    )

    def _create_shape(self, context, constr, select=False):
        ui_scale = context.preferences.system.ui_scale
        angle = constr.leader_angle
        offset = constr.draw_offset / ui_scale
        dist = constr.radius / ui_scale

        rv3d = context.region_data

        p1 = pol2cart(-dist, angle)
        p2 = pol2cart(dist, angle)

        p1_global, p2_global = [
            self.matrix_world @ p.to_3d()
            for p in (p1, p2)
        ]
        scale_1, scale_2 = [
            get_scale_from_pos(p, rv3d)
            for p in (p1_global, p2_global)
        ]

        arrow_1 = get_arrow_size(dist, scale_1)
        arrow_2 = get_arrow_size(dist, scale_2)

        if constr.setting:
            # RADIUS_MODE:
            #   drawn inside and outside as a single segment
            if constr.text_inside():
                coords = (
                    *draw_arrow_shape(
                        p2, pol2cart(dist - arrow_2[0], angle), arrow_2[1]
                    ),
                    p2,
                    (0, 0),
                )
            else:
                coords = (
                    *draw_arrow_shape(
                        p2, pol2cart(arrow_2[0] + dist, angle), arrow_2[1]
                    ),
                    p2,
                    pol2cart(offset, angle),
                )

        else:
            # DIAMETER_MODE:
            #   drawn inside as a single segment
            #   drawn outside as a 2-segment gizmo
            if constr.text_inside():
                coords = (
                    *draw_arrow_shape(
                        p1, pol2cart(arrow_2[0] - dist, angle), arrow_2[1]
                    ),
                    p1,
                    p2,
                    *draw_arrow_shape(
                        p2, pol2cart(dist - arrow_2[0], angle), arrow_2[1]
                    ),
                )
            else:
                coords = (
                    *draw_arrow_shape(
                        p2, pol2cart(arrow_1[0] + dist, angle), arrow_1[1]
                    ),
                    p2,
                    pol2cart(offset, angle),
                    pol2cart(
                        dist + (3 * arrow_2[0]), angle + HALF_TURN
                    ),  # limit length to 3 arrowheads
                    p1,
                    *draw_arrow_shape(
                        p1,
                        pol2cart(dist + arrow_2[0], angle + HALF_TURN),
                        arrow_2[1],
                    ),
                )

        self.custom_shape = self.new_custom_shape("LINES", coords)
