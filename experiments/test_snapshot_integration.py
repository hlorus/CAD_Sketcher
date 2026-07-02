"""Test the integrated snapshot system with curve data.

Simulates what happens during an interactive operator:
1. Create snapshot (invoke)
2. Add entity + native curve (main)
3. Restore snapshot (undo during interaction)
4. Add entity + native curve again (main re-run)
5. Verify no duplicate curves
"""
import bpy
import traceback

print("=" * 60)
print("SNAPSHOT INTEGRATION TEST")
print("=" * 60)

sse = bpy.context.scene.sketcher.entities

# Setup
print("\n1. Setup sketch with one line...")
origin = sse.add_point_3d((0, 0, 0), fixed=True)
nm = sse.add_normal_3d((1, 0, 0, 0), fixed=True)
wp = sse.add_workplane(origin, nm, fixed=True)
sketch = sse.add_sketch(wp)

p1 = sse.add_point_2d((0.0, 0.0), sketch)
p2 = sse.add_point_2d((1.0, 0.0), sketch)
line1 = sse.add_line_2d(p1, p2, sketch)

cd = sketch.target_object.data
print(f"   Curves: {len(cd.curves)}, Points: {len(cd.points)}")

# Simulate create_snapshot
print("\n2. Taking snapshot (simulating invoke)...")
from bl_ext.blend.CAD_Sketcher.operators.base_stateful import GenericEntityOp

snapshot = {
    "scene": bpy.context.scene.sketcher,  # we'll use the actual methods
}

# Use the static methods directly
curve_snap = GenericEntityOp._snapshot_curve_data(cd)
scene_snap_dict = {}
from bl_ext.blend.CAD_Sketcher.serialize import scene_to_dict, scene_from_dict
scene_snap = scene_to_dict(bpy.context.scene)
curve_snapshots = {sketch.slvs_index: curve_snap}

print(f"   Snapshot: {curve_snap['n_curves']} curves, {len(curve_snap['positions'])//3} points")

# Simulate main() - add another line
print("\n3. Simulating main() - adding a second line...")
p3 = sse.add_point_2d((1.0, 1.0), sketch)
line2 = sse.add_line_2d(p2, p3, sketch)
print(f"   After main: {len(cd.curves)} curves, {len(cd.points)} points")
for i in range(len(cd.points)):
    print(f"   Point {i}: {tuple(cd.points[i].position)}")

# Simulate restore_snapshot (undo during interaction)
print("\n4. Restoring snapshot (simulating undo)...")
scene_from_dict(bpy.context.scene, scene_snap)
GenericEntityOp._restore_curve_data(cd, curve_snap)
print(f"   After restore: {len(cd.curves)} curves, {len(cd.points)} points")
for i in range(len(cd.points)):
    print(f"   Point {i}: {tuple(cd.points[i].position)}")

# Verify entities also restored
print(f"   Lines2D count: {len(sse.lines2D)}")
print(f"   Points2D count: {len(sse.points2D)}")

# Simulate main() again with different position
print("\n5. Simulating main() again (mouse moved)...")
p3b = sse.add_point_2d((1.0, 2.0), sketch)  # different Y this time
line2b = sse.add_line_2d(p2, p3b, sketch)
print(f"   After second main: {len(cd.curves)} curves, {len(cd.points)} points")
for i in range(len(cd.points)):
    print(f"   Point {i}: {tuple(cd.points[i].position)}")

# Verify: should be exactly 2 curves (original + new), not 3
assert len(cd.curves) == 2, f"Expected 2 curves, got {len(cd.curves)}"
print("   PASS: No duplicate curves!")

# Simulate cancel
print("\n6. Simulating cancel...")
scene_from_dict(bpy.context.scene, scene_snap)
GenericEntityOp._restore_curve_data(cd, curve_snap)
print(f"   After cancel: {len(cd.curves)} curves, {len(cd.points)} points")
assert len(cd.curves) == 1, f"Expected 1 curve after cancel, got {len(cd.curves)}"
print("   PASS: Clean cancel!")

print("\n" + "=" * 60)
print("ALL SNAPSHOT INTEGRATION TESTS PASS")
print("=" * 60)
