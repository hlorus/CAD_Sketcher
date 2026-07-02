"""Test that deleting an entity removes its curve segment but leaves others."""
import bpy

sse = bpy.context.scene.sketcher.entities
from bl_ext.blend.CAD_Sketcher.converters import remove_native_curve

# Setup
origin = sse.add_point_3d((0, 0, 0), fixed=True)
nm = sse.add_normal_3d((1, 0, 0, 0), fixed=True)
wp = sse.add_workplane(origin, nm, fixed=True)
sketch = sse.add_sketch(wp)

p1 = sse.add_point_2d((0.0, 0.0), sketch)
p2 = sse.add_point_2d((1.0, 0.0), sketch)
p3 = sse.add_point_2d((1.0, 1.0), sketch)
line1 = sse.add_line_2d(p1, p2, sketch)
line2 = sse.add_line_2d(p2, p3, sketch)

cd = sketch.target_object.data
line1_idx = line1.slvs_index
line2_idx = line2.slvs_index

print(f"line1.slvs_index = {line1_idx}")
print(f"line2.slvs_index = {line2_idx}")

print(f"\n--- Before deletion ---")
print(f"Curves: {len(cd.curves)}")
seg = cd.attributes.get("segment_entity_index")
for i in range(len(seg.data)):
    print(f"  Curve {i}: entity_index={seg.data[i].value}")
for i in range(len(cd.points)):
    print(f"  Point {i}: {tuple(cd.points[i].position)}")

# Remove line1's curve
print(f"\n--- Remove line1 curve ---")
remove_native_curve(sketch, line1_idx)
print(f"Curves: {len(cd.curves)}")
seg = cd.attributes.get("segment_entity_index")
for i in range(len(seg.data)):
    print(f"  Curve {i}: entity_index={seg.data[i].value}")
for i in range(len(cd.points)):
    print(f"  Point {i}: {tuple(cd.points[i].position)}")

# Verify line2's curve survived
assert len(cd.curves) == 1, f"Expected 1 curve, got {len(cd.curves)}"
assert seg.data[0].value == line2_idx, f"Remaining curve should be line2"
print("PASS: line1 removed, line2 preserved")

# Remove line2's curve
print(f"\n--- Remove line2 curve ---")
remove_native_curve(sketch, line2_idx)
print(f"Curves: {len(cd.curves)}")
assert len(cd.curves) == 0, f"Expected 0 curves, got {len(cd.curves)}"
print("PASS: all curves removed")

# Test: removing non-existent entity is a no-op
print(f"\n--- Remove non-existent ---")
remove_native_curve(sketch, 999999)
print(f"Curves: {len(cd.curves)}")
print("PASS: no-op for missing entity")

print("\nALL TESTS PASS")
