"""What the depsgraph handler does, and what it skips.

The part and collection passes walk every object in the scene, so they are
gated on the update having touched an object at all. Most updates have not:
solving a sketch, editing a dimension, a modifier input.
"""

import bpy

from ..handlers import on_depsgraph_update
from ..utilities.part import (
    PART_PLANE_KEY,
    create_assembly,
    join_assembly,
    mark_part_root,
    reset_cache,
)
from .utils import BgsTestCase


class _Update:
    """Stands in for a depsgraph update that touched the given id types."""

    updates = ()

    def __init__(self, **updated):
        self._updated = updated

    def id_type_updated(self, id_type: str) -> bool:
        return self._updated.get(id_type, False)


class TestHandlerScope(BgsTestCase):
    def setUp(self):
        super().setUp()
        reset_cache()

    def _part_with_a_loose_member(self):
        """A part whose base plane is not pinned yet, which a pass would pin."""
        root = bpy.data.objects.new("root", None)
        self.scene.collection.objects.link(root)
        mark_part_root(root)

        member = bpy.data.objects.new("root XY", None)
        self.scene.collection.objects.link(member)
        member[PART_PLANE_KEY] = "XY"
        member.parent = root
        member.lock_location = (False, False, False)
        return root, member

    def test_an_update_that_touched_no_object_skips_the_part_passes(self):
        _root, member = self._part_with_a_loose_member()

        on_depsgraph_update(self.scene, _Update(SCENE=True))

        self.assertFalse(
            any(member.lock_location),
            "a pass that walks the scene ran on an update that touched no object",
        )

    def test_an_object_update_runs_them(self):
        _root, member = self._part_with_a_loose_member()

        on_depsgraph_update(self.scene, _Update(OBJECT=True))

        self.assertTrue(all(member.lock_location), "the member was not pinned")

    def test_an_asset_preview_leaves_the_file_alone(self):
        # The preview is rendered in a scene of its own holding a copy of the
        # body, part marker and assembly parent included. Syncing that scene
        # moved the real assembly root into a collection hanging off the
        # temporary one, which crashed Blender once the preview was freed.
        mesh = bpy.data.meshes.new("body")
        mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
        body = bpy.data.objects.new("body", mesh)
        self.scene.collection.objects.link(body)
        mark_part_root(body)
        assembly = create_assembly(self.context)
        join_assembly(assembly, body)
        on_depsgraph_update(self.scene, _Update(OBJECT=True))

        collections = {c.name for c in bpy.data.collections}
        homes = {o.name: {c.name for c in o.users_collection} for o in (body, assembly)}

        body.asset_mark()
        self.addCleanup(body.asset_clear)
        body.asset_generate_preview()

        self.assertEqual({c.name for c in bpy.data.collections}, collections)
        self.assertEqual(
            {o.name: {c.name for c in o.users_collection} for o in (body, assembly)},
            homes,
        )
