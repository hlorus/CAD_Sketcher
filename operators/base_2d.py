import math
from typing import Any, List, Optional

import bpy
from bpy.props import StringProperty
from bpy.types import Context, Event
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

from ..model.curve_ref import CurveRef, PointRef, curve_ref
from ..model.types import SlvsPoint2D
from ..utilities.collections import is_editable
from ..utilities.view import get_blender_snap_info, get_pos_2d, get_scale_from_pos
from .base_stateful import GenericEntityOp
from .placement import MIDPOINT, PointPlacement, ProjectionRequest, placement_of
from .utilities import ignore_hover


def _view_region(context: Context):
    """The 3D view the tool was drawn in, as ``(region, region_data)``.

    Normally the running context's own, but a re-run from the redo panel has
    that panel's region instead, and a dimension placed from it would jump. So
    the screen's first 3D view stands in, keeping the placement put.
    """
    area = getattr(context, "area", None)
    if area is not None and area.type == "VIEW_3D" and context.region_data is not None:
        return context.region, context.region_data

    screen = getattr(context, "screen", None)
    for other in getattr(screen, "areas", ()):
        if other.type != "VIEW_3D":
            continue
        for region in other.regions:
            if region.type == "WINDOW":
                return region, other.spaces.active.region_3d
    return None, None


class Operator2d(GenericEntityOp):
    # Current geometry snap target (dict from get_blender_snap_info) or None,
    # updated as the cursor moves and drawn by the snap-marker handler.
    _snap = None
    _snap_handle = None

    @classmethod
    def poll(cls, context: Context):
        return context.scene.sketcher.active_sketch_object is not None

    def chain_scope(self, context: Context) -> str:
        """A chain point is only carried on from within the same sketch."""
        obj = context.scene.sketcher.active_sketch_object
        return obj.name if obj else ""

    def chain_point_valid(self, context: Context) -> bool:
        """Whether the point a chain was carried on from is still there."""
        try:
            point = self.get_point(context, 0)
        except (KeyError, AttributeError, RuntimeError):
            return False
        return point is not None and getattr(point, "valid", False)

    # A 2D draw operator only ever modifies the active sketch's curve data and
    # constraints -- not the entity system (structural workplane/normal/origin
    # entities). The base snapshot re-serialized and restored the whole scene
    # (137 entities in the #342 file) plus every sketch's curves on each
    # mouse-move (~15ms), the draw-time lag. Scope it to the active sketch's curve
    # data + constraints, skipping the scene serialization entirely.
    def create_snapshot(self, context: Context):
        from ..model.sketch_ref import get_active_sketch

        scene = context.scene
        sketch = get_active_sketch(context)
        obj = sketch.target_object if sketch else None
        snap = {
            "active_name": obj.name if obj else None,
            "constraint_values": {
                k: scene[k] for k in scene.keys() if str(k).startswith("slvs:c:")
            },
        }
        if obj and obj.data and is_editable(obj.data):
            from ..utilities.curve_data import capture_id_caches

            snap["curve_data"] = self._snapshot_curve_data(obj.data)
            snap["constraints"] = self._snapshot_constraints(obj.data)
            # Restoring puts the ids back exactly as they are now, so capture the
            # id caches once here and reinstate them on every restore.
            snap["id_caches"] = capture_id_caches(obj.data)
        return snap

    def restore_snapshot(self, context: Context, snapshot):
        if not snapshot:
            return
        from ..utilities.curve_data import install_id_caches

        scene = context.scene

        name = snapshot.get("active_name")
        obj = bpy.data.objects.get(name) if name else None
        if obj and obj.data and is_editable(obj.data) and "curve_data" in snapshot:
            self._restore_curve_data(obj.data, snapshot["curve_data"])
            # Only this sketch's data changed. Its ids are now exactly the
            # snapshot's, so reinstate the captured caches rather than clearing
            # every sketch's and re-deriving each hex id on the next lookup.
            install_id_caches(obj.data, snapshot.get("id_caches"))
            # Clear then restore: an empty constraints snapshot means "the sketch
            # had none", and _restore_constraints early-returns on empty -- so a
            # constraint added during the preview must be removed here, or it
            # would survive the undo (the pre-draw state had zero constraints).
            for coll in obj.data.sketch_constraints.get_lists():
                while len(coll) > 0:
                    coll.remove(0)
            self._restore_constraints(obj.data, snapshot.get("constraints", {}))

        # Re-apply dimensional values last (see base restore_snapshot / #564).
        for key, value in snapshot.get("constraint_values", {}).items():
            scene[key] = value

    def invoke(self, context: Context, event: Event):
        # Own a POST_PIXEL marker for the current snap target for the lifetime of
        # the modal (removed in _end), so it can never linger past the draw.
        from ..drawing.snap import draw_snap_marker

        self._snap = None
        # A re-pick from the redo panel picks an existing element; it never
        # snaps, and it ends through _end_edit rather than _end.
        if self.edit_state < 0:
            self._snap_handle = bpy.types.SpaceView3D.draw_handler_add(
                draw_snap_marker, (self, context), "WINDOW", "POST_PIXEL"
            )
        return super().invoke(context, event)

    def _remove_snap_handle(self):
        handle = getattr(self, "_snap_handle", None)
        if handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(handle, "WINDOW")
            self._snap_handle = None

    def _end(self, context: Context, succeede, *args, **kwargs):
        self._remove_snap_handle()
        return super()._end(context, succeede, *args, **kwargs)

    def _end_edit(self, context: Context, ok: bool):
        self._remove_snap_handle()
        return super()._end_edit(context, ok)

    def _update_pick_hover(self, context: Context, coords):
        # Gizmos don't hover-test while the re-pick modal runs; do it here.
        from ..drawing import picking, selection

        cid = picking.update_hover(context, coords)
        if cid != selection.hover:
            selection.hover = cid
            if context.area:
                context.area.tag_redraw()

    def init(self, context: Context, event: Event):
        from ..model.sketch_ref import get_active_sketch

        self._active_sketch = get_active_sketch(context)
        return True

    def batched_changes(self, context: Context):
        """Batch the sketch's curve changes for one live update.

        Every curve created outside a batch recomputes the weld ids of the whole
        sketch, and every point write rebuilds all segments. A rectangle preview
        creates 8 curves per mouse move, so that bookkeeping ran 8 times per move
        and grew with every shape already in the sketch. Inside a batch it is done
        once, when the batch closes, with the same end result.
        """
        from contextlib import nullcontext

        from ..utilities.curve_data import batch_update, is_batching

        sketch = self.sketch
        # Nested batches are not supported: an inner exit would end the outer one
        # early. A caller that already batches owns the rebuild.
        if sketch is None or sketch.target_object is None or is_batching(sketch):
            return nullcontext()
        return batch_update(sketch, track_writes=True)

    @property
    def sketch(self):
        # init() sets this on the invoke path; a redo-panel re-run is a fresh
        # instance that never ran init(), so fall back to the active sketch.
        active = getattr(self, "_active_sketch", None)
        if not active:
            from ..model.sketch_ref import get_active_sketch

            active = get_active_sketch(bpy.context)
            self._active_sketch = active
        return active

    def _get_wp(self):
        """The plane this sketch draws on: its workplane object, else its frame."""
        if not self.sketch:
            return None
        return self.sketch.workplane_object or self.sketch.plane_matrix

    def state_func(self, context: Context, coords):
        state = self.state
        wp = self._get_wp()
        self._snap = get_blender_snap_info(context, coords)
        pos = get_pos_2d(context, wp, coords, respect_snapping=True)

        placement = placement_of(self.state_data)
        # Remember whether this point landed on an external-geometry snap, so its
        # deferred creation can anchor it (fixed) — otherwise an inferred
        # constraint would drag the snapped point off target (see create_element).
        placement.snapped = self._snap is not None
        # Stash the snap target so create_element can live-project it (the marker
        # reflects the current position; at click this is the committed one).
        placement.snap = self._snap

        # Handle implicit properties based on state.types
        if SlvsPoint2D in state.types:
            return pos

        # Handle state property based on property type
        prop_name = self.state.property

        prop = self.rna_type.properties.get(prop_name)
        if not prop:
            return super().state_func(context, coords)

        # Handle vector type
        if prop.array_length > 1:
            return pos

        if prop.type in ("FLOAT", "INT"):
            # Take the delta between the state start position and current position in screenspace X-Axis
            # and scale the value by the zoom level at the state start position

            type_cast = float if prop.type == "FLOAT" else int
            old_pos = get_pos_2d(context, wp, self.state_init_coords)
            scale = get_scale_from_pos(old_pos, context.region_data) / 500
            return type_cast((coords.x - self.state_init_coords.x) * scale)

        return super().state_func(context, coords)

    def _link_placement(self, context: Context, placement: PointPlacement):
        """Decide what a placed point links to, projecting a snap target if needed.

        When a point is snapped onto external mesh geometry, create (or reuse) a
        live projected reference and set it as the constraint target, so the placed
        point tracks the source instead of being a dead static point:

        - vertex: project the vertex as a point; coincide the placed point on it.
        - along an edge: project the edge as a line; coincide the point on the line
          (point-on-line) so it slides along the edge.
        - edge midpoint: project the edge as a line; add a midpoint constraint so
          the point stays centered as the edge's endpoints track the source.

        Other snap types, and cases where the snapped feature can't be traced to an
        original one, fall back to the static point. Split into a decision and an
        apply step so the decision can be inspected without creating anything.
        """
        request = self._decide_link(context, placement)
        if request is not None:
            self._apply_projection(placement, request)

    def _decide_link(self, context: Context, placement: PointPlacement):
        """Set this move's link flags; return the projection to create, if any."""
        # Live-snap has its own toggle and does NOT depend on "Auto Constraints";
        # only the per-placement Shift bypass still opts out (place it raw).
        if (
            not context.scene.sketcher.use_snap_project
            or placement.skip_auto_constraints
        ):
            placement.reset_link()
            return None
        if placement.hovered:
            existing = curve_ref(self.sketch, placement.hovered)
            if existing is not None and existing.valid:
                if self._is_projected_reference(placement.hovered):
                    # A live projection from an earlier (non-current) state: its
                    # flags were set when projected, keep them. (Re-projecting is
                    # unnecessary while the curve is still valid.)
                    placement.projected = True
                    return None
                # A genuine pick of an existing sketch entity under the cursor
                # (e.g. a pointer tool's constrain target): a plain coincidence
                # that respects Auto Constraints, anchored only if it is fixed.
                placement.link_existing(
                    placement.hovered,
                    fixed=bool(getattr(existing, "fixed", False)),
                    projected=False,
                )
                return None
            # Stale: a projection wiped by the preview restore while its id lingers
            # here. Honoring it would coincide the endpoint to a deleted curve (a
            # dead static point, the "snaps but no live link" bug); clear it and
            # re-project below so the reference is recreated.
            placement.hovered = ""

        # Fresh (re)evaluation of this state: default to not-anchored, a plain
        # coincidence, and not-projected, so stale flags from a previous frame
        # (e.g. the cursor moved off a vertex/midpoint) are cleared. They are set
        # again when the projection is applied, only if the snap warrants it.
        placement.reset_link()

        snap = placement.snap
        if not snap:
            return None
        snap_type = snap.get("type")
        if snap_type not in ("VERTEX", "EDGE_MIDPOINT", "EDGE"):
            return None
        source = bpy.data.objects.get(snap.get("object") or "")
        if source is None or source.type not in ("MESH", "CURVES"):
            return None
        is_curve = source.type == "CURVES"

        # A mesh snap reports evaluated-mesh indices that must map back to the
        # original vertices (by persistent id when tagged, else an order-preserving
        # index). A curve snap reads the source's control points directly, so its
        # indices are already the originals -- no remap needed.
        from ..stateful_operator.utilities.geometry import get_evaluated_obj
        from ..utilities.projection_anchor import resolve_source_vertex_index

        eval_source = None if is_curve else get_evaluated_obj(context, source)

        def _orig(index):
            if is_curve:
                return index
            return resolve_source_vertex_index(source, eval_source, index)

        if snap_type == "VERTEX":
            v_index = snap.get("vertex_index")
            if v_index is None:
                return None
            vertices = (_orig(v_index),)
        else:  # EDGE_MIDPOINT or EDGE: project the edge as a live line
            edge = snap.get("edge_vertices")
            if not edge:
                return None
            vertices = (_orig(edge[0]), _orig(edge[1]))
        if any(v is None for v in vertices):
            return None
        return ProjectionRequest(
            snap_type=snap_type,
            source=source,
            vertices=vertices,
            world_point=snap.get("world_point"),
        )

    def _apply_projection(self, placement: PointPlacement, request):
        """Create the requested live projection and link the placement to it."""
        from ..utilities.projection_anchor import project_mesh_edge, project_mesh_vertex

        if request.snap_type == "VERTEX":
            # Place the point where the user snapped (the evaluated hit), so a
            # vertex-moving modifier doesn't leave it a frame behind the source.
            projected = project_mesh_vertex(
                self.sketch,
                request.source,
                request.vertices[0],
                construction=True,
                world_co=request.world_point,
            )
        else:
            projected = project_mesh_edge(
                self.sketch,
                request.source,
                request.vertices[0],
                request.vertices[1],
                construction=True,
            )

        if projected is not None and projected.valid:
            # The projection is geometry this draw just created, sitting exactly
            # under the cursor. Left pickable, the next hover test finds it and
            # the state becomes "pick that point" instead of "place a point":
            # state_data's curve_id is then the projection's, the per-move undo
            # deletes it, and the state is left pointing at a dead curve (the
            # endpoint jumping to the sketch origin). Every other tool does the
            # same for what it creates mid-draw.
            self._ignore_projection(projected)
            placement.hovered = projected.curve_id
            # This link IS a projection: its constraint is created regardless of
            # the Auto Constraints toggle (see add_coincident).
            placement.projected = True
            if request.snap_type == "EDGE_MIDPOINT":
                # Constrain the point to the edge's midpoint (POINT, LINE). The
                # projected line's endpoints track the source, and the midpoint
                # constraint keeps the point centered as they move. It fully pins
                # the point, so treat it as anchored for the alignment guard.
                placement.link_kind = MIDPOINT
                placement.anchored = True
            elif request.snap_type == "VERTEX":
                # Coincident to a FIXED point: an auto axis-alignment would fight
                # the fixed position, so flag it anchored (the line tool skips
                # alignment, as it does for two statically-fixed endpoints).
                placement.anchored = True
            # EDGE: point-on-line coincidence (default kind); the point can still
            # slide along the line, so it is not flagged anchored.

    @staticmethod
    def _ignore_projection(projected) -> None:
        """Make a live projection unpickable, endpoints included for a line."""
        from ..model.curve_ref import LineRef

        ignore_hover(projected.curve_id)
        if isinstance(projected, LineRef):
            for point in (projected.p1, projected.p2):
                if point is not None and point.valid:
                    ignore_hover(point.curve_id)

    def _is_projected_reference(self, curve_id: str) -> bool:
        """Whether ``curve_id`` is a live-projected reference, not a picked entity.

        A projected reference is a bound point, or a line whose endpoints are both
        bound. Distinguishes "our projection" (whose constraint bypasses the Auto
        Constraints toggle) from a genuine pick of a pre-existing sketch entity.
        """
        from ..model.curve_ref import LineRef, curve_ref
        from ..utilities.projection_anchor import iter_projected_point_bindings

        bound = {cid for cid, *_ in iter_projected_point_bindings(self.sketch)}
        if not bound:
            return False
        if curve_id in bound:
            return True
        ref = curve_ref(self.sketch, curve_id)
        if isinstance(ref, LineRef):
            p1, p2 = ref.p1, ref.p2
            return bool(p1 and p2 and p1.curve_id in bound and p2.curve_id in bound)
        return False

    def point_is_anchored(self, index: int) -> bool:
        """Whether the point placed for state ``index`` is pinned in place.

        True when the endpoint is a live-projected vertex/midpoint (coincident to a
        FIXED projected point) -- an auto axis-alignment on it would fight the fixed
        position. Used by tools that add alignment constraints to skip it.
        """
        return placement_of(self._state_data.get(index, {})).anchored

    # create element depending on mode
    def create_element(self, context: Context, values: List[Any], state, state_data):
        sketch = self.sketch
        loc = values[0]

        placement = placement_of(state_data)
        # Snapped onto external mesh geometry: live-project it and coincide, so
        # the point tracks the source. Registers the projected point as the
        # coincidence target below (behaves like snapping onto a sketch entity).
        self._link_placement(context, placement)

        # A point snapped to external geometry is a deliberate placement: fix it
        # so the solver keeps it there. Points snapped onto a sketch entity (or a
        # live-projected reference above) are pinned by the coincident constraint
        # below instead, so skip those.
        fixed = placement.snapped and not placement.hovered

        # Recreate a placed point under the id it had before (re-run from the
        # redo panel or a re-pick), so the op's stored identity stays valid.
        from ..utilities.curve_data import reusing_curve_ids

        with reusing_curve_ids(sketch, [state_data.get("curve_id", "")]):
            ref = PointRef.create(sketch, loc, fixed=fixed)
        cid = ref.curve_id

        self.add_coincident(context, ref, state, state_data)

        ignore_hover(cid)
        state_data["type"] = PointRef
        state_data["curve_id"] = cid
        return cid

    def preview_structure(self, context: Context):
        """The current placement inputs that decide what gets created and linked.

        Moving along the same target (free space, one line, one snapped edge)
        keeps the structure; a different hover, snap target or Shift state
        rebuilds.
        """
        data = self.state_data
        if data.get("is_numeric_edit", False):
            return None
        placement = placement_of(data)
        snap = placement.snap
        snap_target = None
        if snap:
            snap_target = (
                snap.get("type"),
                snap.get("object"),
                snap.get("vertex_index"),
                tuple(snap.get("edge_vertices") or ()),
            )
        return (
            context.scene.sketcher.use_construction,
            placement.hovered,
            placement.snapped,
            snap_target,
            placement.skip_auto_constraints,
        )

    def update_preview_point(self, context: Context) -> bool:
        """Move the current state's created point to its latest position."""
        data = self.state_data
        if data.get("is_existing_entity", False):
            # A picked element doesn't move, and the pick is part of the structure.
            return True
        cid = data.get("curve_id", "")
        props = self.get_property()
        if not cid or not props:
            return False
        ref = PointRef(self.sketch, cid)
        if not ref.valid:
            return False
        ref.co = getattr(self, props[0])
        # The hover pick clears the type each move; creating the point sets it.
        data["type"] = PointRef
        return True

    def _check_constrain(self, context: Context, curve_id: int):
        """Check if a hovered curve_id is a constrainable type (line/arc/circle)."""
        from ..model.curve_ref import ArcRef, CircleRef, LineRef

        sketch = self.sketch
        if not sketch:
            return False
        ref = curve_ref(sketch, curve_id)
        return isinstance(ref, (LineRef, ArcRef, CircleRef))

    def get_point(self, context: Context, index: int):
        states = self.get_states_definition()
        state = states[index]
        data = self._state_data[index]
        dtype = data.get("type")
        sketch = self.sketch

        if dtype == bpy.types.MeshVertex:
            sse = context.scene.sketcher.entities
            ob_name, v_index = self.get_state_pointer(index=index, implicit=True)
            ob = bpy.data.objects[ob_name]
            return sse.add_ref_vertex_2d(ob, v_index, sketch)

        # Return CurveRef using the stored type
        cid = data.get("curve_id", "")
        if cid and dtype and issubclass(dtype, CurveRef):
            return dtype(sketch, cid)
        if cid:
            return PointRef(sketch, cid)
        return getattr(self, state.pointer)

    def state_value_origin(self, context: Context):
        """The point this state is placed relative to, in sketch coordinates."""
        return self._placed_point_co(context, self.state_index - 1)

    # Which aligned distance measures a component of a placed point. A sketch's
    # third axis has no aligned distance, so a Z typed into a 3D sketch places
    # the point without being kept as a dimension.
    _COMPONENT_ALIGNMENT = ("HORIZONTAL", "VERTICAL")

    def _run_fini(self, context: Context, succeede: bool) -> None:
        super()._run_fini(context, succeede)
        if succeede:
            self._add_typed_dimensions(context)

    def _add_typed_dimensions(self, context: Context) -> None:
        """Keep every number typed into a value box as a driving dimension.

        Typing a width states what the width *is*, so it outlives the click:
        the pair of points it was typed between gets an aligned distance
        holding them that far apart, and solving the sketch keeps it. A value
        only dragged states nothing and leaves the points free.
        """
        sketch = self.sketch
        if sketch is None:
            return

        for index in range(len(self.get_states())):
            typed = self.get_state_data(index).get("numeric_input") or ()
            if not any(number is not None for number in typed):
                continue
            if self._add_typed_radius(context, index, typed):
                continue
            end = self.get_state_data(index).get("curve_id", "")
            start = self.get_state_data(index - 1).get("curve_id", "") if index else ""
            if not end or not start:
                continue
            origin = self._placed_point_co(context, index - 1)
            placed = self._placed_point_co(context, index)
            if origin is None or placed is None:
                continue

            to_world = sketch.world_matrix
            legs = [
                (to_world @ a, to_world @ b)
                for a, b in self._axis_legs(origin, placed, len(typed))
            ]
            for axis, number in enumerate(typed):
                if number is None or axis >= len(self._COMPONENT_ALIGNMENT):
                    continue
                constraint = sketch.constraints.add_distance(
                    init=True,
                    curve_id_1=start,
                    curve_id_2=end,
                    align=self._COMPONENT_ALIGNMENT[axis],
                    value=abs(placed[axis] - origin[axis]),
                )
                if axis < len(legs):
                    self._place_dimension(context, constraint, legs, axis)

    def _add_typed_radius(self, context: Context, index: int, typed) -> bool:
        """Keep a typed radius as a radius dimension on the circle or arc.

        The state holds one length rather than a point, so there is no pair of
        points to hold apart: what the number states is the size of the curve
        the tool just drew.
        """
        from ..model.curve_ref import ArcRef, CircleRef

        if self._length_prop(index) is None:
            return False
        length = next((number for number in typed if number is not None), None)
        if not length:
            return False

        target = getattr(self, "target", None)
        if not isinstance(target, (CircleRef, ArcRef)) or not target.valid:
            return False

        constraint = self.sketch.constraints.add_diameter(
            init=True,
            curve_id_1=target.curve_id,
            setting=True,
            value=abs(length),
        )
        self._place_radius(context, constraint, target)
        return True

    def _place_radius(self, context: Context, constraint, target) -> None:
        """Point a radius dimension's leader the way the preview was drawn.

        A radius is drawn from the centre out to the rim on the cursor's side,
        and the gizmo draws its own leader at ``leader_angle``, so the angle is
        kept and the label sits just past the rim along it.
        """
        from ..draw_handler import live_dimension_gap

        reach = self._length_reach(context, constraint.radius, target.ct.co.to_3d())
        if reach is None:
            return
        direction = (reach - target.ct.co.to_3d()).to_2d()
        if direction.length < 1e-9:
            return
        constraint.leader_angle = math.atan2(direction.y, direction.x)

        region, region_data = _view_region(context)
        if region is None or region_data is None:
            constraint.draw_offset = constraint.radius
            return
        to_world = self.sketch.world_matrix
        rim = to_world @ reach
        stepped = location_3d_to_region_2d(
            region, region_data, rim + (to_world.to_3x3() @ direction.to_3d())
        )
        near = location_3d_to_region_2d(region, region_data, rim)
        if stepped is None or near is None or (stepped - near).length < 1e-6:
            constraint.draw_offset = constraint.radius
            return
        gap = live_dimension_gap(context) / (stepped - near).length
        constraint.draw_offset = constraint.radius + gap

    def _place_dimension(self, context: Context, constraint, legs, axis: int) -> None:
        """Put a committed dimension where its preview sat while being drawn.

        The preview is drawn a set number of pixels off the leg it measures,
        on the side away from the rest of the geometry, while ``draw_offset``
        is a signed length in the dimension's own frame. So the same placement
        is worked out in pixels and converted back at the leg's own depth,
        rather than letting the new dimension default to the middle of it.
        """
        from ..draw_handler import live_dimension_placement, live_dimension_text_height

        region, region_data = _view_region(context)
        if region is None or region_data is None:
            return

        screen = [
            [location_3d_to_region_2d(region, region_data, point) for point in leg]
            for leg in legs
        ]
        if any(point is None for leg in screen for point in leg):
            return
        ends = [point for leg in screen for point in leg]
        middle = sum(ends, Vector((0.0, 0.0))) / len(ends)
        normal, pixels = live_dimension_placement(
            *screen[axis], middle, live_dimension_text_height(context)
        )

        # How far a step along the dimension's own offset axis reaches on
        # screen, which is what turns those pixels back into a length.
        basis = constraint.matrix_basis()
        origin = basis.translation
        offset_axis = basis.col[1].to_3d().normalized()
        # Measured at the leg, because that is where the pixels were counted.
        middle = (legs[axis][0] + legs[axis][1]) / 2
        stepped = location_3d_to_region_2d(region, region_data, middle + offset_axis)
        if stepped is None:
            return
        step = stepped - location_3d_to_region_2d(region, region_data, middle)
        if step.length < 1e-6:
            return
        side = 1.0 if step.dot(normal) >= 0 else -1.0

        # The dimension measures between two points that need not be on the leg
        # (a rectangle's width is held between opposite corners), so the offset
        # runs from its own origin out to where the preview line was.
        reach = (middle - origin).dot(offset_axis) + side * pixels / step.length

        # In a perspective view the pixels a world offset buys change along the
        # way, so the guess is measured where it lands and corrected until the
        # line is where the preview drew it, to well under a pixel.
        screen_middle = location_3d_to_region_2d(region, region_data, middle)
        for _pass in range(3):
            landed = location_3d_to_region_2d(
                region, region_data, origin + offset_axis * reach
            )
            if landed is None:
                break
            short = pixels - (landed - screen_middle).dot(normal)
            if abs(short) < 0.01:
                break
            reach += side * short / step.length

        # The dimension frame is scaled by the interface scale, which reads as
        # zero when there is no interface at all (a background run).
        ui_scale = context.preferences.system.ui_scale or 1.0
        constraint.draw_offset = reach / ui_scale

    def state_value_spans(self, context: Context, values, count: int):
        """The stretch each of this state's value boxes measures, in world space.

        One box spans what is being drawn: the segment from the last point to
        the one being placed. Several boxes are one per axis, and each spans the
        leg its component covers, so a rectangle's width is dimensioned along
        its horizontal edge and its height along the vertical one, the way a CAD
        sketcher shows them.
        """
        sketch = self.sketch
        if sketch is None or getattr(sketch, "target_object", None) is None:
            return []

        start = self._placed_point_co(context, self.state_index - 1)
        end = self._live_point_co(values)
        if end is None and start is None:
            return []

        to_world = sketch.world_matrix

        if end is None and start is not None and self._length_prop() is not None:
            length = next(
                (v for v in values or () if isinstance(v, (int, float))), None
            )
            reach = self._length_reach(context, length, start)
            if reach is not None:
                return [(to_world @ start, to_world @ reach)] * count

        if start is None or end is None:
            # A lone point, or a number with no second point to measure to:
            # there is no stretch, so every box sits on the one place there is.
            point = to_world @ (start if start is not None else end)
            return [(point, point)] * count

        if count < 2:
            return [(to_world @ start, to_world @ end)]

        return [
            (to_world @ a, to_world @ b) for a, b in self._axis_legs(start, end, count)
        ]

    def _length_prop(self, index: Optional[int] = None):
        """A state's property when it is one plain length, else ``None``.

        Defaults to the running state; ``index`` asks about another one.
        """
        props = (
            self.get_property() if index is None else self.get_property(index=index)
        ) or []
        if len(props) != 1:
            return None
        rna = getattr(self, "rna_type", None)
        prop = rna.properties.get(props[0]) if rna else None
        if prop is None or prop.unit != "LENGTH" or prop.array_length:
            return None
        return prop

    def _length_reach(self, context: Context, length: float, start):
        """Where a length measured from ``start`` reaches, in sketch coordinates.

        A radius is a length out from a point, so it is dimensioned as one: a
        line from that point to the rim, on the side the cursor is dragging,
        rather than a number floating by the centre.
        """
        if not length:
            return None

        direction = Vector((1.0, 0.0))
        # Without a view there is nothing to point at, so it reaches along the
        # sketch's own X.
        has_view = getattr(context, "region_data", None) is not None
        pos = (
            get_pos_2d(context, self._get_wp(), self._last_coords) if has_view else None
        )
        if pos is not None:
            towards = Vector(pos).to_2d() - start.to_2d()
            if towards.length > 1e-9:
                direction = towards.normalized()
        return start + direction.to_3d() * length

    @staticmethod
    def _axis_legs(start, end, count: int):
        """Walk from start to end one axis at a time, in sketch coordinates.

        Each leg is the stretch one component of the placed point measures: a
        rectangle's width along the bottom, then its height up the side.
        """
        legs = []
        corner = start.copy()
        for axis in range(min(count, len(start))):
            moved = corner.copy()
            moved[axis] = end[axis]
            legs.append((corner, moved))
            corner = moved
        return legs

    @staticmethod
    def _live_point_co(values):
        """This state's value as a sketch-local point, if it is one."""
        for value in values or ():
            if hasattr(value, "__len__") and len(value) in (2, 3):
                return Vector(value).to_3d()
        return None

    def _placed_point_co(self, context: Context, index: int):
        """An earlier state's point, sketch-local, or None when it has none."""
        if index < 0 or index not in self._state_data:
            return None
        try:
            ref = self.get_point(context, index)
        except Exception:
            # A state holds whatever its pick produced; it may be no point.
            return None
        is_point = getattr(ref, "is_point", None)
        if not callable(is_point) or not is_point():
            return None
        co = getattr(ref, "co", None)
        return Vector(co).to_3d() if co is not None and len(co) >= 2 else None


class ReplaceableOutputOp:
    """Mixin for 2D tools whose picked points can be re-picked from the redo panel.

    Re-running the operator (a redo-panel change or a re-pick) must replace what
    it created before with exactly one new copy. The operator therefore records
    its own output (curve ids and constraint uids) and removes it before
    rebuilding, and the rebuild reuses those ids so everything that refers to
    them (stored picks, the recorded output itself) stays valid.
    """

    editable = True
    # Curves ("c:<id>") and constraints ("k:<uid>") this operator created.
    output_ids: StringProperty(options={"HIDDEN"})
    # Curve ids main() created, in creation order, for main to reuse.
    main_output_ids: StringProperty(options={"HIDDEN"})

    def _run_main(self, context: Context):
        from ..utilities.curve_data import reusing_curve_ids

        used = []
        with reusing_curve_ids(
            self.sketch, getattr(self, "main_output_ids", "").split(), record=used
        ):
            result = self.main(context)
        if used:
            self._set_hidden("main_output_ids", " ".join(used))
        return result

    def _reapply(self, context: Context):
        from ..model.group_constraints import reusing_constraint_uids

        self._remove_output(context)
        # Recorded once the run finishes (after fini), see _record_committed_output.
        self._baseline_ids = self._collect_output_ids(context)
        # Handed out here and in the fini that follows (see _run_fini): a tool's
        # auto constraints are created there, and they must come back with the
        # ids this run just removed, or the next re-apply won't recognize them
        # as its own output and would leave a duplicate set behind.
        self._reuse_uids = [
            t[2:] for t in getattr(self, "output_ids", "").split() if t[:2] == "k:"
        ]
        with reusing_constraint_uids(self._reuse_uids):
            result = super()._reapply(context)
        return result

    def _ignore_own_output(self) -> None:
        """Make the curves this operator created unpickable.

        A re-pick replaces them, so picking one would leave the operator
        referencing geometry it is about to remove (a line ending on its own
        endpoint, a rectangle cornered on itself).
        """
        from ..drawing import selection

        for token in getattr(self, "output_ids", "").split():
            if token[:2] == "c:" and token[2:] not in selection.ignore_list:
                selection.ignore_list.append(token[2:])

    def _prepare_pick_ui(self, context: Context) -> None:
        super()._prepare_pick_ui(context)
        self._ignore_own_output()

    def _maintain_pick_ui(self, context: Context) -> None:
        super()._maintain_pick_ui(context)
        # The panel's implicit re-run of this operator clears the ignore list
        # (see on_before_redo_states), so put our own output back on it.
        self._ignore_own_output()

    def _finish_pick_ui(self, context: Context) -> None:
        from ..drawing import selection

        super()._finish_pick_ui(context)
        selection.ignore_list.clear()

    def _run_fini(self, context: Context, succeede: bool) -> None:
        from ..model.group_constraints import reusing_constraint_uids

        uids = getattr(self, "_reuse_uids", None)
        if uids is None:
            super()._run_fini(context, succeede)
            return
        try:
            with reusing_constraint_uids(uids):
                super()._run_fini(context, succeede)
        finally:
            self._reuse_uids = None

    def _capture_baseline(self, context: Context):
        self._baseline_ids = self._collect_output_ids(context)

    def _record_committed_output(self, context: Context):
        baseline = getattr(self, "_baseline_ids", None)
        if baseline is None:
            return
        created = self._collect_output_ids(context) - baseline
        self._set_hidden("output_ids", " ".join(sorted(created)))

    def _set_hidden(self, name: str, value: str) -> None:
        try:
            setattr(self, name, value)
        except AttributeError:
            pass  # a non-registered twin (tests) has no RNA props

    def _collect_output_ids(self, context: Context) -> set:
        """Every curve id and constraint uid currently in the active sketch."""
        from ..utilities.curve_data import read_uuid_list

        ids = set()
        sketch = self.sketch
        obj = getattr(sketch, "target_object", None) if sketch else None
        if obj is None or obj.data is None:
            return ids
        ids.update("c:" + cid for cid in read_uuid_list(obj.data, "curve_id") if cid)
        for constraint in sketch.constraints.all:
            uid = getattr(constraint, "constraint_uid", "")
            if uid:
                ids.add("k:" + uid)
        return ids

    def _remove_output(self, context: Context) -> None:
        """Remove the curves and constraints recorded in ``output_ids``."""
        from ..utilities.curve_data import remove_native_curve_by_id

        sketch = self.sketch
        if sketch is None:
            return
        for token in getattr(self, "output_ids", "").split():
            kind, _, ident = token.partition(":")
            if kind == "k":
                constraint = sketch.constraints.get_by_uid(ident)
                if constraint is not None:
                    sketch.constraints.remove(constraint)
            elif kind == "c":
                remove_native_curve_by_id(sketch, ident)
