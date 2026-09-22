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
