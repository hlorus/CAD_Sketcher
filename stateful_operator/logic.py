import bpy
from bpy.props import IntProperty, BoolProperty
from bpy.types import Context, Event
from mathutils import Vector

from .utilities.generic import to_list
from .utilities.description import state_desc, stateful_op_desc
from .utilities.keymap import get_key_map_desc, is_numeric_input, is_unit_input
from .utilities.numeric import NumericInput

from typing import Optional, Any

# Re-export so existing `from .logic import _NumericInput` imports keep working.
_NumericInput = NumericInput


class StatefulOperatorLogic:
    """Base class which implements the stateful operator behaviour.

    Subclasses must define a ``states`` attribute (list or callable returning a
    list of ``OperatorState``) and a ``main(context)`` method.

    Lifecycle (modal path)
    ----------------------
    invoke → prefill_state_props (optional) → modal loop:
        modal → evaluate_state → [next_state | _end | do_continuous_draw]

    Lifecycle (redo/execute path)
    -----------------------------
    execute → redo_states → main → _end
    """

    state_index: IntProperty(options={"HIDDEN", "SKIP_SAVE"})
    wait_for_input: BoolProperty(options={"HIDDEN", "SKIP_SAVE"}, default=True)
    continuous_draw: BoolProperty(name="Continuous Draw", default=False)

    executed = False
    # Stores the screen coords when a state first runs (used by state_func for delta/scale)
    state_init_coords = None
    _state_data = {}
    _last_coords = Vector((0, 0))
    _undo = False
    _state_snapshot = None

    # -------------------------------------------------------------------------
    # Snapshot / undo hooks (override in subclasses)
    # -------------------------------------------------------------------------

    def create_snapshot(self, context: Context) -> Any:
        """Return a snapshot of state to restore on cancel/undo.

        Return ``None`` to fall back to Blender's undo system.
        """
        return None

    def restore_snapshot(self, context: Context, snapshot: Any) -> None:
        """Restore state from a snapshot produced by ``create_snapshot``."""
        pass

    def on_before_redo_states(self, context: Context):
        """Called before ``redo_states`` during undo/redo cycles.

        Override to clear transient state that must be rebuilt
        (e.g. entity ignore lists used by draw handlers).
        """
        pass

    # -------------------------------------------------------------------------
    # State machine — states, transitions, data
    # -------------------------------------------------------------------------

    @classmethod
    def get_states_definition(cls):
        if callable(cls.states):
            return cls.states(operator=None)
        return cls.states

    def get_states(self):
        if callable(self.states):
            return self.states(operator=self)
        return self.states

    @property
    def state(self):
        return self.get_states()[self.state_index]

    def _index_from_state(self, state):
        return [e.name for e in self.get_states()].index(state)

    @state.setter
    def state(self, state):
        self.state_index = self._index_from_state(state)

    def set_state(self, context: Context, index: int):
        self.state_index = index
        self.init_numeric(False)
        self.set_status_text(context)

    def next_state(self, context: Context):
        self._undo = False
        self.state_init_coords = None
        i = self.state_index
        if (i + 1) >= len(self.get_states()):
            return False
        self.set_state(context, i + 1)
        return True

    @property
    def state_data(self):
        return self.get_state_data(self.state_index)

    def get_state_data(self, index):
        return self._state_data.setdefault(index, {})

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
    # Property / callback resolution
    # -------------------------------------------------------------------------

    def get_property(self, index: Optional[int] = None):
        if index is None:
            index = self.state_index
        state = self.get_states()[index]

        if state.property is None:
            return None

        if callable(state.property):
            props = state.property(self, index)
        elif state.property:
            if callable(getattr(self, state.property)):
                props = getattr(self, state.property)(index)
            else:
                props = state.property
        elif hasattr(self, "state_property") and callable(self.state_property):
            props = self.state_property(index)
        else:
            return None

        return to_list(props)

    def get_func(self, state, name):
        """Resolve a callback from the state definition, falling back to operator method.

        A callback can be specified as:
        - a callable on the state directly
        - a string naming a method on the operator
        - absent, in which case the operator method of the same name is used
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
    # Numeric input — delegates to self._numeric (NumericInput)
    # -------------------------------------------------------------------------

    def set_status_text(self, context: Context):
        state = self.state
        desc = (
            state.description(self, state)
            if callable(state.description)
            else state.description
        )

        msg = state_desc(state.name, desc, state.types)
        if self._numeric.is_active:
            prop = self._numeric.prop
            index = self._numeric.substate_index
            array_length = prop.array_length if prop.array_length else 1

            if prop.type == "FLOAT":
                display = [0.0] * array_length
                for key in range(array_length):
                    val = self._numeric.get(key)
                    display[key] = val if val else 0.0
                display[index] = "*" + str(display[index])
                display_str = str(display).replace('"', "").replace("'", "")
                msg += "    {}: {}".format(prop.subtype, display_str)
            elif prop.type == "INT":
                msg += "    {}: {}".format(prop.subtype, self._numeric.current)

        context.workspace.status_text_set(msg)

    def check_numeric(self):
        """Return True if the current state supports numeric text entry."""
        # TODO: Allow to define custom logic
        props = self.get_property()
        if not props or len(props) > 1:
            return False
        prop_name = props[0]
        if not prop_name:
            return False
        prop = self.properties.rna_type.properties.get(prop_name)
        if not prop:
            return False
        return prop.type in ("INT", "FLOAT")

    def init_numeric(self, is_numeric: bool) -> bool:
        self._numeric.reset()
        if not is_numeric:
            self._init_substate()
            return False
        ok = self.check_numeric()
        self._numeric.is_active = ok
        self._init_substate()
        return ok

    def _init_substate(self):
        """Resolve the rna property for the current state and cache it on _numeric."""
        props = self.get_property()
        if not props or not props[0]:
            return
        prop = self.properties.rna_type.properties.get(props[0])
        self._numeric.init_substate(prop)

    # Public wrappers — kept for API compatibility with operator subclasses

    def iterate_substate(self):
        self._numeric.iterate()

    @property
    def numeric_input(self) -> str:
        return self._numeric.current

    @numeric_input.setter
    def numeric_input(self, value: str):
        self._numeric.current = value

    def evaluate_numeric_event(self, event: Event):
        self._numeric.evaluate_event(event)

    def validate_numeric_input(self, value: str) -> str:
        return self._numeric._validate(value)

    def get_numeric_value(self, context: Context, coords):
        """Convert the current numeric text buffer to a typed value (or list)."""
        prop_name = self.get_property()[0]
        prop = self.properties.rna_type.properties[prop_name]

        def parse_input(prop, raw):
            units = context.scene.unit_settings
            unit = prop.unit
            value = None
            if raw == "-":
                pass
            elif unit != "NONE":
                try:
                    value = bpy.utils.units.to_value(units.system, unit, raw)
                except ValueError:
                    return prop.default
                if prop.type == "INT":
                    value = int(value)
            elif prop.type == "FLOAT":
                value = float(raw)
            elif prop.type == "INT":
                value = int(raw)
            return prop.default if value is None else value

        def to_iterable(item):
            if hasattr(item, "__iter__") or hasattr(item, "__getitem__"):
                return list(item)
            return [item]

        size = max(1, self._numeric.substate_count or 0)

        # TODO: Don't evaluate interactive value if not needed
        interactive_val = self._get_state_values(context, self.state, coords)
        if interactive_val is None:
            interactive_val = [None] * size
        else:
            interactive_val = to_iterable(interactive_val)

        storage = [None] * size
        result = [None] * size
        for sub_index in range(size):
            raw = self._numeric.get(sub_index)
            if raw:
                num = parse_input(prop, raw)
                result[sub_index] = num
                storage[sub_index] = num
            elif interactive_val[sub_index] is not None:
                result[sub_index] = interactive_val[sub_index]
            else:
                result[sub_index] = prop.default

        self.state_data["numeric_input"] = storage
        return result[0] if not self._numeric.substate_count else result

    # -------------------------------------------------------------------------
    # Selection prefill
    # -------------------------------------------------------------------------

    def prefill_state_props(self, context: Context):
        selected = self.gather_selection(context)

        while True:
            index = self.state_index
            state = self.state
            self.get_state_data(index)

            if not state.allow_prefill:
                break

            func = self.get_func(state, "parse_selection")
            result = func(context, selected, index=index)

            if result:
                if not self.next_state(context):
                    return {"FINISHED"}
                continue
            break
        return {"RUNNING_MODAL"}

    # -------------------------------------------------------------------------
    # Operator lifecycle — invoke / modal / execute / _end
    # -------------------------------------------------------------------------

    def check_event(self, event):
        is_confirm = event.type in ("LEFTMOUSE", "RET", "NUMPAD_ENTER")
        if is_confirm and event.value == "PRESS":
            return True
        if self.state_index == 0 and not self.wait_for_input:
            return not self._numeric.is_active
        if self.state.no_event:
            return True
        return False

    def invoke(self, context: Context, event: Event):
        self._state_data.clear()
        self._numeric = NumericInput()
        self._state_snapshot = self.create_snapshot(context)

        if hasattr(self, "init"):
            if not self.init(context, event):
                return self._end(context, False)

        retval = {"RUNNING_MODAL"}
        go_modal = True

        if is_numeric_input(event):
            if self.init_numeric(True):
                self._numeric.evaluate_event(event)
                self.evaluate_state(context, event, False)

        # wait_for_input=True: respect selection for prefill, but wait for LMB
        elif self.wait_for_input:
            retval = self.prefill_state_props(context)
            if retval == {"FINISHED"}:
                go_modal = False
            if not self.executed and self.check_props():
                self.run_op(context)
                self.executed = True
            context.area.tag_redraw()

        self.set_status_text(context)

        if go_modal:
            context.window.cursor_modal_set("CROSSHAIR")
            context.window_manager.modal_handler_add(self)
            return retval

        succeede = retval == {"FINISHED"}
        # NOTE: It seems like there's no undo step pushed if an operator finishes
        # from invoke. Pushing one here causes duplicated constraints after redo.
        return self._end(context, succeede)

    def execute(self, context: Context):
        self._numeric = NumericInput()
        self.redo_states(context)
        ok = self.main(context)
        return self._end(context, ok, skip_undo=True)

    def _handle_pass_through(self, context: Context, event: Event):
        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE", "MOUSEMOVE"}:
            return {"PASS_THROUGH"}
        return {"RUNNING_MODAL"}

    def modal(self, context: Context, event: Event):
        state = self.state
        event_triggered = self.check_event(event)
        coords = Vector((event.mouse_region_x, event.mouse_region_y))

        is_numeric_edit = self._numeric.is_active
        is_numeric_event = event.value == "PRESS" and is_numeric_input(event)

        if is_numeric_edit:
            if is_unit_input(event) and event.value == "PRESS":
                is_numeric_event = True
            elif event.type == "TAB" and event.value == "PRESS":
                self._numeric.iterate()
                self.set_status_text(context)
        elif is_numeric_event:
            is_numeric_edit = self.init_numeric(True)

        if event.type in {"RIGHTMOUSE", "ESC"}:
            return self._end(context, False)

        # HACK: calling ops.ed.undo() inside a modal triggers a spurious MOUSEMOVE.
        # Check actual pixel movement to filter it out.
        mousemove_threshold = 0.1
        is_mousemove = (coords - self._last_coords).length > mousemove_threshold
        self._last_coords = coords

        if not event_triggered:
            if is_numeric_event:
                pass
            elif is_mousemove and is_numeric_edit:
                pass
            elif not state.interactive:
                return self._handle_pass_through(context, event)
            elif not is_mousemove:
                return self._handle_pass_through(context, event)

        # TODO: Disable numeric input when no state.property
        if is_numeric_event:
            self._numeric.evaluate_event(event)
            self.set_status_text(context)

        return self.evaluate_state(context, event, event_triggered)

    # -------------------------------------------------------------------------
    # evaluate_state and its sub-steps
    # -------------------------------------------------------------------------

    def _get_state_values(self, context: Context, state, coords):
        """Call the state's state_func and return raw position/value, or None."""
        cb = self.get_func(state, "state_func")
        if not cb:
            return None
        return cb(context, coords)

    def _pick_hovered(self, context: Context, coords, state, is_numeric):
        """Try to pick an existing element under the cursor.

        Returns ``(is_picked, pointer_values)`` — pointer_values is only
        meaningful when is_picked is True.
        """
        if is_numeric or not state.pointer:
            return False, None
        pick = self.get_func(state, "pick_element")
        retval = pick(context, coords)
        if retval is not None:
            return True, to_list(retval)
        return False, None

    def _resolve_values(self, context: Context, coords, state, is_numeric, is_picked):
        """Compute property values for the current state via state_func or numeric input.

        Returns ``(values, ok)`` — ok indicates the state can advance.
        Sets properties on self and marks ``_undo`` if values were produced.
        """
        ok = False
        values = []
        use_create = state.use_create and self.has_func(state, "create_element")
        if not use_create or is_picked:
            return values, ok

        if is_numeric:
            values = [self.get_numeric_value(context, coords)]
        else:
            values = to_list(self._get_state_values(context, state, coords))

        if values:
            props = self.get_property()
            if props:
                for i, v in enumerate(values):
                    setattr(self, props[i], v)
                self._undo = True
                ok = not state.pointer

        return values, ok

    def _apply_undo(self, context: Context):
        """Restore state to snapshot/undo and replay redo_states."""
        if self._state_snapshot is not None:
            self.restore_snapshot(context, self._state_snapshot)
            self.on_before_redo_states(context)
            self.redo_states(context)
        else:
            bpy.ops.ed.undo_push(message="Redo: " + self.bl_label)
            bpy.ops.ed.undo()
            self.on_before_redo_states(context)
            self.redo_states(context)
        self._undo = False

    def evaluate_state(self, context: Context, event, triggered):
        state = self.state
        data = self.state_data
        is_numeric = self._numeric.is_active
        coords = Vector((event.mouse_region_x, event.mouse_region_y))

        if self.state_init_coords is None:
            self.state_init_coords = coords

        is_picked, pointer_values = self._pick_hovered(context, coords, state, is_numeric)
        values, ok = self._resolve_values(context, coords, state, is_numeric, is_picked)

        # Resolve state pointer
        if state.pointer:
            if is_picked:
                data["is_existing_entity"] = True
                self.set_state_pointer(pointer_values, implicit=True)
                ok = True
            elif values:
                # pointer will be filled during redo_states via create_element
                data["is_existing_entity"] = False
                ok = True

        if self._undo:
            self._apply_undo(context)

        succeede = False
        if self.check_props():
            succeede = self.run_op(context)
            self._undo = True

        # State transition
        if triggered and ok:
            if not self.next_state(context):
                if self.check_continuous_draw():
                    self.do_continuous_draw(context)
                else:
                    return self._end(context, succeede)
            if is_numeric:
                # Run next state once immediately so geometry updates without a mousemove
                self.evaluate_state(context, event, False)

        context.area.tag_redraw()

        if triggered and not ok:
            # Triggered on non-valid target — cancel to avoid confusion
            return self._end(context, False)

        if triggered or is_numeric:
            return {"RUNNING_MODAL"}
        return self._handle_pass_through(context, event)

    # -------------------------------------------------------------------------
    # Operator execution helpers
    # -------------------------------------------------------------------------

    def run_op(self, context: Context):
        if not hasattr(self, "main"):
            raise NotImplementedError(
                "StatefulOperators need to have a main method defined!"
            )
        retval = self.main(context)
        self.executed = True
        return retval

    def redo_states(self, context: Context):
        """Recreate non-persistent elements for states up to the current one."""
        for i, state in enumerate(self.get_states()):
            if i > self.state_index:
                # TODO: don't depend on active state; ideally going back is possible
                break
            if state.pointer:
                data = self._state_data.get(i, {})
                is_existing_entity = data["is_existing_entity"]
                props = self.get_property(index=i)
                if props and not is_existing_entity:
                    create = self.get_func(state, "create_element")
                    ret_values = create(
                        context, [getattr(self, p) for p in props], state, data
                    )
                    self.set_state_pointer(to_list(ret_values), index=i, implicit=True)

    def _end(self, context, succeede, skip_undo=False):
        context.window.cursor_modal_restore()
        if hasattr(self, "fini"):
            self.fini(context, succeede)
        self.on_before_redo_states(context)
        context.workspace.status_text_set(None)

        if not succeede and not skip_undo:
            if self._state_snapshot is not None:
                self.restore_snapshot(context, self._state_snapshot)
            else:
                bpy.ops.ed.undo_push(message="Cancelled: " + self.bl_label)
                bpy.ops.ed.undo()

        self._state_snapshot = None
        return {"FINISHED"} if succeede else {"CANCELLED"}

    # -------------------------------------------------------------------------
    # Continuous draw
    # -------------------------------------------------------------------------

    def check_continuous_draw(self):
        if self.continuous_draw:
            if not hasattr(self, "continue_draw") or self.continue_draw():
                return True
        return False

    def _reset_op(self):
        self.executed = False
        for i, s in enumerate(self.get_states()):
            if not s.pointer:
                continue
            self.set_state_pointer(None, index=i)
        self._state_data.clear()
        self._numeric = NumericInput()
        self._state_snapshot = None

    def _take_last_state_pointer(self):
        """Return (last_index, implicit_values, type_metadata) for the last pointer state."""
        for i, s in reversed(list(enumerate(self.get_states()))):
            if not s.pointer:
                continue
            last_type = self._state_data.get(i, {}).get("type")
            values = to_list(self.get_state_pointer(index=i, implicit=True))
            return i, values, last_type
        return None, [], None

    def do_continuous_draw(self, context):
        """Finish the current segment and immediately start the next one.

        The last pointer of the finished segment (e.g. a line endpoint)
        becomes the first pointer of the new segment, creating a chain.
        """
        self._end(context, True)
        bpy.ops.ed.undo_push(message=self.bl_label)

        # Save the endpoint before _reset_op wipes state
        last_index, values, last_type = self._take_last_state_pointer()

        self._reset_op()

        # Re-inject the saved endpoint as the seed for the new segment
        data = self.get_state_data(0)
        data["is_existing_entity"] = True
        if last_type:
            data["type"] = last_type
        self.set_state_pointer(values, index=0, implicit=True)
        self.set_state(context, 1)
        self._state_snapshot = self.create_snapshot(context)

    # -------------------------------------------------------------------------
    # Class-level description
    # -------------------------------------------------------------------------

    @classmethod
    def description(cls, context, _properties):
        states = [
            state_desc(s.name, s.description, s.types)
            for s in cls.get_states_definition()
        ]
        descs = []
        hint = get_key_map_desc(context, cls.bl_idname)
        if hint:
            descs.append(hint)
        if cls.__doc__:
            descs.append(cls.__doc__)
        return stateful_op_desc(" ".join(descs), *states)

    # -------------------------------------------------------------------------
    # Abstract — must be implemented by subclasses
    # -------------------------------------------------------------------------

    def gather_selection(self, context: Context):
        raise NotImplementedError
