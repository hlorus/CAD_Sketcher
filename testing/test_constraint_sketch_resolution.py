"""A constraint must resolve to its *own* sketch, cache or no cache.

``_get_sketch`` used to find the owning Object by scanning ``bpy.data.objects``,
which is O(scene) and runs several times per constraint per solve -- an identical
sketch solved 8x slower in a 1000-object file. It now caches the resolved Object.

Caching a live ``bpy`` reference is the part that needs guarding: references are
invalidated by deletion, undo and file load, and a wrong answer here would silently
solve a constraint against another sketch's geometry. The cache therefore verifies
its answer on every use; these tests cover the cases that verification exists for.
"""

import bpy

from ..model.base_constraint import (
    _data_owner_cache,
    _resolve_data_owner,
    reset_data_owner_cache,
)
from .utils import Sketch2dTestCase


class TestConstraintSketchResolution(Sketch2dTestCase):
    def _constrained_pair(self):
        """A line with a bound distance constraint; returns (p0, p1, constraint)."""
        p0 = self.add_point((0, 0), fixed=True)
        p1 = self.add_point((2, 0))
        self.add_line(p0, p1)
        c = self.sketch.constraints.add_distance(
            init=True, curve_id_1=p0.curve_id, curve_id_2=p1.curve_id
        )
        c.value = 2.0
        self.solve()
        return p0, p1, c

    def test_resolves_to_its_own_object(self):
        _p0, _p1, c = self._constrained_pair()
        reset_data_owner_cache()
        resolved = c._get_sketch()
        self.assertIs(resolved.target_object, self.sketch.target_object)
        # Warm cache must give the same answer.
        self.assertIs(c._get_sketch().target_object, self.sketch.target_object)

    def test_does_not_confuse_two_sketches(self):
        """The cache is keyed per datablock; two sketches must stay separate."""
        _p0, _p1, c1 = self._constrained_pair()
        first_obj = self.sketch.target_object

        second = self.new_sketch()
        self.sketch = second  # add_* helpers target self.sketch
        _q0, _q1, c2 = self._constrained_pair()
        second_obj = second.target_object
        self.assertIsNot(first_obj, second_obj)

        # Resolve repeatedly, interleaved, so a single shared cache slot would show.
        for _ in range(3):
            self.assertIs(c1._get_sketch().target_object, first_obj)
            self.assertIs(c2._get_sketch().target_object, second_obj)

    def test_unrelated_object_deletion_does_not_break_resolution(self):
        _p0, _p1, c = self._constrained_pair()
        filler = bpy.data.objects.new("filler", bpy.data.meshes.new("fillerm"))
        self.scene.collection.objects.link(filler)
        self.assertIs(c._get_sketch().target_object, self.sketch.target_object)

        bpy.data.objects.remove(filler, do_unlink=True)
        self.assertIs(c._get_sketch().target_object, self.sketch.target_object)

    def test_stale_entry_is_rejected_not_trusted(self):
        """A cache entry pointing at the wrong object must lose to a rescan."""
        _p0, _p1, c = self._constrained_pair()
        id_data = self.sketch.target_object.data

        decoy = bpy.data.objects.new("decoy", bpy.data.meshes.new("decoym"))
        self.scene.collection.objects.link(decoy)
        _data_owner_cache[id_data.name] = decoy  # poison it

        self.assertIs(
            _resolve_data_owner(id_data),
            self.sketch.target_object,
            "a poisoned cache entry was trusted instead of revalidated",
        )
        bpy.data.objects.remove(decoy, do_unlink=True)

    def test_removed_cached_object_is_survived(self):
        """A cached reference to a deleted Object must not raise or mislead."""
        _p0, _p1, c = self._constrained_pair()
        id_data = self.sketch.target_object.data

        doomed = bpy.data.objects.new("doomed", bpy.data.meshes.new("doomedm"))
        self.scene.collection.objects.link(doomed)
        _data_owner_cache[id_data.name] = doomed
        bpy.data.objects.remove(doomed, do_unlink=True)

        # Reading .data on the freed reference raises ReferenceError internally;
        # resolution must absorb that and fall back to the scan.
        self.assertIs(_resolve_data_owner(id_data), self.sketch.target_object)

    def test_resolution_survives_undo_redo(self):
        """Undo invalidates bpy references, the classic way such a cache breaks."""
        _p0, _p1, c = self._constrained_pair()
        obj_name = self.sketch.target_object.name
        self.assertIs(c._get_sketch().target_object, self.sketch.target_object)

        try:
            bpy.ops.ed.undo_push(message="perf test")
            bpy.ops.ed.undo()
            bpy.ops.ed.redo()
        except RuntimeError as exc:  # background mode often has no undo stack
            self.skipTest(f"undo unavailable headless: {exc}")

        obj = bpy.data.objects.get(obj_name)
        self.assertIsNotNone(obj, "the sketch object did not survive undo/redo")
        resolved = c._get_sketch()
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.target_object.name, obj_name)
        # And it must still solve.
        self.assertTrue(self.sketch.solve(self.context))

    def test_solving_is_independent_of_scene_size(self):
        """Behavioural check that resolution does not depend on the object count.

        The timing win is machine-dependent, but the *answer* must not change as
        unrelated objects appear, which is what the old scan made fragile.
        """
        _p0, p1, c = self._constrained_pair()
        fillers = []
        for k in range(40):
            ob = bpy.data.objects.new(f"bulk{k}", bpy.data.meshes.new(f"bulkm{k}"))
            self.scene.collection.objects.link(ob)
            fillers.append(ob)
        try:
            self.assertIs(c._get_sketch().target_object, self.sketch.target_object)
            p1.co = (5.0, 0.0)
            self.assertTrue(self.sketch.solve(self.context))
            self.assertAlmostEqual((p1.co - _p0.co).length, 2.0, places=3)
        finally:
            for ob in fillers:
                bpy.data.objects.remove(ob, do_unlink=True)
