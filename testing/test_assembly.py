"""Assemblies: a group of parts with a transform of its own.

An assembly is the next level of the same hierarchy parts use, so joining one is
parenting and nothing else. Parts keep their own transform inside it.
"""

import bmesh
import bpy
from mathutils import Matrix, Vector

from ..utilities.part import (
    assembly_root_of,
    create_assembly,
    is_assembly_root,
    join_assembly,
    mark_part_root,
    part_root_of,
    settle_membership,
    world_matrix_of,
)
from .utils import BgsTestCase


class TestAssembly(BgsTestCase):
    def _cube(self, name, location=(0.0, 0.0, 0.0)):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        self.scene.collection.objects.link(ob)
        ob.location = location
        return ob

    def _part(self, name, location=(0.0, 0.0, 0.0)):
        ob = self._cube(name, location)
        mark_part_root(ob)
        return ob

    def test_an_assembly_is_an_empty_that_can_be_moved(self):
        assembly = create_assembly(self.context)
        self.assertTrue(is_assembly_root(assembly))
        self.assertEqual(assembly.type, "EMPTY")
        self.assertEqual(tuple(assembly.lock_location), (False, False, False))
        # Scale stays locked, as for parts: the solver reads rigid frames.
        self.assertEqual(tuple(assembly.lock_scale), (True, True, True))

    def test_a_part_keeps_its_place_when_it_joins(self):
        part = self._part("part", location=(3.0, 0.0, 0.0))
        assembly = create_assembly(self.context)
        assembly.matrix_basis = Matrix.Translation(Vector((0.0, 5.0, 0.0)))

        join_assembly(assembly, part)
        self.assertEqual(world_matrix_of(part).translation, Vector((3.0, 0.0, 0.0)))
        self.assertEqual(assembly_root_of(part), assembly)
        # Still its own part, and still movable within the assembly.
        self.assertEqual(part_root_of(part), part)
        self.assertEqual(tuple(part.lock_location), (False, False, False))

    def test_moving_an_assembly_carries_its_parts(self):
        part = self._part("part", location=(2.0, 0.0, 0.0))
        assembly = create_assembly(self.context)
        join_assembly(assembly, part)

        assembly.matrix_basis = Matrix.Translation(Vector((0.0, 0.0, 4.0)))
        self.assertEqual(world_matrix_of(part).translation, Vector((2.0, 0.0, 4.0)))

    def test_a_cut_across_parts_of_one_assembly_belongs_to_the_assembly(self):
        first = self._part("part_a")
        second = self._part("part_b", location=(4.0, 0.0, 0.0))
        assembly = create_assembly(self.context)
        join_assembly(assembly, first)
        join_assembly(assembly, second)
        cutter = self._cube("cutter", location=(2.0, 0.0, 0.0))

        self.assertEqual(settle_membership(cutter, [first, second]), assembly)
        self.assertEqual(assembly_root_of(cutter), assembly)
        self.assertIsNone(part_root_of(cutter))
        # It is a feature of the assembly, so it does not wander on its own.
        self.assertEqual(tuple(cutter.lock_location), (True, True, True))

    def test_a_cut_across_unrelated_parts_stays_global(self):
        first = self._part("part_a")
        second = self._part("part_b", location=(4.0, 0.0, 0.0))
        assembly = create_assembly(self.context)
        join_assembly(assembly, first)  # only one of them is in it
        cutter = self._cube("cutter", location=(2.0, 0.0, 0.0))

        self.assertIsNone(settle_membership(cutter, [first, second]))
        self.assertIsNone(assembly_root_of(cutter))

    def test_sub_assemblies_nest(self):
        inner = create_assembly(self.context)
        outer = create_assembly(self.context)
        part = self._part("part")
        join_assembly(inner, part)
        join_assembly(outer, inner)

        # The walk stops at the nearest assembly, but the chain reaches the outer.
        self.assertEqual(assembly_root_of(part), inner)
        self.assertEqual(assembly_root_of(inner.parent), outer)

    def test_the_operator_takes_the_selected_parts_in(self):
        part = self._part("part")
        bpy.ops.object.select_all(action="DESELECT")
        part.select_set(True)
        self.context.view_layer.objects.active = part

        bpy.ops.view3d.slvs_add_assembly()
        self.assertIsNotNone(assembly_root_of(part))

    def test_deleting_an_assembly_root_leaves_its_parts_in_place(self):
        from ..utilities.part import reconcile_assemblies

        part = self._part("part", location=(2.0, 0.0, 0.0))
        assembly = create_assembly(self.context)
        join_assembly(assembly, part)
        assembly.matrix_basis = Matrix.Translation(Vector((0.0, 0.0, 6.0)))
        reconcile_assemblies(self.scene)  # remembers the assembly's frame
        placed_at = world_matrix_of(part).translation.copy()

        bpy.data.objects.remove(assembly)
        self.assertTrue(reconcile_assemblies(self.scene))

        self.assertIsNone(assembly_root_of(part))
        self.assertEqual(world_matrix_of(part).translation, placed_at)
        # Still a part in its own right, still movable.
        self.assertEqual(part_root_of(part), part)
        self.assertEqual(tuple(part.lock_location), (False, False, False))

    def test_leaving_an_assembly_is_followed(self):
        from ..utilities.part import reconcile_assemblies

        part = self._part("part")
        assembly = create_assembly(self.context)
        join_assembly(assembly, part)
        reconcile_assemblies(self.scene)

        part.parent = None
        self.assertTrue(reconcile_assemblies(self.scene))
        self.assertIsNone(assembly_root_of(part))
        self.assertFalse(reconcile_assemblies(self.scene))

    def test_parenting_into_an_assembly_is_adopted(self):
        from ..utilities.part import reconcile_assemblies

        part = self._part("part")
        assembly = create_assembly(self.context)
        reconcile_assemblies(self.scene)

        part.parent = assembly  # a plain outliner drag
        reconcile_assemblies(self.scene)
        self.assertEqual(assembly_root_of(part), assembly)

    def test_an_assembly_can_start_empty(self):
        # Nothing selected: the assembly is created anyway, to be filled by
        # dragging parts into it.
        bpy.ops.object.select_all(action="DESELECT")
        self.context.view_layer.objects.active = None

        before = {o.name for o in self.scene.objects}
        bpy.ops.view3d.slvs_add_assembly()
        created = [o for o in self.scene.objects if o.name not in before]

        self.assertEqual(len(created), 1)
        self.assertTrue(is_assembly_root(created[0]))
        self.assertFalse(created[0].children)

    def test_an_assembly_is_not_offered_as_a_workplane(self):
        # It is an Empty, so the picker would offer it; a sketch drawn on it
        # would sit at its frame and yet belong to nothing.
        from ..utilities.workplane import iter_wp_empties

        assembly = create_assembly(self.context)
        self.context.view_layer.update()

        offered = {obj.name for obj, _pick_id in iter_wp_empties(self.context)}
        self.assertNotIn(assembly.name, offered)

    def test_a_placement_is_not_offered_as_a_workplane(self):
        from ..utilities.collections import sync_part_collections
        from ..utilities.part import instance_part
        from ..utilities.workplane import iter_wp_empties

        root = self._part("widget")
        sync_part_collections(self.scene)
        placement = instance_part(self.context, root)
        self.context.view_layer.update()

        offered = {obj.name for obj, _pick_id in iter_wp_empties(self.context)}
        self.assertNotIn(placement.name, offered)
