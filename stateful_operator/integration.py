"""
Add integration with native blender types, following are supported:

- bpy.types.Object
- bpy.types.MeshVertex
- bpy.types.MeshEdge
- bpy.types.MeshPolygon
"""


from .logic import StatefulOperatorLogic
from .constants import mesh_element_types
from .utilities.generic import get_pointer_get_set, to_list
from .utilities.geometry import (
    get_evaluated_obj,
    get_mesh_element,
    get_placement_pos,
    get_scale_from_pos,
)

import bpy
from bpy.types import Context

from typing import Optional


class StatefulOperator(StatefulOperatorLogic):
    """Extends logic class with native blender integration"""

    @classmethod
    def _has_global_object(cls):
        states = cls.get_states_definition()
        return any([s.pointer == "object" for s in states])

    def _get_global_object_index(cls):
        states = cls.get_states_definition()
        object_in_list = [s.pointer == "object" for s in states]
        if not any(object_in_list):
            return None
        return object_in_list.index(True)

    @classmethod
    def register_properties(cls):
        states = cls.get_states_definition()
        annotations = cls.__annotations__.copy()

        # Have some specific logic: pointer name "object" is used as global object
        # otherwise define ob_name for each element
        # has_global_object = cls._has_global_object()

        for i, s in enumerate(states):
            pointer_name = s.pointer
            types = s.types

            if not pointer_name:
                continue

            if pointer_name in annotations.keys():
                # Skip pointers that have a property defined
                # Note: pointer might not need implicit props, thus no need for getter/setter
                return

            if hasattr(cls, pointer_name):
                # This can happen when the addon is re-enabled in the same session
                continue

            get, set = get_pointer_get_set(i)
            setattr(cls, pointer_name, get)
            # Note: keep state pointers read-only, only set with set_state_pointer()

        for a in annotations.keys():
            if hasattr(cls, a):
                raise NameError(
                    "Cannot register implicit pointer properties, class {} already has attribute of name {}".format(
                        cls, a
                    )
                )

    def state_property(self, state_index):
        return None

    def get_state_pointer(
        self, index: Optional[int] = None, implicit: Optional[bool] = False
    ):
        # Creates pointer value from its implicitly stored props
        if index is None:
            index = self.state_index

        state = self.get_states_definition()[index]
        pointer_name = state.pointer
        data = self._state_data.get(index, {})
        if "type" not in data.keys():
            return None

        pointer_type = data["type"]
        if not pointer_type:
            return None

        if pointer_type in (bpy.types.Object, *mesh_element_types):
            if self._has_global_object():
                global_ob_index = self._get_global_object_index()
                obj_name = self._state_data[global_ob_index]["object_name"]
            else:
                obj_name = data["object_name"]
            obj = get_evaluated_obj(bpy.context, bpy.data.objects[obj_name])

        if pointer_type in mesh_element_types:
            index = data["mesh_index"]

        if pointer_type == bpy.types.Object:
            if implicit:
                return obj_name
            return obj

        elif pointer_type == bpy.types.MeshVertex:
            if implicit:
                return obj_name, index
            return obj.data.vertices[index]

        elif pointer_type == bpy.types.MeshEdge:
            if implicit:
                return obj_name, index
            return obj.data.edges[index]

        elif pointer_type == bpy.types.MeshPolygon:
            if implicit:
                return obj_name, index
            return obj.data.polygons[index]

    def set_state_pointer(self, values, index=None, implicit=False):
        # handles type specific setters
        if index is None:
            index = self.state_index

        state = self.get_states_definition()[index]
        pointer_name = state.pointer
        data = self._state_data.get(index, {})

        pointer_type = data["type"]

        def get_value(index):
            if values is None:
                return None
            return values[index]

        if pointer_type == bpy.types.Object:
            if implicit:
                val = get_value(0)
            else:
                val = get_value(0).name
            data["object_name"] = val
            return True

        elif pointer_type in mesh_element_types:
            obj_name = get_value(0) if implicit else get_value(0).name
            if self._has_global_object():
                self._state_data[self._get_global_object_index()][
                    "object_name"
                ] = obj_name
            else:
                data["object_name"] = obj_name

            data["mesh_index"] = get_value(1) if implicit else get_value(1).index
            return True

    def state_func(self, context: Context, coords):
        pos = get_placement_pos(context, coords)

        prop_name = self.state.property
        prop = self.rna_type.properties.get(prop_name)
        if not prop:
            return super().state_func(context, coords)

        if prop.array_length > 1:
            return pos

        if prop.type in ("FLOAT", "INT"):
            # Take the delta between the state start position and current position in screenspace X-Axis
            # and scale the value by the zoom level at the state start position

            type_cast = float if prop.type == "FLOAT" else int
            old_pos = get_placement_pos(context, self.state_init_coords)
            scale = get_scale_from_pos(old_pos, context.region_data) / 500

            # NOTE: self.state_init_coords is not set for non-interactive states
            print((coords.x - self.state_init_coords.x) * scale)
            return type_cast((coords.x - self.state_init_coords.x) * scale)

        return super().state_func(context, coords)

    def pick_element(self, context: Context, coords):
        # return a list of implicit prop values if pointer need implicit props
        state = self.state
        data = self.state_data

        types = {
            "vertex": (bpy.types.MeshVertex in state.types),
            "edge": (bpy.types.MeshEdge in state.types),
            "face": (bpy.types.MeshPolygon in state.types),
        }

        do_object = bpy.types.Object in state.types
        do_mesh_elem = any(types.values())

        if not do_object and not do_mesh_elem:
            return

        global_ob = None
        if self._has_global_object():
            global_ob_name = self._state_data[self._get_global_object_index()].get(
                "object_name"
            )
            if global_ob_name:
                global_ob = bpy.data.objects[global_ob_name]

        ob, type, index = get_mesh_element(context, coords, **types, object=global_ob)

        if not ob:
            return None

        if bpy.types.Object in state.types:
            data["type"] = bpy.types.Object
            return ob.name

        # maybe have type as return value
        data["type"] = {
            "VERTEX": bpy.types.MeshVertex,
            "EDGE": bpy.types.MeshEdge,
            "FACE": bpy.types.MeshPolygon,
        }[type]

        return ob.name, index

    def gather_selection(self, context: Context):
        # Return list filled with all selected verts/edges/faces/objects
        selected = []
        states = self.get_states()
        types = []
        [types.extend(s.types) for s in states]

        # Note: Where to take mesh elements from? Editmode data is only written
        # when left probably making it impossible to use selected elements in realtime.
        if any([t == bpy.types.Object for t in types]):
            selected.extend(context.selected_objects)

        return selected

    # Gets called for every state
    def parse_selection(self, context, selected, index=None):
        # Look for a valid element in selection
        # should go through objects, vertices, entities depending on state.types

        result = None
        if not index:
            index = self.state_index
        state = self.get_states_definition()[index]
        data = self.get_state_data(index)

        if state.pointer:
            # TODO: Discard if too many entities are selected?
            types = state.types
            for i, e in enumerate(selected):
                if type(e) in types:
                    result = selected.pop(i)
                    break

        if result:
            data["type"] = type(result)
            self.set_state_pointer(to_list(result), index=index)
            self.state_data["is_existing_entity"] = True
            return True

    def draw(self, context):
        layout = self.layout

        for i, state in enumerate(self.get_states()):
            if i != 0:
                layout.separator()

            layout.label(text=state.name)

            state_data = self._state_data.get(i, {})
            is_existing = state_data.get("is_existing_entity", False)
            props = self.get_property(index=i)

            if state.pointer and is_existing:
                layout.label(text=str(getattr(self, state.pointer)))
            elif props:
                for p in props:
                    layout.prop(self, p, text="")

        if hasattr(self, "draw_settings"):
            self.draw_settings(context)
