"""Solver that reads/writes native curve data directly.

Builds solvespace entities from curve attributes (positions, sketch_type,
start_point_id, end_point_id, center_point_id) and writes solved positions
back to curve points. No Slvs* entity read/write needed for geometry.

Structural entities (workplane, normal) still come from the entity system.
Constraints still come from PropertyGroups (referencing entities for now).
"""
import logging
from mathutils import Vector, Matrix as _Matrix

import math

from .model.constants import SketchCurveType
from .utilities.curve_data import (
    get_curve_index, get_curve_data,
    invalidate_curve_id_cache, get_curve_midpoints,
)
from .utilities.workplane import ensure_workplane_empty
from .utilities.constants import FULL_TURN, HALF_TURN

logger = logging.getLogger(__name__)


class CurveSolver:
    """Solver that operates on native curve data."""

    group_fixed = 1
    group_sketch = 3

    def __init__(self, context, sketch):
        self.context = context
        self.sketch = sketch

        import slvs
        slvs.clear_sketch()
        self.solvesys = slvs

        self.ok = True
        self.result = None

        # Tweak state
        self._tweak_curve_id = None
        self._tweak_pos = None

        # Mapping: curve_id → solvespace handle (for points)
        self._point_handles = {}
        # Mapping: curve_id → solvespace handle (for all entities)
        self._entity_handles = {}
        # For circle radius params
        self._distance_params = {}

    def tweak(self, curve_id, pos):
        """Set the curve to be dragged to the given position."""
        self._tweak_curve_id = curve_id
        self._tweak_pos = pos

    def _init_workplane(self):
        """Initialize the workplane from the workplane empty object.

        Falls back to entity workplane if no empty exists yet.
        """
        wp_obj = ensure_workplane_empty(self.sketch)

        # Fallback: curve object's parent
        if not wp_obj and self.sketch.target_object and self.sketch.target_object.parent:
            wp_obj = self.sketch.target_object.parent

        if wp_obj:
            mat = wp_obj.matrix_world
            origin_loc = mat.translation
            quat = mat.to_quaternion()
        elif hasattr(self.sketch, 'wp') and self.sketch.wp:
            origin_loc = self.sketch.wp.p1.location
            quat = self.sketch.wp.nm.orientation
        else:
            # Default to XY plane at origin
            from mathutils import Quaternion
            origin_loc = (0.0, 0.0, 0.0)
            quat = Quaternion()

        origin_handle = self.solvesys.add_point_3d(
            self.group_fixed, *origin_loc
        )
        normal_handle = self.solvesys.add_normal_3d(
            self.group_fixed, quat.w, quat.x, quat.y, quat.z
        )
        wp_handle = self.solvesys.add_workplane(
            self.group_fixed, origin_handle, normal_handle
        )

        if hasattr(self.sketch, 'wp') and self.sketch.wp:
            self.sketch.wp.p1.py_data = origin_handle
            self.sketch.wp.nm.py_data = normal_handle
            self.sketch.wp.py_data = wp_handle

        self._wp_handle = wp_handle
        self._normal_handle = normal_handle

    def _init_geometry(self):
        """Build solvespace entities from curve data."""
        sketch = self.sketch
        if not sketch.target_object or not sketch.target_object.data:
            return

        curve_data = sketch.target_object.data
        n_curves = len(curve_data.curves)
        if n_curves == 0:
            return

        cid_attr = curve_data.attributes.get("curve_id")
        type_attr = curve_data.attributes.get("sketch_type")
        fix_attr = curve_data.attributes.get("fixed")
        sp_attr = curve_data.attributes.get("start_point_id")
        ep_attr = curve_data.attributes.get("end_point_id")
        cp_attr = curve_data.attributes.get("center_point_id")

        if not cid_attr or not type_attr:
            return

        wp = self._wp_handle

        from .utilities.curve_data import is_fixed as _is_fixed

        # First pass: create all points
        for curve_idx in range(n_curves):
            ctype = type_attr.data[curve_idx].value
            if ctype != SketchCurveType.POINT:
                continue

            cid = cid_attr.data[curve_idx].value
            fixed = _is_fixed(self.sketch, cid)
            group = self.group_fixed if fixed else self.group_sketch

            pt_idx = curve_data.curves[curve_idx].points[0].index
            pos = curve_data.points[pt_idx].position
            u, v = float(pos[0]), float(pos[1])

            handle = self.solvesys.add_point_2d(group, u, v, wp)
            self._point_handles[cid] = handle
            self._entity_handles[cid] = handle

        # Second pass: create lines, arcs, circles
        for curve_idx in range(n_curves):
            ctype = type_attr.data[curve_idx].value
            cid = cid_attr.data[curve_idx].value

            if ctype == SketchCurveType.LINE:
                sp_id = sp_attr.data[curve_idx].value if sp_attr else 0
                ep_id = ep_attr.data[curve_idx].value if ep_attr else 0

                p1_handle = self._point_handles.get(sp_id)
                p2_handle = self._point_handles.get(ep_id)
                if p1_handle and p2_handle:
                    handle = self.solvesys.add_line_2d(
                        self.group_sketch, p1_handle, p2_handle, wp
                    )
                    self._entity_handles[cid] = handle

            elif ctype == SketchCurveType.CIRCLE:
                cp_id = cp_attr.data[curve_idx].value if cp_attr else 0
                ct_handle = self._point_handles.get(cp_id)
                if ct_handle:
                    # Get radius from curve geometry
                    ct_pos = Vector(curve_data.points[
                        curve_data.curves[get_curve_index(sketch, cp_id)].points[0].index
                    ].position)
                    first_pt = curve_data.curves[curve_idx].points[0].index
                    edge_pos = Vector(curve_data.points[first_pt].position)
                    radius = (edge_pos - ct_pos).length

                    dist_param = self.solvesys.add_distance(
                        self.group_sketch, radius, wp
                    )
                    handle = self.solvesys.add_circle(
                        self.group_sketch, self._normal_handle,
                        ct_handle, dist_param, wp
                    )
                    self._entity_handles[cid] = handle
                    self._distance_params[cid] = dist_param

            elif ctype == SketchCurveType.ARC:
                cp_id = cp_attr.data[curve_idx].value if cp_attr else 0
                sp_id = sp_attr.data[curve_idx].value if sp_attr else 0
                ep_id = ep_attr.data[curve_idx].value if ep_attr else 0

                ct_handle = self._point_handles.get(cp_id)
                p1_handle = self._point_handles.get(sp_id)
                p2_handle = self._point_handles.get(ep_id)
                if ct_handle and p1_handle and p2_handle:
                    handle = self.solvesys.add_arc(
                        self.group_sketch, self._normal_handle,
                        ct_handle, p1_handle, p2_handle, wp
                    )
                    self._entity_handles[cid] = handle

        # Third pass: handle tweak (after all entities exist)
        if self._tweak_curve_id is not None and self._tweak_pos is not None:
            tweak_handle = self._entity_handles.get(self._tweak_curve_id)
            if tweak_handle:
                wp_obj = self.sketch.workplane_object
                if not wp_obj and self.sketch.target_object:
                    wp_obj = self.sketch.target_object.parent
                if wp_obj:
                    wp_mat = wp_obj.matrix_world
                else:
                    from mathutils import Matrix
                    wp_mat = Matrix.Identity(4)
                tw_u, tw_v, _ = wp_mat.inverted() @ self._tweak_pos
                drag_pt = self.solvesys.add_point_2d(
                    self.group_sketch, tw_u, tw_v, wp
                )
                # For points: coincident point-to-point
                # For lines/arcs/circles: coincident point-on-entity
                self.solvesys.coincident(
                    self.group_sketch, drag_pt, tweak_handle, wp
                )
                self.solvesys.dragged(self.group_sketch, drag_pt, wp)

    def _init_constraints(self):
        """Initialize constraints using curve_id handles."""
        sketch = self.sketch
        sketch_obj = sketch.target_object if hasattr(sketch, 'target_object') else sketch
        wp = self._wp_handle

        # Iterate constraints from the sketch's own data
        if not sketch_obj or not sketch_obj.data:
            return
        sketch_constraints = sketch_obj.data.sketch_constraints

        for c in sketch_constraints.all:
            group = self.group_sketch
            c.failed = False

            if not getattr(c, 'curve_id_1', 0):
                continue

            try:
                c.create_slvs_data_from_curves(
                    self.solvesys, self._entity_handles, wp, group
                )
            except Exception as e:
                logger.debug(f"Constraint init failed: {c}, {e}")

    def _rebuild_arc_bezier(self, curve_data, curve_idx, center_pos, is_cyclic):
        """Rebuild arc/circle bezier handles from solved point positions.

        Replicates create_bezier_curve logic without entity references.
        """
        curve_slice = curve_data.curves[curve_idx]
        n_points = curve_slice.points_length
        first = curve_slice.points[0].index

        # Collect point positions
        positions = []
        for i in range(n_points):
            positions.append(Vector(curve_data.points[first + i].position[:2]))

        center = Vector(center_pos[:2])

        # Compute radius and angle
        radius = (positions[0] - center).length
        if radius < 1e-6:
            return

        if is_cyclic:
            angle_per_segment = FULL_TURN / n_points
            segment_count = n_points
        else:
            # Compute total angle from start to end
            start_vec = positions[0] - center
            end_vec = positions[-1] - center
            from .utilities.math import range_2pi
            total_angle = range_2pi(
                math.atan2(end_vec[1], end_vec[0]) - math.atan2(start_vec[1], start_vec[0])
            )
            segment_count = n_points - 1
            if segment_count == 0:
                return
            angle_per_segment = total_angle / segment_count

        # Compute handle offset (standard bezier circle approximation)
        n = FULL_TURN / angle_per_segment if angle_per_segment != 0 else 0
        if n == 0:
            return
        q = (4 / 3) * math.tan(HALF_TURN / (2 * n))
        base_offset = Vector((radius, q * radius))

        # Compute midpoint positions for multi-segment arcs
        if not is_cyclic and segment_count > 1:
            start_angle = math.atan2(start_vec[1], start_vec[0])
            for i in range(1, segment_count):
                a = start_angle + angle_per_segment * i
                positions[i] = center + Vector((radius * math.cos(a), radius * math.sin(a)))

        # Build locations list
        locations = list(positions)
        if is_cyclic:
            locations.append(locations[0])

        # Set positions and handles
        attrs = curve_data.attributes
        hl = attrs.get("handle_left")
        hr = attrs.get("handle_right")
        if not hl or not hr:
            return

        bezier_indices = list(range(first, first + n_points))
        if is_cyclic:
            bezier_indices.append(first)

        for seg in range(segment_count):
            loc1, loc2 = locations[seg], locations[seg + 1]
            b1_idx, b2_idx = bezier_indices[seg], bezier_indices[seg + 1]

            coords = []
            for i, loc in enumerate((loc1, loc2)):
                pos = loc - center
                angle = math.atan2(pos[1], pos[0])
                offset = base_offset.copy()
                if i == 1:
                    offset[1] *= -1
                offset.rotate(_Matrix.Rotation(angle, 2))
                coords.append((center + offset).to_3d())

            hr.data[b1_idx].vector = coords[0]
            hl.data[b2_idx].vector = coords[1]
            curve_data.points[b2_idx].position = loc2.to_3d()

            if not is_cyclic:
                if seg == 0:
                    pos = loc1 - center
                    angle = math.atan2(pos[1], pos[0])
                    offset = base_offset.copy()
                    offset[1] *= -1
                    offset.rotate(_Matrix.Rotation(angle, 2))
                    hl.data[b1_idx].vector = (center + offset).to_3d()
                if seg == segment_count - 1:
                    pos = loc2 - center
                    angle = math.atan2(pos[1], pos[0])
                    offset = base_offset.copy()
                    offset.rotate(_Matrix.Rotation(angle, 2))
                    hr.data[b2_idx].vector = (center + offset).to_3d()

        # Set start point position
        curve_data.points[first].position = positions[0].to_3d()

    def _get_solved_point_position(self, curve_id):
        """Get solved position for a point curve_id."""
        handle = self._point_handles.get(curve_id)
        if not handle:
            return None
        u = self.solvesys.get_param_value(handle['param'][0])
        v = self.solvesys.get_param_value(handle['param'][1])
        return (u, v, 0.0)

    def _write_results(self):
        """Write solved positions back to curve data."""
        sketch = self.sketch
        if not sketch.target_object or not sketch.target_object.data:
            return

        curve_data = sketch.target_object.data
        n_curves = len(curve_data.curves)
        cid_attr = curve_data.attributes.get("curve_id")
        type_attr = curve_data.attributes.get("sketch_type")
        sp_attr = curve_data.attributes.get("start_point_id")
        ep_attr = curve_data.attributes.get("end_point_id")
        cp_attr = curve_data.attributes.get("center_point_id")

        # First pass: update all point positions
        for curve_idx in range(n_curves):
            ctype = type_attr.data[curve_idx].value
            cid = cid_attr.data[curve_idx].value

            if ctype == SketchCurveType.POINT:
                pos = self._get_solved_point_position(cid)
                if pos:
                    pt_idx = curve_data.curves[curve_idx].points[0].index
                    curve_data.points[pt_idx].position = pos

        # Second pass: update circle/arc edge positions from solved radius
        for curve_idx in range(n_curves):
            ctype = type_attr.data[curve_idx].value
            cid = cid_attr.data[curve_idx].value

            if ctype == SketchCurveType.CIRCLE and cid in self._distance_params:
                dist_param = self._distance_params[cid]
                param_h = dist_param.get('param', [0])[0]
                solved_radius = self.solvesys.get_param_value(param_h) if param_h else None
                cp_id = cp_attr.data[curve_idx].value if cp_attr else 0
                if cp_id and solved_radius is not None:
                    ct_pos = self._get_solved_point_position(cp_id)
                    if ct_pos:
                        # Update first edge point at new radius
                        curve_slice = curve_data.curves[curve_idx]
                        first = curve_slice.points[0].index
                        curve_data.points[first].position = (
                            ct_pos[0] + solved_radius, ct_pos[1], ct_pos[2]
                        )

        # Third pass: rebuild segments from updated point positions
        from .utilities.curve_data import rebuild_segments
        rebuild_segments(sketch)

        # Sync entity.co from solved curve positions (bridge for gizmo positioning)
        # TODO: Remove when gizmos read from curve data directly
        entities = self.context.scene.sketcher.entities
        seg_attr = curve_data.attributes.get("segment_entity_index")
        if seg_attr:
            for curve_idx in range(n_curves):
                entity_index = seg_attr.data[curve_idx].value
                if entity_index == 0:
                    continue
                entity = entities.get(entity_index)
                if entity is None:
                    continue
                ctype = type_attr.data[curve_idx].value
                if ctype == SketchCurveType.POINT and hasattr(entity, 'co'):
                    pt_idx = curve_data.curves[curve_idx].points[0].index
                    pos = curve_data.points[pt_idx].position
                    entity.co = (pos[0], pos[1])
                elif ctype == SketchCurveType.CIRCLE:
                    dist = self._distance_params.get(cid_attr.data[curve_idx].value)
                    if dist and hasattr(entity, 'radius'):
                        entity.radius = self.solvesys.get_param_value(dist['param'][0])

    def solve(self):
        """Run the solver on curve data."""
        self._init_workplane()
        self._init_geometry()
        self._init_constraints()

        result = self.solvesys.solve_sketch(self.group_sketch, True)

        if isinstance(result, dict):
            retval = result
        else:
            retval, *_ = result

        from .global_data import solver_state_items
        from .utilities.bpy import bpyEnum

        result_code = retval['result']
        self.ok = result_code == 0 or result_code == 4

        if result_code > 4:
            self.result = bpyEnum(solver_state_items, index=5)
        else:
            self.result = bpyEnum(solver_state_items, index=result_code)

        self.sketch.solver_state = self.result.identifier
        self.sketch.dof = retval.get('dof', 0)

        if self.ok:
            self._write_results()

        return self.ok


Solver = CurveSolver


def solve_sketch_from_curves(context, sketch):
    """Convenience function to solve a sketch using curve data."""
    if not sketch:
        return False
    solver = CurveSolver(context, sketch)
    return solver.solve()


def solve_system(context, sketch=None):
    """Solve the constraint system for a sketch."""
    if sketch and sketch.target_object and sketch.target_object.data:
        if len(sketch.target_object.data.curves) > 0:
            return solve_sketch_from_curves(context, sketch)
    logger.warning("solve_system called without native curve data, skipping")
    return True
