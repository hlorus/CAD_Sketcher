"""Tool shortcuts interrupt a running tool; the shortcut table stays consistent."""

from types import SimpleNamespace
from unittest import TestCase, mock

from mathutils import Vector

from ..stateful_operator.constants import Operators as StatefulOps
from ..stateful_operator.utilities import switch
from .utils import OpHarness, Sketch2dTestCase


def _event(event_type, value="PRESS", **mods):
    base = dict(ctrl=False, shift=False, alt=False, oskey=False, hyper=False)
    base.update(mods)
    return SimpleNamespace(type=event_type, value=value, **base)


def _kmi(idname, event_type, props=None, **mods):
    base = dict(ctrl=False, shift=False, alt=False, oskey=False, hyper=False)
    base.update(mods)
    return SimpleNamespace(
        idname=idname,
        type=event_type,
        value="PRESS",
        active=True,
        any=False,
        key_modifier="NONE",
        properties=SimpleNamespace(**(props or {})),
        **base,
    )


def _invoke(key, tool, operator, fallthrough=False, **mods):
    props = dict(tool_name=tool, operator=operator, fallthrough=fallthrough)
    return _kmi(StatefulOps.InvokeTool, key, props, **mods)


class TestMatches(TestCase):
    def test_modifiers_must_agree(self):
        kmi = _kmi("x.y", "C", shift=True)
        self.assertTrue(switch.matches(kmi, _event("C", shift=True)))
        self.assertFalse(switch.matches(kmi, _event("C")))
        self.assertFalse(switch.matches(kmi, _event("C", shift=True, ctrl=True)))

    def test_any_modifier(self):
        kmi = _kmi("x.y", "C")
        kmi.any = True
        self.assertTrue(switch.matches(kmi, _event("C", alt=True)))

    def test_only_presses(self):
        self.assertFalse(switch.matches(_kmi("x.y", "C"), _event("C", "RELEASE")))

    def test_inactive_item(self):
        kmi = _kmi("x.y", "C")
        kmi.active = False
        self.assertFalse(switch.matches(kmi, _event("C")))


class TestClassify(TestCase):
    def setUp(self):
        patcher = mock.patch.object(
            switch, "tool_available", lambda context, name: name == "tool.here"
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(switch.clear_switch_operators)

    def test_available_tool_switches(self):
        kmi = _invoke("C", "tool.here", "op.circle")
        self.assertEqual(switch.classify(None, kmi, "op.line"), switch.SWITCH)

    def test_own_shortcut_does_not_restart(self):
        kmi = _invoke("L", "tool.here", "op.line")
        self.assertEqual(switch.classify(None, kmi, "op.line"), switch.BLOCK)

    def test_unavailable_tool(self):
        local = _invoke("S", "tool.gone", "op.sketch")
        glob = _invoke("S", "tool.gone", "op.sketch", fallthrough=True)
        self.assertEqual(switch.classify(None, local, "op.line"), switch.BLOCK)
        self.assertEqual(switch.classify(None, glob, "op.line"), switch.PASS)

    def test_unregistered_operator_blocks(self):
        kmi = _kmi("wm.something", "G")
        self.assertEqual(switch.classify(None, kmi, "op.line"), switch.BLOCK)

    def test_registered_operator_uses_predicate(self):
        switch.register_switch_operator("op.leave", lambda c, k: k.properties.on)
        on = _kmi("op.leave", "A", {"on": True})
        off = _kmi("op.leave", "A", {"on": False})
        self.assertEqual(switch.classify(None, on, "op.line"), switch.SWITCH)
        self.assertEqual(switch.classify(None, off, "op.line"), switch.PASS)
        self.assertEqual(switch.classify(None, on, "op.leave"), switch.BLOCK)

    def test_register_by_enum_member(self):
        from ..declarations import Operators

        switch.register_switch_operator(Operators.AddHorizontal, lambda c, k: True)
        kmi = _kmi(Operators.AddHorizontal.value, "H", shift=True)
        self.assertEqual(switch.classify(None, kmi, "op.line"), switch.SWITCH)

    def _decide(self, items, event, exclude="op.line"):
        return switch.first_verdict(
            items, event, lambda kmi: switch.classify(None, kmi, exclude)
        )

    def test_first_deciding_item_wins(self):
        event = _event("B", ctrl=True, shift=True)
        bevel = _invoke("B", "tool.here", "op.bevel", True, ctrl=True, shift=True)
        array = _invoke("B", "tool.gone", "op.array", True, ctrl=True, shift=True)
        chain = _kmi("op.select_chain", "B", ctrl=True, shift=True)
        self.assertTrue(self._decide([array, bevel], event))
        self.assertFalse(self._decide([array, chain, bevel], event))

    def test_unbound_key_does_not_switch(self):
        items = [_invoke("C", "tool.here", "op.circle")]
        self.assertFalse(self._decide(items, _event("Q")))


class TestIsSwitchEvent(TestCase):
    def test_ignores_non_letter_keys(self):
        with mock.patch.object(switch, "_active_keymaps") as keymaps:
            for event_type in ("LEFTMOUSE", "ONE", "ESC", "WHEELUPMOUSE"):
                self.assertFalse(switch.is_switch_event(None, _event(event_type)))
            keymaps.assert_not_called()


class TestShortcutTable(TestCase):
    def setUp(self):
        from .. import keymaps

        self.keymaps = keymaps

    def test_local_keys_unique_per_tool_set(self):
        km = self.keymaps
        for table in (km.SKETCH_TOOL_KEYS, km.SKETCH_3D_TOOL_KEYS, km.NODE_TOOL_KEYS):
            keys = [row[2] for row in table]
            self.assertEqual(len(keys), len(set(keys)), keys)

    def test_global_keys(self):
        keys = [row[3] for row in self.keymaps.NODE_TOOL_KEYS]
        self.assertEqual(len(keys), len(set(keys)), keys)
        # Ctrl+Shift+S saves as, Ctrl+Shift+O opens recent files.
        self.assertFalse(set(keys) & {"S", "O"})

    def test_tool_access_built_from_table(self):
        km = self.keymaps
        invokes = [item for item in km.tool_access if item[0] == StatefulOps.InvokeTool]
        keys = [item[1]["type"] for item in invokes]
        self.assertEqual(keys, [row[2] for row in km.SKETCH_TOOL_KEYS])


class TestRunningToolHandsOver(Sketch2dTestCase):
    def _op(self):
        from ..operators.add_line_2d import View3D_OT_slvs_add_line2d
        from ..stateful_operator.utilities.numeric import NumericInput

        op = OpHarness(View3D_OT_slvs_add_line2d, self.sketch, self.context).op
        op.edit_state = -1
        op.wait_for_input = True
        op._numeric = NumericInput()
        op._last_coords = Vector((0, 0))
        op._axis_lock = None
        self.ended = []
        op._end = lambda context, succeede, **kw: self.ended.append(succeede)
        op.is_switch_event = lambda context, event: event.type == "C"
        op.evaluate_state = lambda *args: {"RUNNING_MODAL"}
        op.set_status_text = lambda context: None
        return op

    def _key(self, event_type):
        event = _event(event_type)
        event.mouse_region_x = event.mouse_region_y = 0
        return event

    def test_switch_key_cancels_and_passes_on(self):
        op = self._op()
        self.assertEqual(
            op.modal(self.context, self._key("C")), {"CANCELLED", "PASS_THROUGH"}
        )
        self.assertEqual(self.ended, [False])

    def test_other_keys_keep_running(self):
        op = self._op()
        self.assertEqual(op.modal(self.context, self._key("Q")), {"RUNNING_MODAL"})
        self.assertEqual(self.ended, [])

    def test_unit_letter_while_typing_a_number(self):
        import bpy

        op = self._op()
        op._numeric.is_active = True
        op._numeric.init_substate(bpy.types.Object.bl_rna.properties["location"])
        op._numeric.current = "5"
        self.assertEqual(op.modal(self.context, self._key("C")), {"RUNNING_MODAL"})
        self.assertEqual(self.ended, [])
        self.assertEqual(op._numeric.current, "5c")
