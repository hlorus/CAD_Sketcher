"""Test parenting in the actual add_sketch context."""
import bpy

from bl_ext.blend.CAD_Sketcher.converters import ensure_origin_workplane_empties, add_native_point

sse = bpy.context.scene.sketcher.entities
ensure_origin_workplane_empties(bpy.context)

wp_empty = bpy.context.scene.sketcher.wp_xy
print(f"wp_empty: {wp_empty}")

# Create sketch
origin = sse.add_point_3d((0, 0, 0), fixed=True)
nm = sse.add_normal_3d((1, 0, 0, 0), fixed=True)
wp = sse.add_workplane(origin, nm, fixed=True)
sketch = sse.add_sketch(wp)
sketch.workplane_object = wp_empty

# Create point to trigger ensure_sketch_curve_object
p = sse.add_point_2d((0, 0), sketch)
add_native_point(sketch, p, (0, 0))

print(f"target_object: {sketch.target_object}")
print(f"target_object.parent before: {sketch.target_object.parent}")

# Try parenting
sketch.target_object.parent = wp_empty
print(f"target_object.parent after: {sketch.target_object.parent}")

bpy.context.view_layer.update()
print(f"target_object.parent after update: {sketch.target_object.parent}")

# Check outliner hierarchy
for obj in bpy.context.scene.objects:
    parent_name = obj.parent.name if obj.parent else "None"
    print(f"  {obj.name} -> parent: {parent_name}")
