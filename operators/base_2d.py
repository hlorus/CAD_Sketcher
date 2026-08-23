from typing import Any, List

import bpy
from bpy.types import Context, Event

from ..model.curve_ref import CurveRef, PointRef, curve_ref
from ..model.types import SlvsPoint2D
from ..utilities.view import get_blender_snap_info, get_pos_2d, get_scale_from_pos
from .base_stateful import GenericEntityOp
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
            snap["curve_data"] = self._snapshot_curve_data(obj.data)
            snap["constraints"] = self._snapshot_constraints(obj.data)
        return snap

    def restore_snapshot(self, context: Context, snapshot):
        if not snapshot:
            return
        from ..utilities.curve_data import invalidate_curve_id_cache

        scene = context.scene
        invalidate_curve_id_cache()

        name = snapshot.get("active_name")
        obj = bpy.data.objects.get(name) if name else None
        if obj and obj.data and "curve_data" in snapshot:
            self._restore_curve_data(obj.data, snapshot["curve_data"])
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
        self._snap_handle = bpy.types.SpaceView3D.draw_handler_add(
            draw_snap_marker, (self, context), "WINDOW", "POST_PIXEL"
        )
        return super().invoke(context, event)

    def _end(self, context: Context, succeede, *args, **kwargs):
        handle = getattr(self, "_snap_handle", None)
        if handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(handle, "WINDOW")
            self._snap_handle = None
        return super()._end(context, succeede, *args, **kwargs)

    def init(self, context: Context, event: Event):
        from ..model.sketch_ref import get_active_sketch

        self._active_sketch = get_active_sketch(context)
        return True

    @property
    def sketch(self):
        if not self._active_sketch:
            import bpy

            from ..model.sketch_ref import get_active_sketch

            self._active_sketch = get_active_sketch(bpy.context)
        return self._active_sketch

    def _get_wp(self):
        """Get the workplane (empty object or entity) for this sketch."""
        if self.sketch.workplane_object:
            return self.sketch.workplane_object
        # Fallback: curve object's parent is the workplane empty
        if self.sketch.target_object and self.sketch.target_object.parent:
            return self.sketch.target_object.parent
        return None

    def state_func(self, context: Context, coords):
        state = self.state
        wp = self._get_wp()
        self._snap = get_blender_snap_info(context, coords)
        pos = get_pos_2d(context, wp, coords, respect_snapping=True)

        # Remember whether this point landed on an external-geometry snap, so its
        # deferred creation can anchor it (fixed) — otherwise an inferred
        # constraint would drag the snapped point off target (see create_element).
        self.state_data["snapped"] = self._snap is not None
        # Stash the snap target so create_element can live-project it (the marker
        # reflects the current position; at click this is the committed one).
        self.state_data["snap"] = self._snap

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

    def _maybe_link_projected_snap(self, context: Context, state_data):
        """Live-project a snapped mesh feature and register it for constraining.

        When a point is snapped onto external mesh geometry, create (or reuse) a
        live projected reference and set it as the constraint target, so the placed
        point tracks the source instead of being a dead static point:

        - vertex: project the vertex as a point; coincide the placed point on it.
        - along an edge: project the edge as a line; coincide the point on the line
          (point-on-line) so it slides along the edge.
        - edge midpoint: project the edge as a line; add a midpoint constraint so
          the point stays centered as the edge's endpoints track the source.

        Other snap types, and cases where the snapped feature can't be traced to an
        original one, fall back to the static point.
        """
        if not context.scene.sketcher.use_snap_project:
            state_data["snap_anchored"] = False
            state_data["snap_link_kind"] = "COINCIDENT"
            return
        if not self.use_auto_constraints(context, state_data):
            state_data["snap_anchored"] = False
            state_data["snap_link_kind"] = "COINCIDENT"
            return
        hovered = state_data.get("hovered")
        if hovered:
            # Coincident with something already. If it still resolves to a LIVE
            # curve (a genuine pick, or this state's projection), leave it be. But
            # a non-current state's projection gets wiped by the preview restore
            # each frame while its stale hovered id lingers here -- honoring it
            # would coincide the endpoint to a deleted curve (a dead static point,
            # the "snaps but no live link" bug). Detect that and fall through to
            # re-project so the reference is recreated.
            from ..model.curve_ref import curve_ref

            existing = curve_ref(self.sketch, hovered)
            if existing is not None and existing.valid:
                return
            state_data["hovered"] = ""

        # Fresh (re)evaluation of this state: default to not-anchored and a plain
        # coincidence, so stale flags from a previous frame (e.g. the cursor moved
        # off a vertex/midpoint) are cleared. They are set again below only when the
        # current snap warrants it.
        state_data["snap_anchored"] = False
        state_data["snap_link_kind"] = "COINCIDENT"

        snap = state_data.get("snap")
        if not snap:
            return
        snap_type = snap.get("type")
        if snap_type not in ("VERTEX", "EDGE_MIDPOINT", "EDGE"):
            return
        source = bpy.data.objects.get(snap.get("object") or "")
        if source is None or source.type != "MESH":
            return

        # Snapping reads the evaluated mesh; resolve the evaluated vertices back to
        # the original ones to bind (by persistent id when tagged, else an
        # order-preserving index). Skip when the correspondence isn't trustworthy.
        from ..stateful_operator.utilities.geometry import get_evaluated_obj
        from ..utilities.projection_anchor import (
            project_mesh_edge,
            project_mesh_vertex,
            resolve_source_vertex_index,
        )

        eval_source = get_evaluated_obj(context, source)
        world_point = snap.get("world_point")

        # Place the point where the user snapped (the evaluated hit), so a
        # vertex-moving modifier doesn't leave it a frame behind the source.
        if snap_type == "VERTEX":
            v_index = snap.get("vertex_index")
            if v_index is None:
                return
            orig = resolve_source_vertex_index(source, eval_source, v_index)
            if orig is None:
                return
            projected = project_mesh_vertex(
                self.sketch, source, orig, construction=True, world_co=world_point
            )
        else:  # EDGE_MIDPOINT or EDGE: project the edge as a live line
            edge = snap.get("edge_vertices")
            if not edge:
                return
            orig_a = resolve_source_vertex_index(source, eval_source, edge[0])
            orig_b = resolve_source_vertex_index(source, eval_source, edge[1])
            if orig_a is None or orig_b is None:
                return
            projected = project_mesh_edge(
                self.sketch, source, orig_a, orig_b, construction=True
            )

        if projected is not None and projected.valid:
            state_data["hovered"] = projected.curve_id
            if snap_type == "EDGE_MIDPOINT":
                # Constrain the point to the edge's midpoint (POINT, LINE). The
                # projected line's endpoints track the source, and the midpoint
                # constraint keeps the point centered as they move. It fully pins
                # the point, so treat it as anchored for the alignment guard.
                state_data["snap_link_kind"] = "MIDPOINT"
                state_data["snap_anchored"] = True
            elif snap_type == "VERTEX":
                # Coincident to a FIXED point: an auto axis-alignment would fight
                # the fixed position, so flag it anchored (the line tool skips
                # alignment, as it does for two statically-fixed endpoints).
                state_data["snap_anchored"] = True
            # EDGE: point-on-line coincidence (default kind); the point can still
            # slide along the line, so it is not flagged anchored.

    def point_is_anchored(self, index: int) -> bool:
        """Whether the point placed for state ``index`` is pinned in place.

        True when the endpoint is a live-projected vertex/midpoint (coincident to a
        FIXED projected point) -- an auto axis-alignment on it would fight the fixed
        position. Used by tools that add alignment constraints to skip it.
        """
        return bool(self._state_data.get(index, {}).get("snap_anchored", False))

    # create element depending on mode
    def create_element(self, context: Context, values: List[Any], state, state_data):
        sketch = self.sketch
        loc = values[0]

        # Snapped onto external mesh geometry: live-project it and coincide, so
        # the point tracks the source. Registers the projected point as the
        # coincidence target below (behaves like snapping onto a sketch entity).
        self._maybe_link_projected_snap(context, state_data)

        # A point snapped to external geometry is a deliberate placement: fix it
        # so the solver keeps it there. Points snapped onto a sketch entity (or a
        # live-projected reference above) are pinned by the coincident constraint
        # below instead, so skip those.
        fixed = state_data.get("snapped", False) and not state_data.get("hovered")

        ref = PointRef.create(sketch, loc, fixed=fixed)
        cid = ref.curve_id

        self.add_coincident(context, ref, state, state_data)

        ignore_hover(cid)
        state_data["type"] = PointRef
        state_data["curve_id"] = cid
        return cid

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
