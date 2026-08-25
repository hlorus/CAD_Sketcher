import logging

from bpy.props import BoolProperty
from bpy.types import Context

from ..curve_solver import solve_system
from ..model.sketch_ref import get_active_constraints
from ..model.types import SlvsConstraints
from ..stateful_operator.state import state_from_args
from ..utilities.bpy import setprop
from ..utilities.curve_data import refresh_curve_geometry
from ..utilities.select import deselect_all
from ..utilities.view import refresh
from .base_2d import Operator2d

logger = logging.getLogger(__name__)

state_docstr = "Pick entity to constrain."


class GenericConstraintOp(Operator2d):
    initialized: BoolProperty(default=False, options={"SKIP_SAVE", "HIDDEN"})
    _entity_prop_names = ("entity1", "entity2", "entity3", "entity4")
    property_keys = ()
    has_value_state = False

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

        if cls.has_value_state:
            states.append(
                state_from_args(
                    "Value",
                    description="Type a value or confirm the measured value.",
                    property="value",
                    state_func="_current_constraint_value",
                    allow_prefill=False,
                    optional=True,
                )
            )

        return states

    def _current_constraint_value(self, _context, _coords):
        return self.value

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
        if self.sketch:
            refresh_curve_geometry(self.sketch)
        refresh(context)
        self.initialized = True
        return hasattr(self, "target") and bool(self.target)

    def fini(self, context: Context, succeede: bool):
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))

        # Placement of the dimension label is a display-only concern (draw_offset),
        # so it does not belong in this stateful creation operator's snapshot/solve
        # loop. Instead, hand a freshly created dimensional constraint off to the
        # dedicated tweak operator, which lets the user drag the label into place
        # (and enter a value) right after creation, as a plain modal with no
        # per-move solve.
        if succeede:
            self._handoff_placement(context)

    def _handoff_placement(self, context: Context):
        """Start the label-placement/value modal for a new dimensional constraint.

        The modal is started directly here: it comes up live and the creation
        click's leftover release is swallowed by the tweak operator's ``handoff``
        mode (rather than immediately confirming), after which mouse-moves place
        the label and a click confirms.
        """
        target = getattr(self, "target", None)
        if not target or not hasattr(target, "update_draw_offset"):
            return

        constraints = get_active_constraints(context)
        if not constraints:
            return
        index = constraints.get_index(target)
        if index < 0:
            return

        import bpy

        bpy.ops.view3d.slvs_tweak_constraint_value_pos(
            "INVOKE_DEFAULT", type=target.type, index=index, handoff=True
        )

    def draw(self, context: Context):
        layout = self.layout

        c = self.target
        if not c:
            return

        for key in self.property_keys:
            layout.prop(self, key)

    def exists(self, context, constraint_type=None, max_constraints=1) -> bool:
        new_cids = set()
        for name in self._entity_prop_names:
            e = getattr(self, name, None)
            if e and hasattr(e, "curve_id"):
                new_cids.add(e.curve_id)

        constraint_counter = 0
        for c in get_active_constraints(context).all:
            if isinstance(c, constraint_type):
                c_cids = set(c.curve_id_placements())
                if c_cids == new_cids:
                    constraint_counter += 1
                    if constraint_counter >= max_constraints:
                        return True

        return False
