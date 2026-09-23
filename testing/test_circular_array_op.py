"""The Circular Array tool.

The counterpart of the linear array: it patterns the target around a picked
axis, so what it has to get right is the axis (an edge, a curve/sketch line or
one of a part's own axes) reaching the node group as a centre and a direction.
"""

import math

import bmesh
import bpy

from ..declarations import WorkSpaceTools
from ..utilities.circular_array_nodes import _input_ids
from .utils import BgsTestCase

MODIFIER = "CAD_Sketcher Circular Array"


class TestCircularArrayTool(BgsTestCase):
    def tearDown(self):
        for ob in list(self.scene.collection.objects):
            me = ob.data
            bpy.data.objects.remove(ob, do_unlink=True)
            if isinstance(me, bpy.types.Mesh) and me.users == 0:
                bpy.data.meshes.remove(me)

    def _box(self, offset=(2.0, 0.0, 0.0), name="box"):
        """A small box sitting ``offset`` from its object origin.

        Geometry centred on the axis would only spin in place, so an offset is
        what makes a ring measurable.
        """
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=0.4)
        bmesh.ops.translate(bm, verts=bm.verts, vec=offset)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        self.scene.collection.objects.link(ob)
        return ob

    def _points(self, ob):
        ob.update_tag()
        dg = self.context.evaluated_depsgraph_get()
        dg.update()
        return [v.co.copy() for v in ob.evaluated_get(dg).to_mesh().vertices]

    def _run(self, ob, **props):
        settings = dict(
            target_name=ob.name,
            axis_origin=(0.0, 0.0, 0.0),
            axis_direction=(0.0, 0.0, 1.0),
        )
        settings.update(props)
        return bpy.ops.view3d.slvs_node_array_circular("EXEC_DEFAULT", **settings)

    def test_the_operator_and_its_tool_are_registered(self):
        self.assertTrue(hasattr(bpy.ops.view3d, "slvs_node_array_circular"))
        self.assertIn(
            WorkSpaceTools.ArrayCircular.value,
            {t.bl_idname for t in bpy.types.WorkSpaceTool.__subclasses__()},
        )

    def test_it_shares_the_linear_arrays_toolbar_button(self):
        # One button with a flyout, so the arrays share one shortcut: the key
        # names the linear tool and starts whichever the toolbar shows.
        from ..keymaps import NODE_TOOL_KEYS
        from ..workspacetools import manager

        entries = {cls.bl_idname: kwargs for cls, kwargs, _group in manager._registry}
        self.assertTrue(entries[WorkSpaceTools.ArrayLinear].get("group"))
        self.assertEqual(
            entries[WorkSpaceTools.ArrayCircular].get("after"),
            {WorkSpaceTools.ArrayLinear.value},
        )
        keyed = {tool for tool, _op, *_keys in NODE_TOOL_KEYS}
        self.assertIn(WorkSpaceTools.ArrayLinear, keyed)
        self.assertNotIn(WorkSpaceTools.ArrayCircular, keyed)

    def test_it_patterns_the_target_around_the_picked_axis(self):
        ob = self._box()

        self.assertEqual(self._run(ob, count=4), {"FINISHED"})

        mod = ob.modifiers.get(MODIFIER)
        self.assertIsNotNone(mod)
        points = self._points(ob)
        self.assertEqual(len(points), 8 * 4)
        # A quarter turn each: one copy per quadrant, all 2 from the Z axis.
        self.assertGreater(max(p.x for p in points), 1.5)
        self.assertLess(min(p.x for p in points), -1.5)
        self.assertGreater(max(p.y for p in points), 1.5)
        self.assertLess(min(p.y for p in points), -1.5)

    def test_the_axis_it_was_given_is_the_one_it_turns_around(self):
        # Around X instead of Z, so the ring rides in the YZ plane.
        ob = self._box(offset=(0.0, 2.0, 0.0))

        self.assertEqual(
            self._run(ob, count=4, axis_direction=(1.0, 0.0, 0.0)), {"FINISHED"}
        )

        points = self._points(ob)
        self.assertLess(max(abs(p.x) for p in points), 0.5, "no travel along X")
        self.assertGreater(max(p.z for p in points), 1.5)
        self.assertLess(min(p.z for p in points), -1.5)

    def test_the_settings_reach_the_modifier(self):
        ob = self._box()

        self.assertEqual(
            self._run(
                ob,
                count=3,
                angle=math.pi / 2,
                use_total_angle=False,
                align_rotation=False,
                merge=True,
                merge_distance=0.01,
            ),
            {"FINISHED"},
        )

        mod = ob.modifiers.get(MODIFIER)
        ids = _input_ids(mod.node_group)
        from ..operators.modifiers import get_modifier_input

        self.assertEqual(get_modifier_input(mod, ids["Count"]), 3)
        self.assertAlmostEqual(
            get_modifier_input(mod, ids["Angle / Total angle"]), math.pi / 2, places=5
        )
        self.assertFalse(get_modifier_input(mod, ids["Use Total Angle"]))
        self.assertFalse(get_modifier_input(mod, ids["Align Rotation"]))
        self.assertTrue(get_modifier_input(mod, ids["Merge by Distance"]))
        self.assertAlmostEqual(
            get_modifier_input(mod, ids["Merge Distance"]), 0.01, places=5
        )
        self.assertEqual(tuple(get_modifier_input(mod, ids["Axis"])), (0.0, 0.0, 1.0))

    def test_without_an_axis_it_adds_nothing(self):
        # Rather than pattern around the node group's default axis, which is not
        # what the user picked.
        ob = self._box()

        self.assertEqual(self._run(ob, axis_direction=(0.0, 0.0, 0.0)), {"CANCELLED"})
        self.assertIsNone(ob.modifiers.get(MODIFIER))

    def test_a_redo_edits_the_same_modifier(self):
        # The redo panel re-runs execute() on a fresh instance with no pointer
        # state: only the persisted axis survives, and it must edit the modifier
        # that is there instead of stacking another one.
        ob = self._box()
        self.assertEqual(self._run(ob, count=4), {"FINISHED"})

        self.assertEqual(self._run(ob, count=6), {"FINISHED"})

        self.assertEqual(len([m for m in ob.modifiers if m.name == MODIFIER]), 1)
        self.assertEqual(len(self._points(ob)), 8 * 6)
