"""Datablocks that reach us from a depsgraph update are handled by name.

Following a pointer off such an id -- ``id.original`` above all -- crashes
Blender when the update list holds a datablock that is still being built, which
is the state right after objects are created. Every pass that runs from the
handler therefore matches by name, and nothing keeps an Object across passes
without a way to drop it.
"""

import dis
import inspect
import types

from ..utilities import body, face_anchor, projection_anchor, validate
from .utils import BgsTestCase


def reads_attribute(function, name):
    """Whether ``function`` reads ``.name`` off anything, comprehensions too.

    Read from the compiled code rather than the source: a comment mentioning the
    attribute is not a read of it.
    """
    codes = [function.__code__]
    while codes:
        code = codes.pop()
        for instruction in dis.get_instructions(code):
            if instruction.opname in {"LOAD_ATTR", "LOAD_METHOD"}:
                if instruction.argval == name:
                    return True
        codes.extend(c for c in code.co_consts if isinstance(c, types.CodeType))
    return False


# Passes that walk ``depsgraph.updates`` from the handler.
_UPDATE_WALKERS = (
    face_anchor.update_face_workplanes,
    projection_anchor.update_projected_geometry,
    body.rename_after_bodies,
)


class TestDepsgraphIdHandling(BgsTestCase):
    def test_no_pass_follows_an_updates_id(self):
        for pass_fn in _UPDATE_WALKERS:
            self.assertIn("depsgraph.updates", inspect.getsource(pass_fn))
            self.assertFalse(reads_attribute(pass_fn, "original"), pass_fn.__name__)
            self.assertTrue(reads_attribute(pass_fn, "name"), pass_fn.__name__)

    def test_the_handler_path_follows_no_originals(self):
        # Reached on every depsgraph update, so a pointer follow here is the
        # crash; the objects involved come from the scene and are originals.
        for pass_fn in (
            validate._owned_sketches,
            projection_anchor.refresh_projection_for_sketch,
            face_anchor.update_face_workplanes,
        ):
            self.assertFalse(reads_attribute(pass_fn, "original"), pass_fn.__name__)

    def test_caches_holding_datablocks_are_dropped_on_undo(self):
        # Undo frees and reallocates datablocks, so a cached Object from before
        # can point at something else entirely.
        from .. import handlers

        source = inspect.getsource(handlers.on_undo_redo)
        self.assertIn("reset_data_owner_cache", source)
        self.assertIn("reset_workplane_id_map", source)
        self.assertIn("highlight_constraint", source)

    def test_the_workplane_map_can_be_dropped(self):
        from ..utilities.workplane import WP_ID_MAP, reset_workplane_id_map

        WP_ID_MAP["probe"] = object()
        reset_workplane_id_map()
        self.assertEqual(len(WP_ID_MAP), 0)
