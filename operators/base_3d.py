import bpy
from bpy.types import Context, Event

from ..model.types import SlvsLine3D, SlvsWorkplane
from .base_stateful import GenericEntityOp
from .utilities import ignore_hover
from ..utilities.view import get_placement_pos


class Operator3d(GenericEntityOp):
    @classmethod
    def poll(cls, context: Context):
        return context.scene.sketcher.active_sketch_i == -1

    def init(self, context: Context, event: Event):
        pass

    def state_func(self, context, coords):
        return get_placement_pos(context, coords)

    def create_element(self, context, values, state, state_data):
        sse = context.scene.sketcher.entities
        loc = values[0]
        point = sse.add_point_3d(loc)
        self.add_coincident(context, point, state, state_data)

        ignore_hover(point)
        state_data["type"] = type(point)
        return point.slvs_index

    # Check if hovered entity should be constrained
    def _check_constrain(self, context, index):
        type = context.scene.sketcher.entities.type_from_index(index)
        return type in (SlvsLine3D, SlvsWorkplane)

    def get_point(self, context, index):
        states = self.get_states_definition()
        state = states[index]
        data = self._state_data[index]
        type = data["type"]
        sse = context.scene.sketcher.entities

        if type == bpy.types.MeshVertex:
            ob_name, v_index = self.get_state_pointer(index=index, implicit=True)
            ob = bpy.data.objects[ob_name]
            return sse.add_ref_vertex_3d(ob, v_index)
        return getattr(self, state.pointer)
