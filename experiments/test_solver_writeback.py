"""Test that solver results are written back to native curves.

Creates entities with constraints, solves, and verifies curve positions update.

Run with: flatpak run org.blender.Blender --background --python experiments/test_solver_writeback.py
"""
import bpy
import numpy as np

print("=" * 60)
print("SOLVER WRITE-BACK TO NATIVE CURVES TEST")
print("=" * 60)

sse = bpy.context.scene.sketcher.entities
ssc = bpy.context.scene.sketcher.constraints
from bl_ext.blend.CAD_Sketcher.solver import solve_system

# Setup sketch
print("\n1. Setup sketch with a line...")
origin = sse.add_point_3d((0, 0, 0), fixed=True)
nm = sse.add_normal_3d((1, 0, 0, 0), fixed=True)
wp = sse.add_workplane(origin, nm, fixed=True)
sketch = sse.add_sketch(wp)

# Line: (0,0) -> (1,0)
p1 = sse.add_point_2d((0.0, 0.0), sketch, fixed=True)
p2 = sse.add_point_2d((1.0, 0.0), sketch)
line = sse.add_line_2d(p1, p2, sketch)

cd = sketch.target_object.data
print(f"   Curves: {len(cd.curves)}, Points: {len(cd.points)}")
print(f"   Initial: p0={tuple(cd.points[0].position)}, p1={tuple(cd.points[1].position)}")


# --- Test 1: Horizontal constraint ---
print("\n--- Test 1: Horizontal constraint (should keep line horizontal) ---")
ssc.add_horizontal(line, sketch=sketch)
# Move p2 off-horizontal to give the solver something to fix
p2.co = (1.0, 0.3)

# Update the curve to reflect the pre-solve position
from bl_ext.blend.CAD_Sketcher.converters import update_native_curves
update_native_curves(bpy.context.scene, sketch=sketch)
print(f"   Before solve (p2 moved): curve p1={tuple(cd.points[1].position)}")

result = solve_system(bpy.context, sketch=sketch)
print(f"   Solver result: {result}")
print(f"   p2.co after solve: {tuple(p2.co)}")
print(f"   Curve p1 after solve: {tuple(cd.points[1].position)}")

# p2 should be back to y=0 (horizontal)
assert abs(p2.co[1]) < 0.001, f"Horizontal not enforced on entity! y={p2.co[1]}"
assert abs(cd.points[1].position[1]) < 0.001, f"Horizontal not reflected in curve! y={cd.points[1].position[1]}"
print("   PASS: Horizontal constraint reflected in curve!")


# --- Test 2: Distance constraint ---
print("\n--- Test 2: Distance constraint (length = 3.0) ---")
ssc.add_distance(p1, p2, sketch=sketch, init=True)
# Find and set the distance value
for c in ssc.all:
    if hasattr(c, 'value') and hasattr(c, 'entity1'):
        try:
            if c.entity1 == p1 and c.entity2 == p2:
                c.value = 3.0
                print(f"   Set distance to 3.0")
                break
        except:
            pass

result = solve_system(bpy.context, sketch=sketch)
print(f"   Solver result: {result}")
print(f"   p2.co after solve: {tuple(p2.co)}")
print(f"   Curve p1 after solve: {tuple(cd.points[1].position)}")

# Check line length in curve
curve_p1 = np.array(cd.points[0].position[:2])
curve_p2 = np.array(cd.points[1].position[:2])
curve_len = np.linalg.norm(curve_p2 - curve_p1)
entity_len = np.linalg.norm(np.array(p2.co) - np.array(p1.co))
print(f"   Line length (entity): {entity_len:.4f}")
print(f"   Line length (curve):  {curve_len:.4f}")
assert abs(curve_len - 3.0) < 0.01, f"Distance not reflected! Length: {curve_len}"
print("   PASS: Distance constraint reflected in curve!")


# --- Test 3: Multiple solves (interactive simulation) ---
print("\n--- Test 3: Multiple solves with changing constraint ---")
for target_len in [1.5, 2.5, 4.0]:
    for c in ssc.all:
        if hasattr(c, 'value') and hasattr(c, 'entity1'):
            try:
                if c.entity1 == p1 and c.entity2 == p2:
                    c.value = target_len
                    break
            except:
                pass
    result = solve_system(bpy.context, sketch=sketch)
    curve_p2 = np.array(cd.points[1].position[:2])
    curve_len = np.linalg.norm(curve_p2 - np.array(cd.points[0].position[:2]))
    print(f"   Target={target_len}, curve length={curve_len:.4f}, match={abs(curve_len - target_len) < 0.01}")
    assert abs(curve_len - target_len) < 0.01

print("   PASS: All iterative solves reflected in curve!")


print("\n" + "=" * 60)
print("ALL SOLVER WRITE-BACK TESTS PASS")
print("=" * 60)
