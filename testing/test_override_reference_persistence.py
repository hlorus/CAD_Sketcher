"""A library override keeps its sketch, body and workplane links across a reload.

The links are object pointers on the override. Blender drops one on save unless
it is flagged overridable, so after reopening the file an override's links fell
back to the linked originals, and a sketch that should be editable pointed at
read-only data. Each case runs the whole save and reload in fresh processes, as
a user's files do.
"""

import json
import os
import subprocess
import tempfile
from unittest import TestCase

import bpy

CHILD = os.path.join(os.path.dirname(__file__), "override_reload_child.py")
PACKAGE = __package__.rsplit(".", 1)[0]


def _run(step, *args):
    command = [
        bpy.app.binary_path,
        "--background",
        "--factory-startup",
        "--python",
        CHILD,
        "--",
        step,
        PACKAGE,
        *args,
    ]
    done = subprocess.run(command, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr
    for line in done.stdout.splitlines():
        if line.startswith("RESULT "):
            return json.loads(line[len("RESULT ") :])
    return None


class TestOverrideReferencesSurviveReload(TestCase):
    def reloaded(self, *library_args):
        with tempfile.TemporaryDirectory() as tmp:
            library = os.path.join(tmp, "library.blend")
            main = os.path.join(tmp, "main.blend")
            _run("library", library, *library_args)
            _run("override", library, main)
            return _run("report", main)

    def sketch(self, result):
        return next(e for e in result.values() if "body_of" not in e and e["workplane"])

    def body(self, result):
        return next(e for e in result.values() if "body_of" in e)

    def test_the_sketch_keeps_its_workplane(self):
        self.assertEqual(self.sketch(self.reloaded())["workplane"], "override")

    def test_the_sketch_keeps_its_body(self):
        self.assertEqual(self.sketch(self.reloaded())["body"], "override")

    def test_the_body_keeps_its_sketch(self):
        self.assertEqual(self.body(self.reloaded())["body_of"], "override")

    def test_a_library_saved_without_the_flag_still_keeps_workplane_and_body(self):
        result = self.reloaded("old")
        self.assertEqual(self.sketch(result)["workplane"], "override")
        self.assertEqual(self.sketch(result)["body"], "override")

    def test_a_library_saved_without_the_flag_loses_the_body_link(self):
        self.assertEqual(self.body(self.reloaded("old"))["body_of"], "linked")

    def workplane_empty(self, result):
        return next(e for e in result.values() if "wp_source" in e)

    def test_a_face_workplane_keeps_the_object_it_was_drawn_on(self):
        self.assertEqual(self.workplane_empty(self.reloaded())["wp_source"], "override")

    def test_a_sketch_keeps_the_object_it_projects_from(self):
        self.assertEqual(self.sketch(self.reloaded())["project_source"], "override")

    def test_a_library_saved_without_the_flag_loses_the_workplane_source(self):
        result = self.reloaded("old")
        self.assertEqual(self.workplane_empty(result)["wp_source"], "linked")
