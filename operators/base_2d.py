import math
from typing import Any, List

import bpy
from bpy.types import Context, Event
from mathutils import Vector

from ..model.types import SlvsPoint2D
from ..model.types import SlvsLine2D, SlvsCircle, SlvsArc
from ..model.curve_ref import CurveRef, PointRef, curve_ref
from .base_stateful import GenericEntityOp
from .utilities import ignore_hover
from ..utilities.view import get_pos_2d, get_scale_from_pos


class Operator2d(GenericEntityOp):
    @classmethod
    def poll(cls, context: Context):
        return context.scene.sketcher.active_sketch_object is not None

    def init(self, context: Context, event: Event):
        from ..model.sketch_ref import get_active_sketch
        self._active_sketch = get_active_sketch(context)
        return True

    @property
    def sketch(self):
        if not self._active_sketch:
            from ..model.sketch_ref import get_active_sketch
            import bpy
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
        pos = get_pos_2d(context, wp, coords)

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

        ref = PointRef.create(sketch, loc)
        cid = ref.curve_id

        self.add_coincident(context, ref, state, state_data)

        ignore_hover(cid)
        state_data["type"] = PointRef
        state_data["curve_id"] = cid
        return cid

    def _check_constrain(self, context: Context, curve_id: int):
        """Check if a hovered curve_id is a constrainable type (line/arc/circle)."""
        from ..model.curve_ref import LineRef, ArcRef, CircleRef
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


