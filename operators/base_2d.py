from typing import Any, List

import bpy
from bpy.types import Context, Event

from ..drawing import selection
from ..model.curve_ref import CurveRef, PointRef, curve_ref
from ..model.types import SlvsLine3D, SlvsPoint2D, SlvsPoint3D, SlvsWorkplane
from ..stateful_operator.integration import StatefulOperator
from ..utilities.view import (
    get_blender_snap_info,
    get_placement_pos,
    get_pos_2d,
    get_scale_from_pos,
)
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

    def _is_sketch_mode(self):
        return bool(self.sketch)

    # A 2D draw operator only ever modifies the active sketch's curve data and
    # constraints -- not the entity system (structural workplane/normal/origin
    # entities). Outside sketch mode, constraint operators still use the scene
    # entity system, so fall back to the complete GenericEntityOp snapshot.
    def create_snapshot(self, context: Context):
        from ..model.sketch_ref import get_active_sketch

        sketch = get_active_sketch(context)
        if not sketch:
            return super().create_snapshot(context)

        scene = context.scene
        obj = sketch.target_object
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
        # GenericEntityOp snapshots contain the serialized scene. Operator2d's
        # optimized sketch snapshot intentionally does not.
        if "scene" in snapshot:
            return super().restore_snapshot(context, snapshot)

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
        from ..model.sketch_ref import get_active_sketch

        if not get_active_sketch(context):
            self._snap = None
            self._snap_handle = None
            return super().invoke(context, event)

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
        if not hasattr(self, "_active_sketch"):
            self._active_sketch = None
        if not self._active_sketch:
            import bpy

            from ..model.sketch_ref import get_active_sketch
            self._active_sketch = get_active_sketch(bpy.context)
        return self._active_sketch

    def _get_wp(self):
        """Get the workplane (empty object or entity) for this sketch."""
        if not self.sketch:
            return None
        if self.sketch.workplane_object:
            return self.sketch.workplane_object
        # Fallback: curve object's parent is the workplane empty
        if self.sketch.target_object and self.sketch.target_object.parent:
            return self.sketch.target_object.parent
        return None

    def pick_element(self, context, coords):
        if self.sketch:
            return super().pick_element(context, coords)

        # StatefulOperator handles Blender mesh selections first. Legacy CAD
        # entities are addressed by their slvs_index in selection.hover.
        retval = StatefulOperator.pick_element(self, context, coords)
        if retval is not None:
            return retval

        state = self.state
        data = self.state_data
        hover_id = selection.hover
        hovered = None
        if isinstance(hover_id, int):
            hovered = context.scene.sketcher.entities.get(hover_id)
        if hovered and not isinstance(hovered, state.types):
            hovered = None
        if hovered and self.is_in_previous_states(hovered):
            hovered = None

        data["hovered"] = hovered.slvs_index if hovered else -1
        data["type"] = type(hovered) if hovered else None
        return hovered.slvs_index if hovered else None

    def state_func(self, context: Context, coords):
        state = self.state
        if not self.sketch:
            pos = get_placement_pos(context, coords)
            if SlvsPoint3D in state.types:
                return pos
            return super().state_func(context, coords)

        wp = self._get_wp()
        self._snap = get_blender_snap_info(context, coords)
        pos = get_pos_2d(context, wp, coords, respect_snapping=True)

        # Remember whether this point landed on an external-geometry snap, so its
        # deferred creation can anchor it (fixed) — otherwise an inferred
        # constraint would drag the snapped point off target (see create_element).
        self.state_data["snapped"] = self._snap is not None

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

    # create element depending on mode
    def create_element(self, context: Context, values: List[Any], state, state_data):
        if not self.sketch:
            loc = values[0]
            point = context.scene.sketcher.entities.add_point_3d(loc)
            ignore_hover(point)
            state_data["type"] = type(point)
            return point.slvs_index

        sketch = self.sketch
        loc = values[0]

        # A point snapped to external geometry is a deliberate placement: fix it
        # so the solver keeps it there. Points snapped onto a sketch entity are
        # pinned by the coincident constraint below instead, so skip those.
        fixed = state_data.get("snapped", False) and not state_data.get("hovered")

        ref = PointRef.create(sketch, loc, fixed=fixed)
        cid = ref.curve_id

        self.add_coincident(context, ref, state, state_data)

        ignore_hover(cid)
        state_data["type"] = PointRef
        state_data["curve_id"] = cid
        return cid

    def _check_constrain(self, context: Context, curve_id: int):
        """Check if a hovered entity should be constrained."""
        if not self.sketch:
            entity_type = context.scene.sketcher.entities.type_from_index(curve_id)
            return entity_type in (SlvsLine3D, SlvsWorkplane)

        from ..model.curve_ref import ArcRef, CircleRef, LineRef

        ref = curve_ref(self.sketch, curve_id)
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
            if not sketch:
                return sse.add_ref_vertex_3d(ob, v_index)
            return sse.add_ref_vertex_2d(ob, v_index, sketch)

        if not sketch:
            return getattr(self, state.pointer)

        # Return CurveRef using the stored type
        cid = data.get("curve_id", "")
        if cid and dtype and issubclass(dtype, CurveRef):
            return dtype(sketch, cid)
        if cid:
            return PointRef(sketch, cid)
        return getattr(self, state.pointer)
