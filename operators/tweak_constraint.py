import bpy
from bpy.props import BoolProperty, IntProperty, StringProperty
from bpy.types import Context, Event, Operator
from bpy.utils import register_classes_factory
from mathutils import Vector
from mathutils.geometry import intersect_line_plane

from ..declarations import Operators
from ..model.sketch_ref import get_active_constraints, get_active_sketch
from ..stateful_operator.utilities.keymap import is_numeric_input, is_unit_input
from ..stateful_operator.utilities.numeric import NumericInput, parse_numeric
from ..stateful_operator.utilities.switch import (
    CANCEL,
    FORWARD,
    SWITCH,
    key_action,
)
from ..utilities.view import get_picking_origin_end

# Confirm / cancel the placement modal.
_CONFIRM = {"RET", "NUMPAD_ENTER"}
_CANCEL = {"ESC", "RIGHTMOUSE"}


class View3D_OT_slvs_tweak_constraint_value_pos(Operator):
    bl_idname = Operators.TweakConstraintValuePos
    bl_label = "Tweak Constraint"
    bl_description = "Tweak constraint's value or display position"
    bl_options = {"UNDO"}

    type: StringProperty(name="Type")
    index: IntProperty(default=-1)
    # Transient per-invocation flag: must not persist to the next call, or a
    # gizmo drag (which invokes without it) would inherit the creation handoff's
    # True and swallow its own release, becoming sticky. SKIP_SAVE resets it.
    handoff: BoolProperty(default=False, options={"SKIP_SAVE"})

    def invoke(self, context: Context, event: Event):
        self.tweak = False
        self._seen_press = False
        self._numeric = NumericInput()
        self.init_mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))
        # Handed off right after creation: place the label under the cursor at
        # once, so there is no frame at the default offset (and no jump) before
        # the first mouse-move.
        if self.handoff:
            self.tweak = True
            self._place(context, self.init_mouse_pos)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context: Context, event: Event):
        delta = (
            self.init_mouse_pos - Vector((event.mouse_region_x, event.mouse_region_y))
        ).length

        if self.handoff:
            # Optional value entry lives in this placement step: typing a number
            # sets the dimension value (with units), independent of the label drag.
            if event.value == "PRESS" and (
                is_numeric_input(event) or is_unit_input(event, self._numeric.current)
            ):
                self._numeric.is_active = True
                self._numeric.evaluate_event(event)
                self._apply_value(context)
                return {"RUNNING_MODAL"}

            # Another tool's shortcut keeps the dimension where it is (like Esc
            # here) and passes the key on to start that tool; undo acts like Esc.
            action = key_action(context, event)
            if action == CANCEL:
                return {"FINISHED"}
            if action == SWITCH:
                return {"FINISHED", "PASS_THROUGH"}
            if action == FORWARD:
                return {"PASS_THROUGH"}

            self.tweak = True
            if event.type in _CANCEL and event.value == "PRESS":
                return {"FINISHED"}
            if event.type in _CONFIRM and event.value == "PRESS":
                return {"FINISHED"}
            if event.type == "LEFTMOUSE":
                if event.value == "PRESS":
                    self._seen_press = True
                # The creation click's leftover release has no matching press in
                # this modal -- ignore just that one so it does not confirm before
                # the user places the label.
                elif event.value == "RELEASE" and not self._seen_press:
                    return {"RUNNING_MODAL"}

        if not self.tweak and delta > 6:
            self.tweak = True

        if event.type == "LEFTMOUSE" and event.value == "RELEASE":
            if not self.tweak:
                self.execute(context)
            return {"FINISHED"}

        if not self.tweak:
            return {"RUNNING_MODAL"}

        self._place(context, (event.mouse_region_x, event.mouse_region_y))
        return {"RUNNING_MODAL"}

    def _constraint(self, context: Context):
        constraints = get_active_constraints(context)
        if not constraints:
            return None
        return constraints.get_from_type_index(self.type, self.index)

    def _place(self, context: Context, coords):
        """Project the cursor onto the constraint's draw plane and offset it there."""
        constr = self._constraint(context)
        if constr is None:
            return

        origin, end_point = get_picking_origin_end(context, coords)
        pos = intersect_line_plane(origin, end_point, *constr.draw_plane())
        if pos is None:
            return

        pos = constr.matrix_basis().inverted() @ pos
        constr.update_draw_offset(pos, context.preferences.system.ui_scale)
        if context.space_data:
            context.space_data.show_gizmo = True
        # When driven by the gizmo, its own modal drag redraws the viewport; when
        # this operator is invoked directly (the handoff right after creating a
        # dimension) nothing else does, so tag a redraw to keep the label live.
        if context.area:
            context.area.tag_redraw()

    def _apply_value(self, context: Context):
        """Set the dimension value from the numeric buffer, then re-solve."""
        constr = self._constraint(context)
        if constr is None:
            return

        prop = constr.rna_type.properties.get("value")
        if prop is None:
            return
        value = parse_numeric(
            prop, self._numeric.current, context.scene.unit_settings.system
        )
        if value is None:
            # Empty or mid-typing/invalid input -- keep the current value.
            return

        # Route through the property setter (matches the creation-time value
        # entry: from_displayed_value + the update callback that re-solves).
        constr.value = value

        sketch = get_active_sketch(context)
        if sketch:
            from ..curve_solver import solve_system
            from ..utilities.curve_data import refresh_curve_geometry

            if solve_system(context, sketch=sketch):
                refresh_curve_geometry(sketch)
        if context.area:
            context.area.tag_redraw()

    def execute(self, context: Context):
        bpy.ops.view3d.slvs_edit_constraint_value(
            "INVOKE_DEFAULT", type=self.type, index=self.index
        )
        return {"FINISHED"}


class View3D_OT_slvs_edit_constraint_value(Operator):
    """Edit a dimension, with its value ready to type into"""

    bl_idname = Operators.EditConstraintValue
    bl_label = "Edit Dimension"
    bl_options = {"UNDO"}

    type: StringProperty(name="Type", options={"SKIP_SAVE"})
    index: IntProperty(name="Index", default=-1, options={"SKIP_SAVE"})

    def _constraint(self, context: Context):
        constraints = get_active_constraints(context)
        if not constraints:
            return None
        return constraints.get_from_type_index(self.type, self.index)

    def invoke(self, context: Context, event: Event):
        constr = self._constraint(context)
        if constr is None or not hasattr(constr, "value"):
            # Nothing to type into, so the generic menu is still the right thing.
            return bpy.ops.view3d.slvs_context_menu(type=self.type, index=self.index)

        # The field draws a scene property, which has to exist before the dialog
        # is laid out; nothing has needed it until the dimension is opened.
        context.scene.sketcher.create_constraint_value_endpoint(constr)
        # A popup rather than a props dialog: every field writes through as it
        # is edited, so an OK button would confirm what already happened and a
        # Cancel would not undo it.
        return context.window_manager.invoke_popup(self, width=180)

    def draw(self, context: Context):
        constr = self._constraint(context)
        if constr is None:
            return

        # The value goes first and opens focused, so the number can be typed
        # straight away. That focus is why a dimension gets a popup of its own:
        # the activation step never runs for a popup_menu. Everything below is
        # the constraint's usual menu, unchanged.
        layout = self.layout
        layout.activate_init = True
        constr.draw_value(layout)
        constr.draw_props(layout, include_value=False)

        layout.separator()
        row = layout.row()
        row.alert = True
        op = row.operator(Operators.DeleteConstraint, text="Delete", icon="X")
        op.type = constr.type
        op.index = constr.index()

    def execute(self, context: Context):
        # Never reached through the popup, which closes on its own; here so the
        # operator can still be called directly.
        return {"FINISHED"}


register, unregister = register_classes_factory(
    (
        View3D_OT_slvs_tweak_constraint_value_pos,
        View3D_OT_slvs_edit_constraint_value,
    )
)
