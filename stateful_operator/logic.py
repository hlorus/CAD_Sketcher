import bpy
from bpy.props import IntProperty, BoolProperty
from bpy.types import Context, Event
from mathutils import Vector

# TODO: Move to entity extended op
from .. import global_data

from .utilities.generic import to_list
from .utilities.description import state_desc, stateful_op_desc
from .utilities.keymap import (
    get_key_map_desc,
    is_numeric_input,
    is_unit_input,
    get_unit_value,
    get_value_from_event,
)

from typing import Optional


class StatefulOperatorLogic:
    """Base class which implements the behaviour logic"""

    state_index: IntProperty(options={"HIDDEN", "SKIP_SAVE"})
    wait_for_input: BoolProperty(options={"HIDDEN", "SKIP_SAVE"}, default=True)
    continuous_draw: BoolProperty(name="Continuous Draw", default=False)

    executed = False
    # Stores the returned value of state_func the first time it runs per state
    state_init_coords = None
    _state_data = {}
    _last_coords = Vector((0, 0))
    _numeric_input = {}
    _undo = False

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

        retval = to_list(props)
        return retval

    @classmethod
    def get_states_definition(cls):
        if callable(cls.states):
            return cls.states()
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

    def set_status_text(self, context: Context):
        # Setup state
        state = self.state
        desc = (
            state.description(self, state)
            if callable(state.description)
            else state.description
        )

        msg = state_desc(state.name, desc, state.types)
        if self.state_data.get("is_numeric_edit", False):
            index = self._substate_index
            prop = self._stateprop
            type = prop.type
            array_length = prop.array_length if prop.array_length else 1
            if type == "FLOAT":
                input = [0.0] * array_length
                for key, val in self._numeric_input.items():
                    input[key] = val

                input[index] = "*" + str(input[index])
                input = str(input).replace('"', "").replace("'", "")
            elif type == "INT":
                input = self.numeric_input

            msg += "    {}: {}".format(prop.subtype, input)

        context.workspace.status_text_set(msg)

    def check_numeric(self):
        """Check if the state supports numeric edit"""

        # TODO: Allow to define custom logic

        state = self.state
        props = self.get_property()

        # Disable for multi props
        if not props or len(props) > 1:
            return False

        prop_name = props[0]
        if not prop_name:
            return False

        prop = self.properties.rna_type.properties.get(prop_name)
        if not prop:
            return False

        if prop.type not in ("INT", "FLOAT"):
            return False
        return True

    def init_numeric(self, is_numeric):
        self._numeric_input = {}
        self._substate_index = 0

        ok = False
        if is_numeric:
            ok = self.check_numeric()
            # TODO: not when iterating substates
            self.state_data["is_numeric_edit"] = is_numeric and ok

        self.init_substate()
        return ok

    def init_substate(self):

        # Reset
        self._substate_count = None
        self._stateprop = None

        props = self.get_property()
        if not props:
            return
        if not props[0]:
            return

        prop_name = props[0]
        prop = self.properties.rna_type.properties.get(prop_name)
        if not prop:
            return

        self._substate_count = prop.array_length
        self._stateprop = prop

    def iterate_substate(self):
        i = self._substate_index
        if i + 1 >= self._substate_count:
            i = 0
        else:
            i += 1
        self._substate_index = i

    @property
    def numeric_input(self):
        return self._numeric_input.get(self._substate_index, "")

    @numeric_input.setter
    def numeric_input(self, value):
        self._numeric_input[self._substate_index] = value

    def check_event(self, event):
        state = self.state
        is_confirm_button = event.type in ("LEFTMOUSE", "RET", "NUMPAD_ENTER")

        if is_confirm_button and event.value == "PRESS":
            return True
        if self.state_index == 0 and not self.wait_for_input:
            # Trigger the first state
            return not self.state_data.get("is_numeric_edit", False)
        if state.no_event:
            return True
        return False

    def evaluate_numeric_event(self, event: Event):
        type = event.type
        if type == "BACK_SPACE":
            input = self.numeric_input
            if len(input):
                self.numeric_input = input[:-1]
            return

        if type in ("MINUS", "NUMPAD_MINUS"):
            input = self.numeric_input
            if input.startswith("-"):
                input = input[1:]
            else:
                input = "-" + input
            self.numeric_input = input
            return

        if is_unit_input(event):
            self.numeric_input += get_unit_value(event)
            return

        value = get_value_from_event(event)
        self.numeric_input += self.validate_numeric_input(value)

    def validate_numeric_input(self, value):
        """Check if existing input is valid after appending value"""
        num_input = self.numeric_input

        separators = (".", ",")
        if value in separators:
            if any([char in num_input for char in separators]):
                return ""
            if not len(num_input) or not num_input[-1].isdigit():
                return "0."
        return value

    def is_in_previous_states(self, entity):
        i = self.state_index - 1
        while True:
            if i < 0:
                break
            state = self.get_states()[i]
            if state.pointer and entity == getattr(self, state.pointer):
                return True
            i -= 1
        return False

    def prefill_state_props(self, context: Context):
        selected = self.gather_selection(context)
        states = self.get_states_definition()

        # Iterate states and try to prefill state props
        while True:
            index = self.state_index
            result = None
            state = self.state
            data = self.get_state_data(index)
            coords = None

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

    @property
    def state_data(self):
        return self._state_data.setdefault(self.state_index, {})

    def get_state_data(self, index):
        if not self._state_data.get(index):
            self._state_data[index] = {}
        return self._state_data[index]

    def get_func(self, state, name):
        # fallback to operator method if function isn't specified by state
        func = getattr(state, name, None)

        if func:
            if isinstance(func, str):
                # callback can be specified by function name
                return getattr(self, func)
            return func

        if hasattr(self, name):
            return getattr(self, name)
        return None

    def has_func(self, state, name):
        return self.get_func(state, name) is not None

    def state_func(self, context, coords):
        return NotImplementedError

    def invoke(self, context: Context, event: Event):
        self._state_data.clear()
        if hasattr(self, "init"):
            if not self.init(context, event):
                return self._end(context, False)

        retval = {"RUNNING_MODAL"}

        go_modal = True
        if is_numeric_input(event):
            if self.init_numeric(True):
                self.evaluate_numeric_event(event)
                retval = {"RUNNING_MODAL"}
                self.evaluate_state(context, event, False)

        # NOTE: This allows to start the operator but waits for action (LMB event).
        # Try to fill states based on selection only when this is True since it doesn't
        # make senese to respect selection when the user interactivley starts the operator.
        elif self.wait_for_input:
            retval = self.prefill_state_props(context)
            if retval == {"FINISHED"}:
                go_modal = False

            # NOTE: It might make sense to cancel Operator if no prop could be filled
            # Otherwise it might not be obvious that an operator is running
            # if self.state_index == 0:
            #     return self._end(context, False)

            if not self.executed and self.check_props():
                self.run_op(context)
                self.executed = True
            context.area.tag_redraw()  # doesn't seem to work...

        self.set_status_text(context)

        if go_modal:
            context.window.cursor_modal_set("CROSSHAIR")
            context.window_manager.modal_handler_add(self)
            return retval

        succeede = retval == {"FINISHED"}
        if succeede:
            # NOTE: It seems like there's no undo step pushed if an operator finishes from invoke
            # could push an undo_step here however this causes duplicated constraints after redo,
            # disable for now
            # bpy.ops.ed.undo_push()
            pass
        return self._end(context, succeede)

    def run_op(self, context: Context):
        if not hasattr(self, "main"):
            raise NotImplementedError(
                "StatefulOperators need to have a main method defined!"
            )
        retval = self.main(context)
        self.executed = True
        return retval

    # Creates non-persistent data
    def redo_states(self, context: Context):
        for i, state in enumerate(self.get_states()):
            if i > self.state_index:
                # TODO: don't depend on active state, idealy it's possible to go back
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
                    values = to_list(ret_values)
                    self.set_state_pointer(values, index=i, implicit=True)

    def execute(self, context: Context):
        self.redo_states(context)
        ok = self.main(context)
        return self._end(context, ok, skip_undo=True)
        # maybe allow to be modal again?

    def get_numeric_value(self, context: Context, coords):
        state = self.state
        prop_name = self.get_property()[0]
        prop = self.properties.rna_type.properties[prop_name]

        def parse_input(prop, input):
            units = context.scene.unit_settings
            unit = prop.unit
            type = prop.type
            value = None

            if input == "-":
                pass
            elif unit != "NONE":
                try:
                    value = bpy.utils.units.to_value(units.system, unit, input)
                except ValueError:
                    return prop.default
                if type == "INT":
                    value = int(value)
            elif type == "FLOAT":
                value = float(input)
            elif type == "INT":
                value = int(input)

            if value is None:
                return prop.default
            return value

        size = max(1, self._substate_count)

        def to_iterable(item):
            if hasattr(item, "__iter__") or hasattr(item, "__getitem__"):
                return list(item)
            return [
                item,
            ]

        # TODO: Don't evaluate if not needed
        interactive_val = self._get_state_values(context, state, coords)
        if interactive_val is None:
            interactive_val = [None] * size
        else:
            interactive_val = to_iterable(interactive_val)

        storage = [None] * size
        result = [None] * size

        for sub_index in range(size):
            num = None

            input = self._numeric_input.get(sub_index)
            if input:
                num = parse_input(prop, input)
                result[sub_index] = num
                storage[sub_index] = num
            elif interactive_val[sub_index] is not None:
                result[sub_index] = interactive_val[sub_index]
            else:
                result[sub_index] = prop.default

        self.state_data["numeric_input"] = storage

        if not self._substate_count:
            return result[0]
        return result

    def _handle_pass_through(self, context: Context, event: Event):
        # Only pass through navigation events
        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE", "MOUSEMOVE"}:
            return {"PASS_THROUGH"}
        return {"RUNNING_MODAL"}

    def modal(self, context: Context, event: Event):
        state = self.state
        event_triggered = self.check_event(event)
        coords = Vector((event.mouse_region_x, event.mouse_region_y))

        is_numeric_edit = self.state_data.get("is_numeric_edit", False)
        is_numeric_event = event.value == "PRESS" and is_numeric_input(event)

        if is_numeric_edit:
            if is_unit_input(event) and event.value == "PRESS":
                is_numeric_event = True
            elif event.type == "TAB" and event.value == "PRESS":
                self.iterate_substate()
                self.set_status_text(context)
        elif is_numeric_event:
            # Initialize
            is_numeric_edit = self.init_numeric(True)

        if event.type in {"RIGHTMOUSE", "ESC"}:
            return self._end(context, False)

        # HACK: when calling ops.ed.undo() inside an operator a mousemove event
        # is getting triggered. manually check if there's a mousemove...
        mousemove_threshold = 0.1
        is_mousemove = (coords - self._last_coords).length > mousemove_threshold
        self._last_coords = coords

        if not event_triggered:
            if is_numeric_event:
                pass
            elif is_mousemove and is_numeric_edit:
                event_triggered = False
                pass
            elif not state.interactive:
                return self._handle_pass_through(context, event)
            elif not is_mousemove:
                return self._handle_pass_through(context, event)

        # TODO: Disable numeric input when no state.property
        if is_numeric_event:
            self.evaluate_numeric_event(event)
            self.set_status_text(context)

        return self.evaluate_state(context, event, event_triggered)

    def _get_state_values(self, context: Context, state, coords):
        # Get values of state_func, can be none
        position_cb = self.get_func(state, "state_func")
        if not position_cb:
            return None
        pos_val = position_cb(context, coords)
        return pos_val

    def evaluate_state(self, context: Context, event, triggered):
        state = self.state
        data = self.state_data
        is_numeric = self.state_data.get("is_numeric_edit", False)
        coords = Vector((event.mouse_region_x, event.mouse_region_y))

        if self.state_init_coords is None:
            self.state_init_coords = coords

        # Pick hovered element
        hovered = None
        is_picked = False
        if not is_numeric and state.pointer:
            pick = self.get_func(state, "pick_element")
            pick_retval = pick(context, coords)

            if pick_retval is not None:
                is_picked = True
                pointer_values = to_list(pick_retval)

        # Set state property
        ok = False
        values = []
        use_create = state.use_create and self.has_func(state, "create_element")
        if use_create and not is_picked:
            if is_numeric:
                # numeric edit is supported for one property only
                values = [
                    self.get_numeric_value(context, coords),
                ]
            elif not is_picked:
                values = to_list(self._get_state_values(context, state, coords))

            if values:
                props = self.get_property()
                if props:
                    for i, v in enumerate(values):
                        setattr(self, props[i], v)
                    self._undo = True
                    ok = not state.pointer

        # Set state pointer
        pointer = None
        if state.pointer:
            if is_picked:
                pointer = pointer_values
                self.state_data["is_existing_entity"] = True
            elif values:
                # Let pointer be filled from redo_states
                self.state_data["is_existing_entity"] = False
                ok = True

            if pointer:
                self.set_state_pointer(pointer, implicit=True)
                ok = True

        if self._undo:
            bpy.ops.ed.undo_push(message="Redo: " + self.bl_label)
            bpy.ops.ed.undo()
            global_data.ignore_list.clear()
            self.redo_states(context)
            self._undo = False

        succeede = False
        if self.check_props():
            succeede = self.run_op(context)
            self._undo = True

        # Iterate state
        if triggered and ok:
            if not self.next_state(context):
                if self.check_continuous_draw():
                    self.do_continuous_draw(context)
                else:
                    return self._end(context, succeede)

            if is_numeric:
                # NOTE: Run next state already once even if there's no mousemove yet,
                # This is needed in order for the geometry to update
                self.evaluate_state(context, event, False)
        context.area.tag_redraw()

        if triggered and not ok:
            # Event was triggered on non-valid selection, cancel operator to avoid confusion
            return self._end(context, False)

        if triggered or is_numeric:
            return {"RUNNING_MODAL"}
        return self._handle_pass_through(context, event)

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

    def do_continuous_draw(self, context):
        # end operator
        self._end(context, True)
        bpy.ops.ed.undo_push(message=self.bl_label)

        # save last prop
        last_pointer = None
        for i, s in reversed(list(enumerate(self.get_states()))):
            if not s.pointer:
                continue
            last_index = i
            last_pointer = getattr(self, s.pointer)
            break

        values = to_list(self.get_state_pointer(index=last_index, implicit=True))

        # reset operator
        self._reset_op()

        data = {}
        self._state_data[0] = data
        data["is_existing_entity"] = True
        data["type"] = type(last_pointer)

        # set first pointer
        self.set_state_pointer(values, index=0, implicit=True)
        self.set_state(context, 1)

    def _end(self, context, succeede, skip_undo=False):
        context.window.cursor_modal_restore()
        if hasattr(self, "fini"):
            self.fini(context, succeede)
        global_data.ignore_list.clear()

        context.workspace.status_text_set(None)

        if not succeede and not skip_undo:
            bpy.ops.ed.undo_push(message="Cancelled: " + self.bl_label)
            bpy.ops.ed.undo()

        retval = {"FINISHED"} if succeede else {"CANCELLED"}
        return retval

    def check_props(self):
        for i, state in enumerate(self.get_states()):

            if state.optional:
                continue

            props = self.get_property(index=i)
            if state.pointer:
                if not bool(self.get_state_pointer(index=i)):
                    return False

            elif props:
                for p in props:
                    if not self.properties.is_property_set(p):
                        return False
        return True

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

    # Dummy methods
    def gather_selection(self, context: Context):
        raise NotImplementedError
