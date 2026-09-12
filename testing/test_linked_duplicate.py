"""Alt+D (linked duplicate) of a sketch drops the copy's sketch role.

A linked duplicate shares the Curves datablock, which made the self-heal churn
(re-minting a shared constraint uid forever, leaking scene keys) and showed a
second sketch entry. The copy is untagged and unlocked so it stops being a
sketch, while keeping the shared data + modifiers (still shows the result,
native linked-duplicate behaviour). A full duplicate (Shift+D) copies the data
and stays an independent sketch.
"""

from ..model.sketch_ref import _TAG, is_sketch_object, stamp_sketch_props
from ..utilities.consumable import reconcile_linked_duplicates
from ..utilities.validate import validate_all_sketches
from .utils import Sketch2dTestCase


class TestLinkedDuplicate(Sketch2dTestCase):
    def _dimensioned_sketch(self):
        p0 = self.add_point((0, 0), fixed=True)
        p1 = self.add_point((2, 0))
        line = self.add_line(p0, p1)
        self.sketch.constraints.add_distance(
            init=True, value=2.0, curve_id_1=line.curve_id
        )
        # The handler continually refreshes datablock ownership while a sketch is
        # single-user; run it once so the owner is current (the harness renames
        # the object after creation).
        reconcile_linked_duplicates(self.context.scene)

    def _link_duplicate(self):
        """Mimic Alt+D: copy the object, share its data."""
        a = self.sketch.target_object
        b = a.copy()  # shares a.data
        self.context.scene.collection.objects.link(b)
        stamp_sketch_props(b)  # Alt+D copies the tag; emulate that
        return a, b

    def test_linked_copy_is_demoted(self):
        self._dimensioned_sketch()
        a, b = self._link_duplicate()
        self.assertIs(a.data, b.data)
        self.assertTrue(is_sketch_object(b))

        self.assertTrue(reconcile_linked_duplicates(self.context.scene))

        # The copy is no longer a sketch, is unlocked, and still shares the data
        # (native linked-duplicate: it keeps showing the source's result).
        self.assertFalse(is_sketch_object(b))
        self.assertNotIn(_TAG, b)
        self.assertIs(a.data, b.data)
        self.assertTrue(is_sketch_object(a), "the original stays a sketch")
        self.assertEqual(tuple(b.lock_location), (False, False, False))
        self.assertEqual(tuple(b.lock_rotation), (False, False, False))
        self.assertEqual(tuple(b.lock_scale), (False, False, False))

    def test_demotion_stops_the_churn(self):
        self._dimensioned_sketch()
        a, b = self._link_duplicate()

        def n_keys():
            return len(
                [k for k in self.context.scene.keys() if k.startswith("slvs:c:")]
            )

        # Shared data churns the self-heal and leaks a scene key per pass.
        start = n_keys()
        for _ in range(3):
            validate_all_sketches(self.context.scene)
        self.assertGreater(n_keys(), start, "linked-dup should churn before the fix")

        reconcile_linked_duplicates(self.context.scene)

        before = n_keys()
        for _ in range(5):
            validate_all_sketches(self.context.scene)
        self.assertEqual(n_keys(), before, "demotion must stop the scene-key leak")

    def test_full_duplicate_stays_a_sketch(self):
        self._dimensioned_sketch()
        a = self.sketch.target_object
        c = a.copy()
        c.data = a.data.copy()  # Shift+D: independent data
        self.context.scene.collection.objects.link(c)
        stamp_sketch_props(c)

        # A full copy owns its own data, so it is never demoted.
        reconcile_linked_duplicates(self.context.scene)
        self.assertTrue(is_sketch_object(c))
