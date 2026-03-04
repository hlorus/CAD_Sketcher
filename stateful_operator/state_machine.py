from typing import Optional

from .utilities.generic import to_list


class _StateMachineMixin:
    """Pure state machine: state definitions, data, and callback/property resolution.

    Has no dependency on Blender's modal operator system, numeric input, or snapshots.
    All methods here are usable as soon as ``states`` and ``state_index`` are defined.

    Subclasses must define
    ----------------------
    - ``states``: a list of ``OperatorState``, or a callable ``(operator=...)`` that
      returns one.
    - ``get_state_pointer(index, implicit)`` — provided by the integration layer.
    - ``set_state_pointer(values, index, implicit)`` — provided by the integration layer.
    """

    _state_data: dict = {}

    # -------------------------------------------------------------------------
    # State access
    # -------------------------------------------------------------------------

    @classmethod
    def get_states_definition(cls):
        """Return state list without an operator instance (e.g. at registration time)."""
        if callable(cls.states):
            return cls.states(operator=None)
        return cls.states

    def get_states(self):
        """Return the state list, passing self when states is a callable."""
        if callable(self.states):
            return self.states(operator=self)
        return self.states

    @property
    def state(self):
        return self.get_states()[self.state_index]

    @state.setter
    def state(self, state):
        self.state_index = self._index_from_state(state)

    def _index_from_state(self, state):
        return [e.name for e in self.get_states()].index(state)

    # -------------------------------------------------------------------------
    # Per-state data store
    # -------------------------------------------------------------------------

    @property
    def state_data(self):
        return self.get_state_data(self.state_index)

    def get_state_data(self, index):
        return self._state_data.setdefault(index, {})

    # -------------------------------------------------------------------------
    # Property and callback resolution
    # -------------------------------------------------------------------------

    def get_property(self, index: Optional[int] = None):
        """Return the operator property name(s) for the given state index."""
        if index is None:
            index = self.state_index
        state = self.get_states()[index]

        if state.property is None:
            return None

        if callable(state.property):
            props = state.property(self, index)
        elif state.property:
            attr = getattr(self, state.property, None)
            if callable(attr):
                props = attr(index)
            else:
                props = state.property
        elif hasattr(self, "state_property") and callable(self.state_property):
            props = self.state_property(index)
        else:
            return None

        return to_list(props)

    def get_func(self, state, name):
        """Resolve a callback from the state definition, falling back to an operator method.

        Priority
        --------
        1. ``state.<name>`` as a callable — used directly.
        2. ``state.<name>`` as a string — looked up as a method on ``self``.
        3. Operator method ``self.<name>`` — used as the default implementation.
        """
        func = getattr(state, name, None)

        if func:
            if isinstance(func, str):
                method = getattr(self, func, None)
                if method is None:
                    raise AttributeError(
                        f"{type(self).__name__} has no method '{func}' "
                        f"(referenced by state '{state.name}' field '{name}')"
                    )
                return method
            return func

        if hasattr(self, name):
            return getattr(self, name)
        return None

    def has_func(self, state, name):
        return self.get_func(state, name) is not None

    def state_func(self, context, coords):
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # State validation and inspection
    # -------------------------------------------------------------------------

    def check_props(self):
        """Return True when every non-optional state has its pointer/property set."""
        for i, state in enumerate(self.get_states()):
            if state.optional:
                continue
            if state.pointer:
                if not bool(self.get_state_pointer(index=i)):
                    return False
            else:
                props = self.get_property(index=i)
                if props:
                    for p in props:
                        if not self.properties.is_property_set(p):
                            return False
        return True

    def is_in_previous_states(self, entity):
        """Return True if *entity* is already used by an earlier state's pointer."""
        i = self.state_index - 1
        while i >= 0:
            state = self.get_states()[i]
            if state.pointer and entity == getattr(self, state.pointer):
                return True
            i -= 1
        return False

    # -------------------------------------------------------------------------
    # Abstract
    # -------------------------------------------------------------------------

    def gather_selection(self, context):
        raise NotImplementedError
