import math

from bpy.types import Gizmo, GizmoGroup
from mathutils import Vector
from mathutils.geometry import intersect_point_line

from ..declarations import GizmoGroups, Gizmos
from ..model.types import SlvsDistance
from ..utilities.view import get_scale_from_pos
from .base import ConstraintGenericGGT, ConstraintGizmoGeneric
from .utilities import draw_arrow_shape, get_arrow_size, get_overshoot


class VIEW3D_GGT_slvs_distance(GizmoGroup, ConstraintGenericGGT):
    bl_idname = GizmoGroups.Distance
    bl_label = "Distance Constraint Gizmo Group"

    type = SlvsDistance.type
    gizmo_type = Gizmos.Distance


class VIEW3D_GT_slvs_distance(Gizmo, ConstraintGizmoGeneric):
    bl_idname = Gizmos.Distance
    type = SlvsDistance.type

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
        ui_scale = context.preferences.system.ui_scale
        dist = constr.value / 2 / ui_scale
        offset = self.target_get_value("offset")
        entity1, entity2 = constr.entity1, constr.entity2
        if entity1.is_line():
            entity1, entity2 = entity1.p1, entity1.p2

        # Get constraints points in local space and adjust helplines
        # based on their position
        mat_inv = constr.matrix_basis().inverted()

        def get_local(point):
            return (mat_inv @ point.to_3d()) / ui_scale

        # Store the two endpoints of the helplines in local space
        points_local = []

        # Add endpoint for entity1 helpline
        if entity1.is_curve():
            centerpoint = entity1.ct.co

            if entity2.is_point():
                targetpoint = entity2.co
            elif entity2.is_line():
                targetpoint, _ = intersect_point_line(
                    centerpoint, entity2.p1.co, entity2.p2.co
                )
            else:
                # TODO: Handle the case for SlvsWorkplane
                pass

            targetvec = targetpoint - centerpoint
            points_local.append(get_local(
                centerpoint + entity1.radius * targetvec / targetvec.length
            ))

        else:
            points_local.append(get_local(entity1.location))

        # Add endpoint for entity2 helpline
        if entity2.is_point():
            points_local.append(get_local(entity2.location))

        elif entity2.is_line():
            line_points = (
                get_local(entity2.p1.location),
                get_local(entity2.p2.location),
            )
            line_points_side = [pos.y - offset > 0 for pos in line_points]

            x = math.copysign(dist, line_points[0].x)
            y = offset

            if line_points_side[0] != line_points_side[1]:
                # Distance line is between line points
                y = offset
            else:
                # Get the closest point
                points_delta = [abs(p.y - offset) for p in line_points]
                i = int(points_delta[0] > points_delta[1])
                y = line_points[i].y
            points_local.append(Vector((x, y, 0.0)))

        # Pick the points based on their x location
        if points_local[0].x > points_local[1].x:
            point_right, point_left = points_local
        else:
            point_right, point_left = reversed(points_local)

        overshoot_1 = offset + get_overshoot(scale_1, point_left.y - offset)
        overshoot_2 = offset + get_overshoot(scale_2, point_right.y - offset)

        return (
            (-dist, overshoot_1, 0.0),
            (-dist, point_left.y, 0.0),
            (dist, overshoot_2, 0.0),
            (dist, point_right.y, 0.0),
        )

    def _create_shape(self, context, constr, select=False):
        rv3d = context.region_data
        ui_scale = context.preferences.system.ui_scale

        half_dist = constr.value / 2 / ui_scale
        offset = self.target_get_value("offset")
        outset = constr.draw_outset

        p1 = Vector((-half_dist, offset, 0.0))
        p2 = Vector((half_dist, offset, 0.0))
        if not constr.text_inside(ui_scale):
            p1, p2 = p2, p1
        p1_global, p2_global = [self.matrix_world @ p for p in (p1, p2)]

        scale_1, scale_2 = [
            get_scale_from_pos(p, rv3d)
            for p in (p1_global, p2_global)
        ]

        arrow_1 = get_arrow_size(half_dist, scale_1)
        arrow_2 = get_arrow_size(half_dist, scale_2)

        if constr.text_inside(ui_scale):
            coords = (
                *draw_arrow_shape(
                    p1, p1 + Vector((arrow_1[0], 0, 0)), arrow_1[1], is_3d=True
                ),
                p1,
                p2,
                *draw_arrow_shape(
                    p2, p2 - Vector((arrow_2[0], 0, 0)), arrow_2[1], is_3d=True
                ),
                *(
                    self._get_helplines(context, constr, scale_1, scale_2)
                    if not select
                    else ()
                ),
            )
        else:  # the same thing, but with a little jitter to the outside
            coords = (
                *draw_arrow_shape(
                    p1, p1 + Vector((arrow_1[0], 0, 0)), arrow_1[1], is_3d=True
                ),
                p1,
                # jitter back and forth to extend leader line for
                # text_outside case but it is unnecessary work for
                # text_inside case
                Vector(
                    (outset, offset, 0)
                ),
                p1,
                p2,
                *draw_arrow_shape(
                    p2, p2 - Vector((arrow_2[0], 0, 0)), arrow_2[1], is_3d=True
                ),
                *(
                    self._get_helplines(context, constr, scale_1, scale_2)
                    if not select
                    else ()
                ),
            )

        self.custom_shape = self.new_custom_shape("LINES", coords)
