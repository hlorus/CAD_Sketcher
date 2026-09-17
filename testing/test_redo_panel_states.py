"""Redo panel only lists states that have something to show."""

from types import SimpleNamespace
from unittest import TestCase

from ..stateful_operator.integration import StatefulOperator


def _op(props, picked=False):
    properties = {
        name: SimpleNamespace(is_hidden=hidden) for name, hidden in props.items()
    }
    return SimpleNamespace(
        get_property=lambda index: list(props),
        rna_type=SimpleNamespace(properties=properties),
        ptr0_existing=picked,
        ptr0_kind="LineRef" if picked else "",
    )


class TestRedoPanelStates(TestCase):
    def test_hidden_properties_are_skipped(self):
        op = _op({"placement": True, "value": False})
        self.assertEqual(StatefulOperator._visible_state_props(op, 0), ["value"])

    def test_state_with_only_hidden_properties_has_nothing_to_show(self):
        op = _op({"placement": True})
        self.assertEqual(StatefulOperator._visible_state_props(op, 0), [])

    def test_picked_pointer_counts_as_content(self):
        state = SimpleNamespace(pointer="entity1")
        self.assertTrue(StatefulOperator._is_picked(_op({}, picked=True), 0, state))
        self.assertFalse(StatefulOperator._is_picked(_op({}), 0, state))
