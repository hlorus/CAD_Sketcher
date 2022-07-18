import bpy
from bpy.types import Context, Event
from mathutils import Vector
from mathutils.geometry import intersect_line_plane

from .. import functions, class_defines
from .base_stateful import GenericEntityOp
from .utilities import ignore_hover


class Operator2d(GenericEntityOp):
    @classmethod
    def poll(cls, context: Context):
        return context.scene.sketcher.active_sketch_i != -1

    def init(self, context: Context, event: Event):
        self.sketch = context.scene.sketcher.active_sketch

    def state_func(self, context: Context, coords):
        wp = self.sketch.wp
        origin, end_point = functions.get_picking_origin_end(context, coords)
        pos = intersect_line_plane(origin, end_point, wp.p1.location, wp.normal)
        if pos is None:
            return None

        pos = wp.matrix_basis.inverted() @ pos
        return Vector(pos[:-1])

    # create element depending on mode
    def create_element(self, context, values, state, state_data):
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
            class_defines.SlvsLine2D,
            class_defines.SlvsCircle,
            class_defines.SlvsArc,
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


class_defines.slvs_entity_pointer(Operator2d, "sketch")
