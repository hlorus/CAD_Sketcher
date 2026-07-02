"""Test snapshot/restore when sketch starts with no target_object (first segment).

This simulates:
1. Activate sketch (no curves yet)
2. Invoke line operator (snapshot: no target_object)
3. main() adds line (creates target_object + 1 curve)
4. Mouse move → restore snapshot → should clear curves
5. main() again → should have exactly 1 curve, not 2
"""
import bpy

sse = bpy.context.scene.sketcher.entities
from bl_ext.blend.CAD_Sketcher.operators.base_stateful import GenericEntityOp
from bl_ext.blend.CAD_Sketcher.serialize import scene_to_dict, scene_from_dict

print("=" * 60)
print("FIRST SEGMENT SNAPSHOT TEST")
print("=" * 60)

# Setup sketch with NO lines (no target_object)
origin = sse.add_point_3d((0, 0, 0), fixed=True)
nm = sse.add_normal_3d((1, 0, 0, 0), fixed=True)
wp = sse.add_workplane(origin, nm, fixed=True)
sketch = sse.add_sketch(wp)

p1 = sse.add_point_2d((0.0, 0.0), sketch)
p2 = sse.add_point_2d((1.0, 0.0), sketch)

print(f"Before any lines:")
print(f"  target_object: {sketch.target_object}")

# Take snapshot (no target_object yet)
op = GenericEntityOp.__new__(GenericEntityOp)
snapshot = op.create_snapshot(bpy.context)
print(f"\nSnapshot taken (sketch has no target_object)")
print(f"  curves snapshot: {snapshot['curves']}")

# Simulate main() — add a line (this creates target_object)
line1 = sse.add_line_2d(p1, p2, sketch)
print(f"\nAfter main():")
print(f"  target_object: {sketch.target_object}")
print(f"  Curves: {len(sketch.target_object.data.curves)}")

# Simulate restore (mouse moved, undo)
op.restore_snapshot(bpy.context, snapshot)
sketch = bpy.context.scene.sketcher.entities.sketches[0]
print(f"\nAfter restore:")
print(f"  target_object: {sketch.target_object}")
if sketch.target_object:
    print(f"  Curves: {len(sketch.target_object.data.curves)}")
    assert len(sketch.target_object.data.curves) == 0, "Should have 0 curves after restore!"
    print("  PASS: Curves cleared")
else:
    print("  PASS: No target_object (expected)")

# Simulate main() again (new mouse position)
p2b = sse.add_point_2d((2.0, 0.0), sketch)
line1b = sse.add_line_2d(p1, p2b, sketch)
print(f"\nAfter second main():")
print(f"  Curves: {len(sketch.target_object.data.curves)}")
assert len(sketch.target_object.data.curves) == 1, f"Should have 1 curve, got {len(sketch.target_object.data.curves)}"
print("  PASS: Exactly 1 curve")

# Restore again
op.restore_snapshot(bpy.context, snapshot)
sketch = bpy.context.scene.sketcher.entities.sketches[0]
if sketch.target_object:
    print(f"\nAfter second restore: {len(sketch.target_object.data.curves)} curves")
    assert len(sketch.target_object.data.curves) == 0
else:
    print(f"\nAfter second restore: no target_object")
print("  PASS: No accumulation")

print("\n" + "=" * 60)
print("ALL TESTS PASS")
print("=" * 60)
