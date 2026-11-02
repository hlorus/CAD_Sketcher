"""A sketch that comes from a library can't be entered (#802).

Edits to its Curves data never reach the library file, and an override of that
data refuses the constraint edits a tool makes, so entering it is refused.
"""

import types
from unittest import mock

from ..model.sketch_ref import get_active_sketch
from ..operators import utilities
from ..operators.utilities import activate_sketch
from .live_harness import _LiveContext
from .utils import Sketch2dTestCase


class _Reports:
    """An operator stand-in that records what it was asked to report."""

    def __init__(self):
        self.reports = []

    def report(self, kinds, message):
        self.reports.append((kinds, message))


class TestLinkedSketchEntry(Sketch2dTestCase):
    def _view_context(self):
        context = _LiveContext(self.context)
        context.space_data = types.SimpleNamespace(
            shading=types.SimpleNamespace(show_xray=False)
        )
        return context

    def _assert_refused(self, sketch_obj):
        operator = _Reports()
        context = self._view_context()

        result = activate_sketch(context, sketch_obj, operator)

        self.assertEqual(result, {"CANCELLED"})
        self.assertIsNone(get_active_sketch(self.context))
        self.assertEqual(len(operator.reports), 1)
        kinds, message = operator.reports[0]
        self.assertEqual(kinds, {"WARNING"})
        self.assertIn(sketch_obj.name, message)
        self.assertIn("library.blend", message)

    def setUp(self):
        super().setUp()
        from ..model.sketch_ref import set_active_sketch

        set_active_sketch(self.context, None)
        patcher = mock.patch.object(utilities, "switch_sketch_mode")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_linked_sketch_is_refused(self):
        self._assert_refused(self.library_sketch())

    def test_a_sketch_with_overridden_data_is_refused(self):
        self._assert_refused(self.library_sketch(override_data=True))

    def test_a_local_sketch_with_linked_data_is_refused(self):
        linked = self.library_sketch()
        local = self.sketch.target_object
        local.data = linked.data
        self._assert_refused(local)

    def test_a_local_sketch_is_not_refused(self):
        operator = _Reports()
        context = self._view_context()

        result = activate_sketch(context, self.sketch.target_object, operator)

        self.assertEqual(result, {"FINISHED"})
        self.assertEqual(operator.reports, [])
        self.assertEqual(get_active_sketch(self.context), self.sketch)

    def tearDown(self):
        from ..workspacetools.manager import leave_sketch_mode

        leave_sketch_mode()
        return super().tearDown()
