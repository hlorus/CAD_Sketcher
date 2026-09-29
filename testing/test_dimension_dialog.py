"""The dimension edit dialog: value first, and focused for typing.

Blender only runs a popup's activation step for one opened through
``invoke_props_dialog``; ``window_manager.popup_menu`` (the shared context menu)
never does, so a dimension gets its own dialog. These cover the layout side of
that: the value is drawn first, it can be left out of the generic props, and the
request to focus it reaches the field rather than stopping at the layout above.
"""

from .utils import Sketch2dTestCase


class _FakeLayout:
    """Records what a draw call asks for, standing in for a real UILayout.

    A ``UILayout`` can only be had from Blender while a popup or panel is being
    drawn, which a headless test has no way to enter.
    """

    def __init__(self, calls=None, children=None):
        self.calls = [] if calls is None else calls
        self.children = [] if children is None else children
        self.enabled = True
        self.activate_init = False
        self.alert = False
        self.scale_y = 1.0

    def column(self, *args, **kwargs):
        child = _FakeLayout(self.calls, self.children)
        self.children.append(child)
        return child

    row = column
    box = column
    split = column

    def prop(self, _data, name, **kwargs):
        self.calls.append(("prop", name))

    def label(self, **kwargs):
        self.calls.append(("label", kwargs.get("text", "")))

    def separator(self, *args, **kwargs):
        self.calls.append(("separator", ""))

    def operator(self, idname, **kwargs):
        self.calls.append(("operator", idname))
        return type("_FakeOp", (), {"type": "", "index": 0})()

    def props(self):
        return [name for kind, name in self.calls if kind == "prop"]


class TestDimensionDialog(Sketch2dTestCase):
    def _distance(self):
        p1 = self.add_point((0.0, 0.0))
        p2 = self.add_point((0.05, 0.0))
        constraint = self.sketch.constraints.add_distance(
            init=True, curve_id_1=p1.curve_id, curve_id_2=p2.curve_id
        )
        # The field draws a scene property, which the dialog makes sure exists.
        self.context.scene.sketcher.create_constraint_value_endpoint(constraint)
        return constraint

    def _value_key(self, constraint):
        key = self.context.scene.sketcher.get_constraint_value_endpoint(constraint)
        self.assertIsNotNone(key, "the constraint has no value endpoint to draw")
        return f'["{key}"]'

    def test_the_value_can_be_drawn_on_its_own(self):
        constraint = self._distance()
        layout = _FakeLayout()

        self.assertTrue(constraint.draw_value(layout))
        self.assertEqual(layout.props(), [self._value_key(constraint)])

    def test_the_generic_props_can_leave_the_value_out(self):
        constraint = self._distance()
        key = self._value_key(constraint)

        with_value = _FakeLayout()
        constraint.draw_props(with_value)
        self.assertIn(key, with_value.props())
        # Once, so the dialog drawing it first does not repeat it below.
        self.assertEqual(with_value.props().count(key), 1)

        without = _FakeLayout()
        constraint.draw_props(without, include_value=False)
        self.assertNotIn(key, without.props())
        # Everything else is still there, so the dialog is not a reduced menu.
        self.assertIn("visible", without.props())
        self.assertIn("is_reference", without.props())

    def test_the_value_is_what_the_dialog_draws_first(self):
        constraint = self._distance()
        layout = _FakeLayout()

        constraint.draw_value(layout)
        constraint.draw_props(layout, include_value=False)

        self.assertEqual(layout.props()[0], self._value_key(constraint))

    def test_asking_for_focus_reaches_the_field(self):
        """The field sits in a column, and a popup activates one button.

        Set on the dialog's layout alone, the request lands on whatever is drawn
        straight onto it (the name), not on the value nested a column down.
        """
        constraint = self._distance()
        layout = _FakeLayout()
        layout.activate_init = True

        constraint.draw_value(layout)

        self.assertTrue(
            any(child.activate_init for child in layout.children),
            "the column holding the value was not marked for activation",
        )

    def test_focus_is_not_forced_on_the_context_menu(self):
        constraint = self._distance()
        layout = _FakeLayout()  # activate_init left False, as a popup_menu has it

        constraint.draw_value(layout)

        self.assertFalse(any(child.activate_init for child in layout.children))

    def test_a_reference_dimension_greys_its_value(self):
        constraint = self._distance()
        constraint.is_reference = True
        layout = _FakeLayout()

        constraint.draw_value(layout)

        self.assertTrue(any(not child.enabled for child in layout.children))


class TestDimensionDialogEntry(Sketch2dTestCase):
    def test_the_operator_is_registered(self):
        import bpy

        from ..declarations import Operators

        name = Operators.EditConstraintValue.value.split(".")[-1]
        self.assertTrue(hasattr(bpy.ops.view3d, name))
