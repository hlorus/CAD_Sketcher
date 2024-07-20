import logging
from typing import List
from bpy.types import Context
from bpy.props import BoolProperty

from ..utilities.bpy import setprop
from ..model.types import SlvsConstraints
from ..solver import solve_system
from ..stateful_operator.state import state_from_args
from ..utilities.select import deselect_all
from ..utilities.view import refresh
from .base_2d import Operator2d


logger = logging.getLogger(__name__)

state_docstr = "Pick entity to constrain."


class GenericConstraintOp(Operator2d):
    initialized: BoolProperty(default=False, options={"SKIP_SAVE", "HIDDEN"})
    _entity_prop_names = ("entity1", "entity2", "entity3", "entity4")
    property_keys = ()

    @classmethod
    def poll(cls, context):
        return True

    def __init__(self):
        self.target = None
        super().__init__()

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
                    use_create=False,
                )
            )
        return states

    def get_settings(self) -> dict:
        """Return a dictionary with settings that are already set"""

        settings = {}
        for name in self.property_keys:
            if not self.properties.is_property_set(name):
                continue
            settings[name] = getattr(self, name)
        return settings

    def sync_settings(self):
        """Sync operator properties that are not set with constraint's properties"""

        if self.initialized:
            return

        if not hasattr(self, "target"):
            return
        target = self.target
        if not target:
            return

        for key in self.property_keys:
            if self.properties.is_property_set(key):
                continue
            value = getattr(target, key)
            setprop(self.properties, key, value)

        # Note: setprop(self.properties, ...), setattr(self, ...) will both mark the operator
        # properties as set. Therefor is_property_set will always return True after the first
        # time a operator property has been synced. Ideally it would be possible to change property
        # values without marking them as set.

    def main(self, context: Context):
        self.sync_settings()

        deselect_all(context)
        solve_system(context, sketch=self.sketch)
        refresh(context)
        self.initialized = True
        return hasattr(self, "target") and bool(self.target)

    def fini(self, context: Context, succeede: bool):
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))

    def draw(self, context: Context):
        layout = self.layout

        c = self.target
        if not c:
            return

        for key in self.property_keys:
            layout.prop(self, key)

    def exists(self, context, constraint_type=None, max_constraints=1) -> bool:
        if hasattr(self, "entity2"):
            new_dependencies = [i for i in [self.entity1, self.entity2, self.sketch] if i is not None]
        else:
            new_dependencies = [i for i in [self.entity1, self.sketch] if i is not None]

        constraint_counter = 0
        for c in context.scene.sketcher.constraints.all:
            if isinstance(c, constraint_type):
                if set(c.dependencies()) == set(new_dependencies):
                    constraint_counter += 1
                    if constraint_counter >= max_constraints:
                        return True

        return False
