"""Alt+D (linked duplicate) of a sketch demotes the copy to a consumable.

A linked duplicate shares the Curves datablock, which made the self-heal churn
(re-minting a shared constraint uid forever, leaking scene keys). The copy is
demoted to a dumb linked consumable of the source instead: own data, no sketch
tag, driven by an Object Info node. A full duplicate (Shift+D) copies the data
and stays an independent sketch.
"""

from ..model.sketch_ref import _TAG, is_sketch_object, stamp_sketch_props
from ..utilities.consumable import (
    _CONSUME_MODIFIER,
    demote_to_consumable,
    plan_linked_duplicates,
)
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
        # The depsgraph handler continually refreshes datablock ownership while a
        # sketch is single-user; simulate that so the owner is current (the test
        # harness renames the object after creation).
        plan_linked_duplicates(self.context.scene)

    def _link_duplicate(self):
        """Mimic Alt+D: copy the object, share its data."""
        a = self.sketch.target_object
        b = a.copy()  # shares a.data
        self.context.scene.collection.objects.link(b)
        stamp_sketch_props(b)  # Alt+D copies the tag; emulate that
        return a, b

    def test_linked_copy_is_planned_for_demotion(self):
        self._dimensioned_sketch()
        a, b = self._link_duplicate()
        self.assertIs(a.data, b.data)

        plan = plan_linked_duplicates(self.context.scene)
        # The owner (a) is kept; the copy (b) is queued for demotion.
        self.assertIn((b.name, a.name), plan)
        self.assertNotIn((a.name, b.name), plan)

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

        demote_to_consumable(b, a)

        # b is no longer a sketch and no longer shares a's data.
        self.assertFalse(is_sketch_object(b))
        self.assertNotIn(_TAG, b)
        self.assertIsNot(a.data, b.data)
        self.assertIn(_CONSUME_MODIFIER, [m.name for m in b.modifiers])

        # The consumable must be movable: its Object Info reads the source in
        # ORIGINAL space so the object's own transform places it (RELATIVE would
        # glue it to the source and make it impossible to move).
        ng = b.modifiers[_CONSUME_MODIFIER].node_group
        info = ng.nodes.get("source_info")
        self.assertIsNotNone(info)
        self.assertEqual(info.transform_space, "ORIGINAL")

        # The churn/leak is gone.
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
        plan = plan_linked_duplicates(self.context.scene)
        self.assertNotIn(c.name, [copy for copy, _ in plan])
        self.assertTrue(is_sketch_object(c))
