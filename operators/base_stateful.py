from typing import Union

import bpy
from bpy.types import Context
from bpy.props import FloatVectorProperty

from .. import global_data
from ..stateful_operator.integration import StatefulOperator
from ..model.types import SlvsGenericEntity, SlvsPoint3D, SlvsPoint2D, SlvsNormal3D
from .utilities import get_hovered


class GenericEntityOp(StatefulOperator):
    """Extend StatefulOperator with extension specific types"""

    def check_event(self, event):
        return super().check_event(event)

    def pick_element(self, context, coords):
        retval = super().pick_element(context, coords)
        if retval is not None:
            return retval

        state = self.state
        data = self.state_data

        hovered = get_hovered(context, *state.types)
        if hovered and self.is_in_previous_states(hovered):
            hovered = None

        # Set the hovered entity for constraining if not directly used
        hovered_index = -1
        if not hovered and hasattr(self, "_check_constrain"):
            hover = global_data.hover
            if hover and self._check_constrain(context, hover):
                hovered_index = hover

        data["hovered"] = hovered_index
        data["type"] = type(hovered) if hovered else None
        return hovered.slvs_index if hovered else None

    def add_coincident(self, context: Context, point, state, state_data):
        index = state_data.get("hovered", -1)
        if index != -1:
            hovered = context.scene.sketcher.entities.get(index)
            constraints = context.scene.sketcher.constraints

            sketch = None
            if hasattr(self, "sketch"):
                sketch = self.sketch
            state_data["coincident"] = constraints.add_coincident(
                point, hovered, sketch=sketch
            )

    def has_coincident(self):
        for state_index, data in self._state_data.items():
            if data.get("coincident", None):
                return True
        return False

    @classmethod
    def register_properties(cls):
        super().register_properties()

        states = cls.get_states_definition()

        for s in states:
            if not s.pointer:
                continue

            name = s.pointer
            types = s.types

            annotations = {}
            if hasattr(cls, "__annotations__"):
                annotations = cls.__annotations__.copy()

            # handle SlvsPoint3D fallback props
            if any([t == SlvsPoint3D for t in types]):
                kwargs = {"size": 3, "subtype": "XYZ", "unit": "LENGTH"}
                annotations[name + "_fallback"] = FloatVectorProperty(
                    name=name, **kwargs
                )

            # handle SlvsPoint2D fallback props
            if any([t == SlvsPoint2D for t in types]):
                kwargs = {"size": 2, "subtype": "XYZ", "unit": "LENGTH"}
                annotations[name + "_fallback"] = FloatVectorProperty(
                    name=name, **kwargs
                )

            if any([t == SlvsNormal3D for t in types]):
                kwargs = {"size": 3, "subtype": "EULER", "unit": "ROTATION"}
                annotations[name + "_fallback"] = FloatVectorProperty(
                    name=name, **kwargs
                )

            for a in annotations.keys():
                if hasattr(cls, a):
                    raise NameError(
                        (
                            f"Class {cls} already has attribute of name {a},"
                            f"cannot register implicit pointer properties"
                        )
                    )
            setattr(cls, "__annotations__", annotations)

    def state_property(self, state_index):
        # Return state_prop / properties. Handle multiple types
        props = super().state_property(state_index)
        if props:
            return props

        state = self.get_states_definition()[state_index]

        pointer_name = state.pointer
        if not pointer_name:
            return ""

        if any([issubclass(t, SlvsGenericEntity) for t in state.types]):
            return pointer_name + "_fallback"
        return ""

    def get_state_pointer(self, index=Union[None, int], implicit=False):
        retval = super().get_state_pointer(index=index, implicit=implicit)
        if retval:
            return retval

        # Creates pointer from its implicitly stored props
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

        if issubclass(pointer_type, SlvsGenericEntity):
            i = data["entity_index"]
            if implicit:
                return i

            if i == -1:
                return None
            return bpy.context.scene.sketcher.entities.get(i)

    def set_state_pointer(self, values, index=None, implicit=False):
        retval = super().set_state_pointer(values, index=index, implicit=implicit)
        if retval:
            return retval

        # handles type specific setters
        if index is None:
            index = self.state_index

        state = self.get_states_definition()[index]
        pointer_name = state.pointer
        data = self._state_data.get(index, {})
        pointer_type = data["type"]

        if issubclass(pointer_type, SlvsGenericEntity):
            value = values[0] if values is not None else None

            if value is None:
                i = -1
            elif implicit:
                i = value
            else:
                i = value.slvs_index
            data["entity_index"] = i
            return True

    def gather_selection(self, context: Context):
        # Return list filled with all selected verts/edges/faces/objects
        selected = super().gather_selection(context)
        states = self.get_states()
        types = [s.types for s in states]

        selected.extend(list(context.scene.sketcher.entities.selected))
        return selected
