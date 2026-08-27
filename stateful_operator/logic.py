import math
from typing import Any

import bpy
from bpy.props import BoolProperty, IntProperty
from bpy.types import Context, Event
from mathutils import Vector

from .. import global_data
from .state_machine import _StateMachineMixin
from .utilities.description import state_desc, stateful_op_desc
from .utilities.generic import to_list
from .utilities.keymap import get_key_map_desc, is_numeric_input, is_unit_input
from .utilities.numeric import NumericInput, parse_numeric

# Re-export so any `from .logic import _NumericInput` keeps working.
_NumericInput = NumericInput


class StatefulOperatorLogic(_StateMachineMixin):
    """Stateful operator behaviour: numeric input, modal loop, undo, continuous draw.

    Inherits the pure state machine from ``_StateMachineMixin``.

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
    # >= 0 -> re-enter to edit just that state: restore the persisted input, let
    # the user re-pick that one state, then re-apply idempotently. -1 = normal.
    edit_state: IntProperty(default=-1, options={"HIDDEN", "SKIP_SAVE"})

    executed = False
    # Tool id to activate once the operator succeeds (see _end). Lets a one-off
    # tool return to a select tool afterwards instead of lingering; None keeps
    # the current tool. On failure/cancel the tool is left alone so a missed
    # pick can be retried.
    return_to_tool = None
    # Screen coords when a state first runs — used by state_func for delta/scale
    state_init_coords = None
    _last_coords = Vector((0, 0))
    _undo = False
    _state_snapshot = None
    # Global axis constraint (0=X, 1=Y, 2=Z, or None) for the current vector
    # state, toggled with the X/Y/Z keys and applied by the state's state_func.
    _axis_lock = None
    # Formatted live value of the current state, shown in the status bar.
    _status_value = None

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
    # State transitions (depend on numeric + status text — stay here)
    # -------------------------------------------------------------------------

    def set_state(self, context: Context, index: int):
        self.state_index = index
        self.init_numeric(False)
        self._axis_lock = None
        self._status_value = None
        self.set_status_text(context)
        # Publish the new state's accepted pick types so the hover gizmo
        # highlights what this state will pick. Clear any existing hover when
        # the new state picks nothing (a property/interactive state), since it
        # consumes mouse-moves and the gizmo won't fire to clear it.
        global_data.hover_types = self.get_states()[index].types
        if not global_data.hover_types:
            global_data.hover_element = None

    def next_state(self, context: Context):
        self._undo = False
        self.state_init_coords = None
        i = self.state_index
        if (i + 1) >= len(self.get_states()):
            return False
        self.set_state(context, i + 1)
        return True

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
        elif self._status_value:
            # Live value while modifying a state (property or point placement).
            msg += "    {}: {}".format(state.name, self._status_value)

        if self._axis_lock is not None:
            msg += "    [{} axis]".format("XYZ"[self._axis_lock])

        context.workspace.status_text_set(msg)

    def _format_values(self, values):
        """Format resolved state values (vectors / floats / ints) for display.

        Angle-subtype properties are shown in degrees to match how Blender
        presents them everywhere else.
        """
        props = self.get_property() or []
        parts = []
        for i, v in enumerate(values):
            subtype = None
            if i < len(props):
                prop = self.rna_type.properties.get(props[i])
                subtype = prop.subtype if prop else None
            if hasattr(v, "__len__") and not isinstance(v, str):
                parts.append("(" + ", ".join("{:.3f}".format(x) for x in v) + ")")
            elif isinstance(v, float):
                if subtype == "ANGLE":
                    parts.append("{:.1f}°".format(math.degrees(v)))
                else:
                    parts.append("{:.3f}".format(v))
            else:
                parts.append(str(v))
        return ", ".join(parts)

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
        unit_system = context.scene.unit_settings.system

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
                num = parse_numeric(prop, raw, unit_system)
                if num is None:
                    num = prop.default
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
        global_data.stateful_op_running = True
        self._state_data.clear()
        self._numeric = NumericInput()

        if self.edit_state >= 0:
            return self._invoke_edit(context, event)

        entered_modal = False
        global_data.hover_types = self.get_states()[0].types
        self._state_snapshot = self.create_snapshot(context)
        try:
            if hasattr(self, "init"):
                if not self.init(context, event):
                    return self._end(context, False)
            self._capture_baseline(context)

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
                entered_modal = True
                return retval

            succeede = retval == {"FINISHED"}
            # NOTE: Pushing an undo step here causes duplicated constraints after redo.
            return self._end(context, succeede)
        finally:
            if not entered_modal and global_data.stateful_op_running:
                global_data.stateful_op_running = False

    # -------------------------------------------------------------------------
    # Edit-state re-entry (re-pick one state of a finished op, idempotently)
    # -------------------------------------------------------------------------

    def _invoke_edit(self, context: Context, event: Event):
        """Re-enter to edit a single state: restore the persisted input, then let
        the user re-pick just ``edit_state``. Invoked top-level from the redo
        panel, so the re-applied op becomes the adjustable last operation."""
        if hasattr(self, "init"):
            # Load assets etc.; entity ops also set _active_sketch here.
            if not self.init(context, event):
                return self._end_edit(context, False)
        # Rebuild every state from the forwarded/persisted props, then clear the
        # one being edited so the user picks it fresh. No snapshot -- idempotent
        # apply (_run_main) replaces this op's own output.
        self._state_snapshot = None
        self._restore_pointers()
        # Let subclasses snapshot pre-re-pick state (the target being edited away
        # from) before the user changes it -- e.g. node ops relocating a modifier.
        self._prepare_edit(context)
        i = self.edit_state
        self.get_state_data(i).pop("type", None)
        self.set_state(context, i)
        global_data.hover_types = self.get_states()[i].types
        # Make the op's hover/preselection UI available for the re-pick even
        # though the workspace tool that normally owns it isn't active.
        self._prepare_pick_ui(context)
        context.window.cursor_modal_set("EYEDROPPER")
        self.set_status_text(context)
        # A modal invoked from a redo-panel button can stall waiting for its first
        # event (the button-click context delivers none until the mouse moves).
        # A modal timer keeps it ticking so it becomes responsive immediately.
        self._edit_timer = context.window_manager.event_timer_add(
            0.05, window=context.window
        )
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _modal_edit(self, context: Context, event: Event):
        # Clicking the eyedropper button in the redo panel makes Blender also
        # re-run the previous operator's execute()/_end() (an implicit undo +
        # re-apply). That nulls the shared global_data.hover_types this edit modal
        # set, and reverts any state _prepare_pick_ui changed (e.g. a hidden
        # modifier). Re-assert both every event so the pick keeps working.
        global_data.hover_types = self.get_states()[self.edit_state].types
        self._maintain_pick_ui(context)
        if event.type in {"RIGHTMOUSE", "ESC"} and event.value == "PRESS":
            return self._end_edit(context, False)
        if event.type == "TIMER":
            return {"RUNNING_MODAL"}  # just keeps the modal responsive
        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            coords = Vector((event.mouse_region_x, event.mouse_region_y))
            is_picked, values = self._pick_hovered(context, coords, self.state, False)
            if not is_picked:
                return {"RUNNING_MODAL"}  # missed a target -- keep waiting
            self.state_data["is_existing_entity"] = True
            self.set_state_pointer(values, implicit=True)
            self._store_pointers()
            ok = self._reapply(context)
            if context.area:
                context.area.tag_redraw()
            return self._end_edit(context, ok)
        if event.type == "MOUSEMOVE":
            # Gizmos don't run their hover test while a modal operator is active,
            # so drive the hover highlight ourselves for the re-pick.
            coords = Vector((event.mouse_region_x, event.mouse_region_y))
            self._update_pick_hover(context, coords)
        return self._handle_pass_through(context, event)

    def _end_edit(self, context: Context, ok: bool):
        timer = getattr(self, "_edit_timer", None)
        if timer is not None:
            context.window_manager.event_timer_remove(timer)
            self._edit_timer = None
        self._finish_pick_ui(context)
        context.window.cursor_modal_restore()
        context.workspace.status_text_set(None)
        global_data.hover_types = None
        global_data.hover_element = None
        global_data.stateful_op_running = False
        return {"FINISHED"} if ok else {"CANCELLED"}

    def execute(self, context: Context):
        global_data.stateful_op_running = True
        try:
            self._numeric = NumericInput()
            ok = self._reapply(context)
            return self._end(context, ok, skip_undo=True)
        finally:
            if global_data.stateful_op_running:
                global_data.stateful_op_running = False

    def _run_main(self, context: Context):
        """Invoke ``main``; a hook for subclasses to make apply idempotent
        (e.g. entity ops that own + replace their created output)."""
        return self.main(context)

    def _reapply(self, context: Context):
        """Rebuild everything from persisted state and run main -- the shared
        execute / redo-panel / edit-re-pick path. Default: redo_states + main.
        Subclasses that own their output (Operator2d) remove it first so their
        stable-id recreation doesn't collide with the still-present old copy."""
        self.redo_states(context)
        return self._run_main(context)

    def _prepare_edit(self, context: Context):
        """Hook: called in the edit re-pick invoke, after the persisted state is
        restored but before the user re-picks edit_state. Lets a subclass capture
        what it is editing away from (default no-op)."""
        pass

    def _prepare_pick_ui(self, context: Context):
        """Hook: called when the edit re-pick modal starts. Lets a subclass make
        its hover/preselection UI available even though the workspace tool that
        owns it isn't active (e.g. ensure a gizmo group is linked, or reveal
        geometry a modifier is hiding). Default no-op."""
        pass

    def _finish_pick_ui(self, context: Context):
        """Hook: called when the edit re-pick modal ends. Undo whatever
        ``_prepare_pick_ui`` set up. Default no-op."""
        pass

    def _update_pick_hover(self, context: Context, coords):
        """Hook: called on mouse-move during the edit re-pick to refresh the
        hover highlight (gizmos don't run their hover test during a modal).
        Default no-op."""
        pass

    def _maintain_pick_ui(self, context: Context):
        """Hook: called on every edit-modal event to re-assert whatever
        ``_prepare_pick_ui`` set up, since a redo-panel re-run can revert it.
        Default no-op."""
        pass

    def _capture_baseline(self, context: Context):
        """Hook: record the state before the op runs (for output ownership)."""
        pass

    def _record_committed_output(self, context: Context):
        """Hook: after a successful commit, record what the op created."""
        pass

    def _handle_pass_through(self, context: Context, event: Event):
        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE", "MOUSEMOVE"}:
            return {"PASS_THROUGH"}
        return {"RUNNING_MODAL"}

    def modal(self, context: Context, event: Event):
        if self.edit_state >= 0:
            return self._modal_edit(context, event)

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

        # Global axis constraint (X/Y/Z), only for states that opt in and apply
        # self._axis_lock in their state_func — toggle and re-run so the preview
        # updates.
        if (
            event.value == "PRESS"
            and event.type in ("X", "Y", "Z")
            and getattr(state, "axis_lock", False)
        ):
            axis = "XYZ".index(event.type)
            self._axis_lock = None if self._axis_lock == axis else axis
            self.set_status_text(context)
            return self.evaluate_state(context, event, False)

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
        """Call the state's state_func and return the raw position/value, or None."""
        cb = self.get_func(state, "state_func")
        if not cb:
            return None
        return cb(context, coords)

    def _pick_hovered(self, context: Context, coords, state, is_numeric):
        """Try to pick an existing element under the cursor.

        Returns ``(is_picked, pointer_values)`` — pointer_values only valid when
        is_picked is True.
        """
        if is_numeric or not state.pointer:
            return False, None
        pick = self.get_func(state, "pick_element")
        retval = pick(context, coords)
        if retval is not None:
            return True, to_list(retval)
        return False, None

    def _resolve_values(self, context: Context, coords, state, is_numeric, is_picked):
        """Compute property values via state_func or numeric input.

        Returns ``(values, ok)`` — ok indicates the state can advance.
        Sets properties on self and marks ``_undo`` when values are produced.
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
        """Restore to snapshot or Blender undo, then replay redo_states."""
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

        is_picked, pointer_values = self._pick_hovered(
            context, coords, state, is_numeric
        )
        values, ok = self._resolve_values(context, coords, state, is_numeric, is_picked)

        # Reflect the live value (property or point placement) in the status bar.
        if not is_numeric:
            self._status_value = self._format_values(values) if values else None
            self.set_status_text(context)

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
        # Capture the picked pointers so a later redo (fresh instance) can
        # rebuild them; this runs on every live update, keeping it current.
        self._store_pointers()
        retval = self._run_main(context)
        self.executed = True
        return retval

    # -------------------------------------------------------------------------
    # Pointer persistence (survives the redo/execute path)
    # -------------------------------------------------------------------------
    #
    # Each pointer state's identity is stored in hidden, per-state real
    # properties (registered by register_properties): ``ptr{i}_kind`` (the
    # picked type's __name__), ``ptr{i}_existing`` (is_existing_entity), and the
    # implicit value split into a string slot ``ptr{i}_name`` + int slot
    # ``ptr{i}_index``. Blender persists these across the redo/execute path (a
    # fresh instance), where the transient _state_data is gone.

    def _pointer_type_registry(self):
        """Map a pointer type's ``__name__`` back to the class, for redo restore.

        Base is empty; the integration layer adds native Blender types and the
        extension layer adds its entity/curve-ref types.
        """
        return {}

    @staticmethod
    def _pack_pointer_vals(vals):
        """Split implicit pointer values into a (name, index) pair for storage.

        Implicit values are at most one string id (object name / curve_id) and
        one int (mesh element index / entity index); -1 marks "no int".
        """
        name, index = "", -1
        for v in vals:
            if isinstance(v, bool):
                continue
            if isinstance(v, str):
                name = v
            elif isinstance(v, int):
                index = v
        return name, index

    @staticmethod
    def _unpack_pointer_vals(name, index):
        """Rebuild the implicit value list from the stored (name, index) slots.

        The filled slots imply the shape: name+index -> mesh element [name,
        index]; name only -> object / curve-ref [name]; index only -> entity
        [index]. Returns None when neither slot is set.
        """
        if name and index >= 0:
            return [name, index]
        if name:
            return [name]
        if index >= 0:
            return [index]
        return None

    def _store_pointers(self):
        """Write each resolved pointer state's identity to its hidden props."""
        for i, state in enumerate(self.get_states()):
            if not state.pointer:
                continue
            data = self._state_data.get(i)
            kind, existing, name, index = "", False, "", -1
            if data and data.get("type"):
                kind = data["type"].__name__
                existing = bool(data.get("is_existing_entity", False))
                name, index = self._pack_pointer_vals(
                    to_list(self.get_state_pointer(index=i, implicit=True))
                )
            # Guarded: duplicate-registration phantoms lack the RNA properties.
            try:
                setattr(self, "ptr%d_kind" % i, kind)
                setattr(self, "ptr%d_existing" % i, existing)
                setattr(self, "ptr%d_name" % i, name)
                setattr(self, "ptr%d_index" % i, index)
            except AttributeError:
                pass

    def _restore_pointers(self):
        """Rebuild pointer state data from the hidden props (redo/execute path).

        Only for the fresh-instance execute/redo/edit path (``_state_snapshot is
        None``). During the interactive modal a snapshot is held and _state_data
        is resolved live every frame; restoring there would re-inject the last
        *picked* identity (kind + is_existing_entity) and clobber a subsequent
        free placement -- e.g. hover a point then move to empty and the endpoint
        stays stuck on the point. The per-state ``data.get("type")`` guard below
        is not enough on its own: pick_element nulls ``type`` when hovering empty,
        which re-opens the door for the stale restore.
        """
        if self._state_snapshot is not None:
            return
        registry = self._pointer_type_registry()
        for i, state in enumerate(self.get_states()):
            if not state.pointer:
                continue
            data = self.get_state_data(i)
            if data.get("type"):
                continue
            kind = getattr(self, "ptr%d_kind" % i, "")
            if not kind:
                continue
            ptype = registry.get(kind)
            if ptype is None:
                continue
            data["type"] = ptype
            data["is_existing_entity"] = bool(getattr(self, "ptr%d_existing" % i, False))
            vals = self._unpack_pointer_vals(
                getattr(self, "ptr%d_name" % i, ""),
                getattr(self, "ptr%d_index" % i, -1),
            )
            if vals is not None:
                self.set_state_pointer(vals, index=i, implicit=True)

    def redo_states(self, context: Context):
        """Recreate non-persistent elements for states up to the current one."""
        # The redo/execute path runs on a fresh instance with empty _state_data;
        # rebuild the picked pointers from the persisted identity first.
        self._restore_pointers()

        for i, state in enumerate(self.get_states()):
            if i > self.state_index:
                # TODO: don't depend on active state; ideally going back is possible
                break
            if state.pointer:
                data = self._state_data.get(i, {})
                is_existing_entity = data.get("is_existing_entity", True)
                props = self.get_property(index=i)
                if props and not is_existing_entity:
                    create = self.get_func(state, "create_element")
                    ret_values = create(
                        context, [getattr(self, p) for p in props], state, data
                    )
                    self.set_state_pointer(to_list(ret_values), index=i, implicit=True)

    def _end(self, context, succeede, skip_undo=False, keep_stateful_running=False):
        context.window.cursor_modal_restore()
        if hasattr(self, "fini"):
            self.fini(context, succeede)
        # One-off tools return to their select tool once done (only on success,
        # so a missed pick keeps the tool for a retry). The target tool differs
        # per operator: object tools -> Blender's select, sketch tools -> the
        # sketch select tool.
        if succeede and self.return_to_tool:
            try:
                bpy.ops.wm.tool_set_by_id(name=self.return_to_tool)
            except Exception:
                pass
        self.on_before_redo_states(context)
        context.workspace.status_text_set(None)

        if not keep_stateful_running:
            global_data.stateful_op_running = False

        # Stop publishing pick types so hover falls back to the idle default.
        global_data.hover_types = None
        global_data.hover_element = None

        if not succeede and not skip_undo:
            if self._state_snapshot is not None:
                self.restore_snapshot(context, self._state_snapshot)
            else:
                bpy.ops.ed.undo_push(message="Cancelled: " + self.bl_label)
                bpy.ops.ed.undo()
        elif succeede:
            # Record what this commit created (modal path; the execute/edit path
            # records in _run_main). Enables idempotent re-apply on re-pick.
            self._record_committed_output(context)

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
        self._end(context, True, keep_stateful_running=True)
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
