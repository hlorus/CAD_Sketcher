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


