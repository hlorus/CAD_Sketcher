"""Test that snapshot/restore preserves target_object pointer and curve data.

Simulates the interactive operator cycle where scene_from_dict wipes PointerProperties.
"""
import bpy

sse = bpy.context.scene.sketcher.entities
from bl_ext.blend.CAD_Sketcher.operators.base_stateful import GenericEntityOp
from bl_ext.blend.CAD_Sketcher.serialize import scene_to_dict, scene_from_dict

print("=" * 60)
print("SNAPSHOT POINTER RESTORE TEST")
print("=" * 60)

# Setup
origin = sse.add_point_3d((0, 0, 0), fixed=True)
nm = sse.add_normal_3d((1, 0, 0, 0), fixed=True)
wp = sse.add_workplane(origin, nm, fixed=True)
sketch = sse.add_sketch(wp)

p1 = sse.add_point_2d((0.0, 0.0), sketch)
p2 = sse.add_point_2d((1.0, 0.0), sketch)
line1 = sse.add_line_2d(p1, p2, sketch)

print(f"target_object: {sketch.target_object.name}")
print(f"Curves before snapshot: {len(sketch.target_object.data.curves)}")

# Take snapshot (simulating invoke)
op = GenericEntityOp.__new__(GenericEntityOp)
snapshot = op.create_snapshot(bpy.context)
print(f"\nSnapshot taken")
print(f"  curves key: {list(snapshot['curves'].keys())}")

# Simulate main() — add another line
p3 = sse.add_point_2d((1.0, 1.0), sketch)
line2 = sse.add_line_2d(p2, p3, sketch)
print(f"\nAfter main(): {len(sketch.target_object.data.curves)} curves")

# Simulate restore (undo during interaction)
print(f"\nRestoring snapshot...")
print(f"  target_object before restore: {sketch.target_object}")

op.restore_snapshot(bpy.context, snapshot)

# After restore, check pointer and curves
sketch = bpy.context.scene.sketcher.entities.sketches[0]
print(f"  target_object after restore: {sketch.target_object}")
if sketch.target_object:
    cd = sketch.target_object.data
    print(f"  Curves after restore: {len(cd.curves)}")
    for i in range(len(cd.points)):
        print(f"    Point {i}: {tuple(cd.points[i].position)}")
    assert len(cd.curves) == 1, f"Expected 1 curve, got {len(cd.curves)}"
    print("  PASS: Pointer restored, curves correct")
else:
    print("  FAIL: target_object is None after restore!")

# Simulate main() again
print(f"\nSimulating main() again...")
p3b = sse.add_point_2d((1.0, 2.0), sketch)
line2b = sse.add_line_2d(p2, p3b, sketch)
print(f"  Curves: {len(sketch.target_object.data.curves)}")
assert len(sketch.target_object.data.curves) == 2, "Should have 2 curves"

# Restore again
op.restore_snapshot(bpy.context, snapshot)
sketch = bpy.context.scene.sketcher.entities.sketches[0]
print(f"\nAfter second restore: {len(sketch.target_object.data.curves)} curves")
assert len(sketch.target_object.data.curves) == 1, "Should be back to 1"
print("  PASS: No accumulation")

print("\n" + "=" * 60)
print("ALL TESTS PASS")
print("=" * 60)
