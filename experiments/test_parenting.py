"""Test correct object parenting in Blender."""
import bpy
from mathutils import Matrix

# Create parent empty
parent = bpy.data.objects.new("Parent", None)
parent.empty_display_type = 'PLAIN_AXES'
bpy.context.scene.collection.objects.link(parent)
parent.location = (1, 2, 3)

# Create child
cd = bpy.data.hair_curves.new("Child")
child = bpy.data.objects.new("ChildObj", cd)
bpy.context.scene.collection.objects.link(child)

# Method 1: direct parent assignment
print("=== Method 1: direct assignment ===")
child.parent = parent
# Need to set matrix_parent_inverse to keep world position
child.matrix_parent_inverse = parent.matrix_world.inverted()
print(f"  child.parent: {child.parent.name}")
print(f"  child.matrix_world: {child.matrix_world.translation[:]}")
print(f"  child.matrix_local: {child.matrix_local.translation[:]}")

# Update depsgraph
bpy.context.view_layer.update()
print(f"  After update:")
print(f"  child.matrix_world: {child.matrix_world.translation[:]}")

# Method 2: match parent transform
print("\n=== Method 2: child at parent position ===")
child2 = bpy.data.objects.new("ChildObj2", None)
bpy.context.scene.collection.objects.link(child2)
child2.parent = parent
child2.matrix_parent_inverse = Matrix.Identity(4)
child2.matrix_local = Matrix.Identity(4)

bpy.context.view_layer.update()
print(f"  child2.matrix_world: {child2.matrix_world.translation[:]}")
print(f"  parent.matrix_world: {parent.matrix_world.translation[:]}")
print(f"  Match: {child2.matrix_world.translation[:] == parent.matrix_world.translation[:]}")

print("\nDONE")
