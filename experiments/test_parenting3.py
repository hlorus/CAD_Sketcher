"""Simulate the exact add_sketch flow and check parenting."""
import bpy

from bl_ext.blend.CAD_Sketcher.converters import (
    ensure_origin_workplane_empties, add_native_point,
)

sse = bpy.context.scene.sketcher.entities
ensure_origin_workplane_empties(bpy.context)
# Also create entity origin elements
sse.ensure_origin_elements(bpy.context)

wp_empty = bpy.context.scene.sketcher.wp_xy

# Simulate main()
origin = sse.add_point_3d(tuple(wp_empty.matrix_world.translation), fixed=True)
quat = wp_empty.matrix_world.to_quaternion()
nm = sse.add_normal_3d(quat, fixed=True)
wp_entity = sse.add_workplane(origin, nm, fixed=True)
sketch = sse.add_sketch(wp_entity)
sketch.workplane_object = wp_empty

p = sse.add_point_2d((0, 0), sketch)
p.fixed = True
add_native_point(sketch, p, (0, 0))

print(f"After main:")
print(f"  target_object: {sketch.target_object}")
print(f"  workplane_object: {sketch.workplane_object}")

# Simulate activate_sketch
bpy.context.scene.sketcher.active_sketch_i = sketch.slvs_index

print(f"\nAfter activate:")
print(f"  target_object: {sketch.target_object}")
print(f"  workplane_object: {sketch.workplane_object}")

# Simulate fini() — parent here
if sketch.target_object and sketch.workplane_object:
    print(f"\n  Setting parent...")
    sketch.target_object.parent = sketch.workplane_object
    print(f"  parent: {sketch.target_object.parent}")

bpy.context.view_layer.update()

print(f"\nFinal state:")
for obj in bpy.context.scene.objects:
    parent_name = obj.parent.name if obj.parent else "None"
    if "Sketch" in obj.name or "WP" in obj.name:
        print(f"  {obj.name} -> parent: {parent_name}")
