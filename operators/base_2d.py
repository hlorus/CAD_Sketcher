from typing import Any, List

import bpy
from bpy.props import StringProperty
from bpy.types import Context, Event

from ..model.curve_ref import CurveRef, PointRef, curve_ref
from ..model.types import SlvsPoint2D
from ..utilities.view import get_blender_snap_info, get_pos_2d, get_scale_from_pos
from .base_stateful import GenericEntityOp
from .placement import MIDPOINT, PointPlacement, ProjectionRequest, placement_of
from .utilities import ignore_hover


class Operator2d(GenericEntityOp):
    # Current geometry snap target (dict from get_blender_snap_info) or None,
    # updated as the cursor moves and drawn by the snap-marker handler.
    _snap = None
    _snap_handle = None

    @classmethod
    def poll(cls, context: Context):
        return context.scene.sketcher.active_sketch_object is not None

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
        if obj and obj.data:
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
        if obj and obj.data and "curve_data" in snapshot:
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
