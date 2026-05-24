import json
import logging

import bpy
from bpy.types import Operator
from bpy.props import IntProperty, EnumProperty
from bpy.utils import register_classes_factory
from mathutils import Matrix, Vector

from ..declarations import Operators
from ..model.types import SlvsLine2D
from .utilities import activate_sketch

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reference-plane picker popup
# ---------------------------------------------------------------------------

# Module-level cache populated in invoke() so the EnumProperty callback works.
_ref_plane_items: list = [("-", "—  (none)", "", 0)]
_ref_plane_sketch_indices: list = []  # slvs_index values, in sorted order


def _get_ref_plane_items(self, context):
    return _ref_plane_items


class View3D_OT_slvs_pick_reference_planes(Operator):
    """Project linked geometry lines from same-tag reference planes into the
    new linked sketch. Each plane up to and including the chosen one
    contributes one fixed construction line (the source line's endpoints
    projected onto that plane along the new sketch's normal)."""

    bl_idname = Operators.PickReferencePlanes
    bl_label = "Add Reference Plane Projections"
    bl_options = {"UNDO"}

    new_sketch_index: IntProperty(name="New Sketch Index", default=-1)
    source_line_index: IntProperty(name="Source Line Index", default=-1)
    upto_plane: EnumProperty(
        name="Up to plane",
        description=(
            "Create linked geometry projections for every same-tag plane up "
            "to and including this one (ordered nearest → farthest along the "
            "sketch's local Z).  Choose '—  (none)' to skip."
        ),
        items=_get_ref_plane_items,
    )

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def invoke(self, context, event):
        global _ref_plane_items, _ref_plane_sketch_indices

        sse = context.scene.sketcher.entities
        new_sketch = sse.get(self.new_sketch_index)
        source_line = sse.get(self.source_line_index)
        if new_sketch is None or source_line is None:
            return self.execute(context)

        # Use the SOURCE sketch's normal as the ray direction: it is
        # perpendicular to the source plane and will intersect other planes
        # that have the SAME tag as the source (e.g. Elevation→Elevation).
        source_sketch = source_line.sketch
        source_tag = getattr(source_sketch, "tag", "")
        ray_dir = source_sketch.wp.normal.copy()
        source_origin = source_sketch.wp.p1.location.copy()

        # Candidates: same tag as the SOURCE sketch, restricted to one side
        # of the source plane along its normal:
        #   Plan   source → planes in the +normal direction (dist > 0)
        #   Elevation source → planes in the -normal direction (dist < 0)
        # Sorted by distance from closest to farthest.
        sign = -1.0 if source_tag == "Elevation" else 1.0
        candidates = []
        for sk in sse.sketches:
            if sk.slvs_index == source_sketch.slvs_index:
                continue
            if sk.slvs_index == self.new_sketch_index:
                continue
            if getattr(sk, "tag", "") != source_tag:
                continue
            raw = (sk.wp.p1.location - source_origin).dot(ray_dir)
            dist = sign * raw  # positive means "in the wanted direction"
            if dist > 1e-4:
                candidates.append((dist, sk))

        candidates.sort(key=lambda x: x[0])
        _ref_plane_sketch_indices = [sk.slvs_index for _, sk in candidates]

        # Build enum items: first entry is always the "none" option.
        _ref_plane_items = [("-", "—  (none)", "", 0)]
        for i, (dist, sk) in enumerate(candidates):
            label = "{} ({:.3f} m)".format(sk.name, dist)
            _ref_plane_items.append((str(sk.slvs_index), label, "", i + 1))

        if len(_ref_plane_items) == 1:
            # No candidate planes — nothing to show.
            return self.execute(context)

        return context.window_manager.invoke_props_dialog(self, width=340)

    def draw(self, context):
        self.layout.prop(self, "upto_plane", text="Up to plane")

    def execute(self, context):
        if self.upto_plane == "-":
            return {"FINISHED"}

        sse = context.scene.sketcher.entities
        new_sketch = sse.get(self.new_sketch_index)
        source_line = sse.get(self.source_line_index)
        if new_sketch is None or source_line is None:
            self.report({"ERROR"}, "Invalid sketch or source line index")
            return {"CANCELLED"}

        # Ray travels along the SOURCE sketch's normal (same as in invoke).
        source_sketch = source_line.sketch
        ray_dir = source_sketch.wp.normal.copy()
        wp_mat_inv = new_sketch.wp.matrix_basis.inverted()

        p1_world = source_line.p1.location.copy()
        p2_world = source_line.p2.location.copy()

        # Walk the ordered list and stop after the selected plane.
        target_idx = int(self.upto_plane)
        for plane_idx in _ref_plane_sketch_indices:
            on_sketch = sse.get(plane_idx)
            if on_sketch is None:
                continue

            on_origin = on_sketch.wp.p1.location.copy()
            on_normal = on_sketch.wp.normal.copy()
            denom = on_normal.dot(ray_dir)
            if abs(denom) < 1e-8:
                logger.debug("Ray parallel to plane %s — skipping", on_sketch.name)
                if plane_idx == target_idx:
                    break
                continue

            # Ray-plane intersection for p1 and p2 of the source line.
            t1 = on_normal.dot(on_origin - p1_world) / denom
            onp1_world = p1_world + t1 * ray_dir

            t2 = on_normal.dot(on_origin - p2_world) / denom
            onp2_world = p2_world + t2 * ray_dir

            # Convert world positions to new sketch's local 2-D coordinates.
            onp1_local = wp_mat_inv @ onp1_world
            onp2_local = wp_mat_inv @ onp2_world

            # Add fixed linked points and the connecting line.
            pt1 = sse.add_point_2d((onp1_local.x, onp1_local.y), new_sketch)
            pt1.fixed = True
            pt1.linked = True

            pt2 = sse.add_point_2d((onp2_local.x, onp2_local.y), new_sketch)
            pt2.fixed = True
            pt2.linked = True

            ext_line = sse.add_line_2d(pt1, pt2, new_sketch)
            ext_line.fixed = True
            ext_line.linked = True

            logger.debug(
                "Added reference projection from '%s' into '%s'",
                on_sketch.name,
                new_sketch.name,
            )

            if plane_idx == target_idx:
                break

        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Main operator
# ---------------------------------------------------------------------------


class View3D_OT_slvs_add_linked_sketch(Operator):
    """Create a new linked sketch whose plane is orthogonal to the source sketch. \
The selected line's p1->p2 direction becomes the X axis of the new sketch \
and the source sketch's normal becomes the Y axis. \
The line is mirrored as fixed construction geometry along the new X axis"""

    bl_idname = Operators.AddLinkedSketch
    bl_label = "add linked sketch"
    bl_options = {"UNDO"}

    line_index: IntProperty(
        name="Line Index",
        description="slvs_index of the source Line2D",
        default=-1,
    )

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def execute(self, context):
        sse = context.scene.sketcher.entities

        # Resolve source line
        line = sse.get(self.line_index)
        if not isinstance(line, SlvsLine2D):
            self.report({"ERROR"}, "No valid Line2D selected")
            return {"CANCELLED"}

        # --- Compute linked sketch coordinate frame ---
        origin_3d = line.p1.location.copy()
        p2_3d = line.p2.location.copy()
        line_vec = p2_3d - origin_3d
        line_length = line_vec.length

        if line_length < 1e-8:
            self.report({"ERROR"}, "Source line has zero length")
            return {"CANCELLED"}

        x_new = line_vec.normalized()
        # Source sketch normal becomes new Y axis (keeps planes orthogonal)
        y_new = line.sketch.wp.normal.copy()
        z_new = x_new.cross(y_new).normalized()
        # Re-orthogonalise y against z to guard float drift
        y_new = z_new.cross(x_new).normalized()

        # For an Elevation source the resulting plan workplane must face
        # downward, so flip the local z axis.
        if getattr(line.sketch, "tag", "") == "Elevation":
            z_new = -z_new
            y_new = z_new.cross(x_new).normalized()

        # Rotation matrix whose columns are the new basis vectors
        mat3 = Matrix((x_new, y_new, z_new)).transposed()
        quat = mat3.to_quaternion()

        # --- Build 3D workplane primitives ---
        origin_pt = sse.add_point_3d(tuple(origin_3d))
        nm = sse.add_normal_3d(tuple(quat))
        wp = sse.add_workplane(origin_pt, nm)

        # Align workplane rect with the linked geometry line:
        # start at origin, extend right by line_length, upward by workplane size.
        wp.linked_wp_width = line_length

        # --- Create sketch ---
        new_sketch = sse.add_sketch(wp)
        new_sketch.source_line_i = line.slvs_index
        source_role = getattr(line.sketch, "tag", "")
        if source_role == "Plan":
            new_sketch.tag = "Elevation"
        elif source_role == "Elevation":
            new_sketch.tag = "Plan"

        if new_sketch.tag in {"Plan", "Elevation"}:
            wp.tag = new_sketch.tag

        # Fixed sketch origin coinciding with the workplane origin
        p_origin = sse.add_point_2d((0.0, 0.0), new_sketch)
        p_origin.fixed = True
        p_origin.linked = True

        # Linked geometry: fixed line along X axis mirroring the source line
        p_end = sse.add_point_2d((line_length, 0.0), new_sketch)
        p_end.fixed = True
        p_end.linked = True

        ext_line = sse.add_line_2d(p_origin, p_end, new_sketch)
        ext_line.fixed = True
        ext_line.linked = True

        new_sketch.source_linked_line_i = ext_line.slvs_index

        # --- Points constrained to the source line → linked geometry references ---
        # Any point in the source sketch that is coincident with (or midpoint of)
        # the source line is projected along the line direction onto the new sketch's
        # X axis and added as a fixed linked point.  This lets the user snap to
        # door/window positions, column grid intersections, etc. while drawing.
        _seen_pt_indices = {line.p1.slvs_index, line.p2.slvs_index}
        for _constraint_col in (
            context.scene.sketcher.constraints.coincident,
            context.scene.sketcher.constraints.midpoint,
        ):
            for _c in _constraint_col:
                # PropertyGroup pointers are different Python objects even when
                # they reference the same entity, so compare by slvs_index.
                if _c.entity2.slvs_index != line.slvs_index:
                    continue
                _pt = _c.entity1
                if not _pt.is_point():
                    continue
                if _pt.slvs_index in _seen_pt_indices:
                    continue
                _seen_pt_indices.add(_pt.slvs_index)
                _t = (_pt.location - origin_3d).dot(x_new)
                _ext_pt = sse.add_point_2d((_t, 0.0), new_sketch)
                _ext_pt.fixed = True
                _ext_pt.linked = True
                if getattr(_pt, "tag", ""):
                    _ext_pt.tag = _pt.tag
                if getattr(_pt, "guid", ""):
                    _ext_pt.guid = _pt.guid
                logger.debug("Added linked reference point at X=%.4f from %s", _t, _pt)

        # --- IFC IfcWall: pre-populate height and build elevation reference rectangle ---
        if context.scene.sketcher.ifc_integration:
            line_tag = getattr(line, "tag", "")
            line_guid = getattr(line, "guid", "")
            if line_tag == "IfcWall" and line_guid:
                wall_height = None
                try:
                    import bonsai.tool as _bonsai_tool
                    import ifcopenshell.util.representation as _ifc_rep
                    import ifcopenshell.util.unit as _ifc_unit

                    ifc_file = _bonsai_tool.Ifc.get()
                    if ifc_file:
                        existing = ifc_file.by_guid(line_guid)
                        if existing:
                            unit_scale = _ifc_unit.calculate_unit_scale(ifc_file)
                            body = _ifc_rep.get_representation(
                                existing, "Model", "Body", "MODEL_VIEW"
                            )
                            if body:
                                for rep_item in body.Items:
                                    if rep_item.is_a("IfcExtrudedAreaSolid"):
                                        wall_height = rep_item.Depth * unit_scale
                                        break
                except Exception:
                    pass

                if wall_height and wall_height > 1e-6:
                    wp.linked_wp_height = wall_height

                    p_top_end = sse.add_point_2d((line_length, wall_height), new_sketch)
                    p_top_origin = sse.add_point_2d((0.0, wall_height), new_sketch)

                    right_line = sse.add_line_2d(p_end, p_top_end, new_sketch)
                    top_line = sse.add_line_2d(p_top_end, p_top_origin, new_sketch)
                    left_line = sse.add_line_2d(p_top_origin, p_origin, new_sketch)

                    elev_poly = sse.add_polyline(
                        [
                            ext_line.slvs_index,
                            right_line.slvs_index,
                            top_line.slvs_index,
                            left_line.slvs_index,
                        ],
                        True,
                        new_sketch,
                    )
                    elev_poly.tag = line_tag
                    elev_poly.guid = line_guid

        activate_sketch(context, new_sketch.slvs_index, self)

        # _toggle_local_view hides all workplanes when entering sketch mode and
        # saves their pre-sketch visibility for later restore.  Because the new
        # workplane was created AFTER the state was saved (we are already inside
        # the parent sketch), it is absent from the saved dict and its current
        # value (False, set by the hide step) would be restored on exit instead
        # of True.  Patch the saved dict now so the workplane is visible once
        # the user leaves sketch mode.
        _WP_PROP = "slvs_pre_sketch_wp_visible"
        _wp_str = context.scene.get(_WP_PROP)
        if _wp_str is not None:
            try:
                _wp_state = json.loads(_wp_str)
                _wp_state[str(wp.slvs_index)] = True
                context.scene[_WP_PROP] = json.dumps(_wp_state)
            except Exception:
                pass

        self.target = new_sketch

        logger.debug("Added linked sketch: {}".format(new_sketch))

        # Invite the user to pick reference planes for cross-projection.
        bpy.ops.view3d.slvs_pick_reference_planes(
            "INVOKE_DEFAULT",
            new_sketch_index=new_sketch.slvs_index,
            source_line_index=line.slvs_index,
        )

        return {"FINISHED"}


register, unregister = register_classes_factory(
    (View3D_OT_slvs_pick_reference_planes, View3D_OT_slvs_add_linked_sketch)
)
