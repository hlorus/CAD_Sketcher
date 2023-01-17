import logging
from bpy.types import Context
from bpy.props import BoolProperty

from ..model.types import SlvsConstraints
from ..solver import solve_system
from ..stateful_operator.state import state_from_args
from .base_stateful import GenericEntityOp
from ..utilities.select import deselect_all
from ..utilities.view import refresh

logger = logging.getLogger(__name__)

state_docstr = "Pick entity to constrain."


class GenericConstraintOp(GenericEntityOp):
    initialized: BoolProperty(options={"SKIP_SAVE", "HIDDEN"})
    _entity_prop_names = ("entity1", "entity2", "entity3", "entity4")

    def _available_entities(self):
        # Gets entities that are already set
        cls = SlvsConstraints.cls_from_type(self.type)
        entities = [None] * len(cls.signature)
        for i, name in enumerate(self._entity_prop_names):
            if hasattr(self, name):
                e = getattr(self, name)
                if not e:
                    continue
                entities[i] = e
        return entities

    @classmethod
    def states(cls, operator=None):
        states = []

        cls_constraint = SlvsConstraints.cls_from_type(cls.type)

        for i, _ in enumerate(cls_constraint.signature):
            name_index = i + 1
            if hasattr(cls_constraint, "get_types") and operator:
                types = cls_constraint.get_types(i, operator._available_entities())
            else:
                types = cls_constraint.signature[i]

            if not types:
                break

            states.append(
                state_from_args(
                    "Entity " + str(name_index),
                    description=state_docstr,
                    pointer="entity" + str(name_index),
                    property=None,
                    types=types,
                )
            )
        return states

    def initialize_constraint(self):
        c = self.target
        if not self.initialized and hasattr(c, "init_props"):
            kwargs = {}
            if hasattr(self, "value") and self.properties.is_property_set("value"):
                kwargs["value"] = self.value
            if hasattr(self, "setting") and self.properties.is_property_set("setting"):
                kwargs["setting"] = self.setting

            value, setting = c.init_props(**kwargs)
            if value is not None:
                self.value = value
            if setting is not None:
                self.setting = setting
        self.initialized = True

    def fill_entities(self):
        c = self.target
        args = []
        # fill in entities!
        for prop in self._entity_prop_names:
            if hasattr(c, prop):
                value = getattr(self, prop)
                setattr(c, prop, value)
                args.append(value)
        return args

    def main(self, context: Context):
        c = self.target = context.scene.sketcher.constraints.new_from_type(self.type)
        self.sketch = context.scene.sketcher.active_sketch
        entities = self.fill_entities()
        c.sketch = self.sketch

        self.initialize_constraint()

        if hasattr(c, "value"):
            c["value"] = self.value
        if hasattr(c, "setting"):
            c["setting"] = self.setting

        deselect_all(context)
        solve_system(context, sketch=self.sketch)
        refresh(context)
        return True

    def fini(self, context: Context, succeede: bool):
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))

    def draw(self, context: Context):
        layout = self.layout

        c = self.target
        if not c:
            return

        if hasattr(c, "value"):
            layout.prop(self, "value")
        if hasattr(c, "setting"):
            layout.prop(self, "setting")

        if hasattr(self, "draw_settings"):
            self.draw_settings(context)
