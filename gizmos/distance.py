import math

from bpy.types import Gizmo, GizmoGroup
from mathutils import Vector
from mathutils.geometry import distance_point_to_plane, intersect_point_line

from ..declarations import GizmoGroups, Gizmos
from ..model.types import SlvsDistance
from ..model.workplane import SlvsWorkplane
from ..utilities.view import get_scale_from_pos
from .base import ConstraintGenericGGT, ConstraintGizmoGeneric
from .utilities import draw_arrow_shape, get_arrow_size, get_overshoot


def _position(entity):
    if hasattr(entity, "co"):
        return Vector(entity.co)
    return Vector(entity.location)


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
        "_shape_sig",
    )

    def _get_helplines(self, context, constr, scale_1, scale_2):
        ui_scale = context.preferences.system.ui_scale
        dist = constr.value / 2 / ui_scale
        offset = self.target_get_value("offset")
        entity1 = constr._resolved_entity(1)
        entity2 = constr._resolved_entity(2)
        if entity1 is None:
            return ((0, 0, 0),) * 4
        if entity1.is_line():
            entity1, entity2 = entity1.p1, entity1.p2
        if entity2 is None:
            return ((0, 0, 0),) * 4

        # Get constraints points in local space and adjust helplines
        # based on their position
        mat_inv = constr.matrix_basis().inverted()

        def get_local(point):
            point = Vector(point)
            if len(point) == 2:
                point = point.to_3d()
            return (mat_inv @ point) / ui_scale

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
                return ((0, 0, 0),) * 4

            targetvec = targetpoint - centerpoint
            if targetvec.length == 0:
                return ((0, 0, 0),) * 4
            points_local.append(
                get_local(centerpoint + entity1.radius * targetvec / targetvec.length)
            )

        else:
            points_local.append(get_local(_position(entity1)))

        # Add endpoint for entity2 helpline
        if entity2.is_point():
            points_local.append(get_local(_position(entity2)))

        elif entity2.is_line():
            line_points = (
                get_local(_position(entity2.p1)),
                get_local(_position(entity2.p2)),
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

        elif isinstance(entity2, SlvsWorkplane):
            p1 = _position(entity1)
            normal = Vector(entity2.normal).normalized()
            signed_distance = distance_point_to_plane(
                p1, entity2.p1.location, normal
            )
            points_local.append(get_local(p1 - normal * signed_distance))

        # Pick the points based on their x location
        if len(points_local) < 2:
            return ((0, 0, 0),) * 4
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
                Vector((outset, offset, 0)),
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
