import math
from typing import Any, List

import bpy
from bpy.types import Context, Event
from mathutils import Vector

from ..model.types import SlvsPoint2D
from ..model.types import SlvsLine2D, SlvsCircle, SlvsArc
from ..model.utilities import slvs_entity_pointer
from .base_stateful import GenericEntityOp
from .utilities import ignore_hover
from ..utilities.view import get_pos_2d


class Operator2d(GenericEntityOp):
    @classmethod
    def poll(cls, context: Context):
        return context.scene.sketcher.active_sketch_i != -1

    def init(self, context: Context, event: Event):
        self.sketch = context.scene.sketcher.active_sketch

    def state_func(self, context: Context, coords):
        state = self.state
        wp = self.sketch.wp
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
            # Take the delta between the state start position and current position in 2d space
            # Define the sign by the screen space x axis

            type_cast = float if prop.type == "FLOAT" else int
            old_pos = get_pos_2d(context, wp, self.state_init_coords)
            dist = type_cast(Vector(pos - old_pos).length)
            return math.copysign(dist, coords.x - self.state_init_coords.x)

        return super().state_func(context, coords)

    # create element depending on mode
    def create_element(self, context: Context, values: List[Any], state, state_data):
        sse = context.scene.sketcher.entities
        sketch = self.sketch
        loc = values[0]
        point = sse.add_point_2d(loc, sketch)
        self.add_coincident(context, point, state, state_data)

        ignore_hover(point)
        state_data["type"] = type(point)
        return point.slvs_index

    def _check_constrain(self, context: Context, index: int):
        type = context.scene.sketcher.entities.type_from_index(index)
        return type in (
            SlvsLine2D,
            SlvsCircle,
            SlvsArc,
        )

    def get_point(self, context: Context, index: int):
        states = self.get_states_definition()
        state = states[index]
        data = self._state_data[index]
        type = data["type"]
        sse = context.scene.sketcher.entities
        sketch = self.sketch

        if type == bpy.types.MeshVertex:
            ob_name, v_index = self.get_state_pointer(index=index, implicit=True)
            ob = bpy.data.objects[ob_name]
            return sse.add_ref_vertex_2d(ob, v_index, sketch)
        return getattr(self, state.pointer)


slvs_entity_pointer(Operator2d, "sketch")
