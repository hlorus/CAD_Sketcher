"""What the toolbar and the redo panel call things.

A tool only appears while its kind of sketch is active, so a "2D" or "3D" in its
name says nothing the toolbar does not already say. And "Solvespace" is the name
of the solver the add-on drives, not something a user should have to read.
"""

import bpy

from ..workspacetools import manager
from .utils import BgsTestCase

_OPERATOR_PREFIXES = ("view3d.slvs_", "sketcher.slvs_", "view3d.node_")


def _tool_classes():
    return [entry[0] for entry in manager._registry]


def _operator_classes():
    return [
        cls
        for cls in bpy.types.Operator.__subclasses__()
        if getattr(cls, "bl_idname", "").startswith(_OPERATOR_PREFIXES)
    ]


class TestToolNames(BgsTestCase):
    def test_a_tool_name_never_says_2d_or_3d(self):
        for tool_cls in _tool_classes():
            with self.subTest(tool_cls.bl_idname):
                self.assertNotRegex(tool_cls.bl_label, r"\b[23]D\b")

    def test_every_tool_says_what_it_does(self):
        """The toolbar tooltip is the label plus this, so it has to be there."""
        for tool_cls in _tool_classes():
            with self.subTest(tool_cls.bl_idname):
                self.assertTrue(getattr(tool_cls, "bl_description", ""))

    def test_no_name_mentions_the_solver(self):
        names = [cls.bl_label for cls in _tool_classes() + _operator_classes()]
        self.assertTrue(names)
        for name in names:
            with self.subTest(name):
                self.assertNotIn("solvespace", name.lower())
