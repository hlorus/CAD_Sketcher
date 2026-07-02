"""PoC: Solver round-trip with native curve data as source of truth.

Tests the critical loop:
  1. Create native curve geometry (hair_curves) with points
  2. Read positions from curve -> feed to solvespace solver
  3. Add constraints
  4. Solve
  5. Write solved positions back to curve
  6. Verify positions changed correctly

Run with: flatpak run org.blender.Blender --background --python experiments/test_solver_roundtrip.py
"""
import bpy
import time
import numpy as np
import slvs


def setup_workplane():
    """Create a standard XY workplane for the solver."""
    origin = slvs.add_point_3d(1, 0, 0, 0)
    # Quaternion for Z-up normal: identity quat (w=1, x=0, y=0, z=0)
    normal = slvs.add_normal_3d(1, 1.0, 0.0, 0.0, 0.0)
    wp = slvs.add_workplane(1, origin, normal)
    return wp


print("=" * 60)
print("SOLVER ROUND-TRIP TEST")
print("=" * 60)


# ============================================================
# Test 1: Basic solver round-trip
# Create an L-shape: line1 (0,0)->(1,0), line2 (1.1,0)->(1.1,1)
# Add coincident constraint on the shared point
# Solver should move them together
# ============================================================
print("\n--- Test 1: Coincident constraint round-trip ---")

# Step 1: Create curve data with 2 lines
curve_data = bpy.data.hair_curves.new("SolverTest")
obj = bpy.data.objects.new("SolverTestObj", curve_data)
bpy.context.scene.collection.objects.link(obj)

curve_data.add_curves([2, 2])  # 2 curves, 2 points each

# Set initial positions (line1 and line2 with a small gap)
curve_data.points[0].position = (0.0, 0.0, 0.0)  # line1.p1
curve_data.points[1].position = (1.0, 0.0, 0.0)  # line1.p2
curve_data.points[2].position = (1.1, 0.0, 0.0)  # line2.p1 (gap of 0.1)
curve_data.points[3].position = (1.1, 1.0, 0.0)  # line2.p2

print("Initial positions:")
for i in range(4):
    print(f"  Point {i}: {tuple(curve_data.points[i].position)}")

# Step 2: Read positions from curve and feed to solver
slvs.clear_sketch()
wp = setup_workplane()

# Read positions from curve and create solver entities
p0 = slvs.add_point_2d(1, curve_data.points[0].position[0], curve_data.points[0].position[1], wp)
p1 = slvs.add_point_2d(2, curve_data.points[1].position[0], curve_data.points[1].position[1], wp)
p2 = slvs.add_point_2d(2, curve_data.points[2].position[0], curve_data.points[2].position[1], wp)
p3 = slvs.add_point_2d(2, curve_data.points[3].position[0], curve_data.points[3].position[1], wp)

line1 = slvs.add_line_2d(2, p0, p1, wp)
line2 = slvs.add_line_2d(2, p2, p3, wp)

# Fix p0 so the shape is anchored
slvs.dragged(1, p0, wp)

# Step 3: Add coincident constraint (p1 == p2)
slvs.coincident(2, p1, p2, wp)

# Step 4: Solve
t0 = time.perf_counter()
result = slvs.solve_sketch(2, True)
t_solve = time.perf_counter() - t0
print(f"\nSolver result: {result}")
print(f"Solve time: {t_solve*1000:.2f}ms")

# Step 5: Write solved positions back to curve
for i, p in enumerate([p0, p1, p2, p3]):
    x = slvs.get_param_value(p['param'][0])
    y = slvs.get_param_value(p['param'][1])
    curve_data.points[i].position = (x, y, 0.0)

print("\nSolved positions:")
for i in range(4):
    print(f"  Point {i}: {tuple(curve_data.points[i].position)}")

# Verify coincident constraint worked
p1_pos = np.array(curve_data.points[1].position[:2])
p2_pos = np.array(curve_data.points[2].position[:2])
distance = np.linalg.norm(p1_pos - p2_pos)
print(f"\nDistance between p1 and p2: {distance:.6f}")
assert distance < 0.001, f"Coincident constraint failed! Distance: {distance}"
print("PASS: Coincident constraint satisfied!")


# ============================================================
# Test 2: Distance + horizontal constraints
# ============================================================
print("\n\n--- Test 2: Distance + horizontal constraints ---")

slvs.clear_sketch()
wp = setup_workplane()

# Read current positions from curve
pts = []
for i in range(4):
    pos = curve_data.points[i].position
    group = 1 if i == 0 else 2
    pts.append(slvs.add_point_2d(group, float(pos[0]), float(pos[1]), wp))

line1 = slvs.add_line_2d(2, pts[0], pts[1], wp)
line2 = slvs.add_line_2d(2, pts[2], pts[3], wp)

# Fix p0
slvs.dragged(1, pts[0], wp)

# Coincident p1==p2
slvs.coincident(2, pts[1], pts[2], wp)

# Distance constraint on line1: length = 2.0
slvs.distance(2, pts[0], pts[1], 2.0, wp)

# Horizontal constraint on line1
slvs.horizontal(2, line1, wp)

t0 = time.perf_counter()
result = slvs.solve_sketch(2, True)
t_solve = time.perf_counter() - t0
print(f"Solver result: {result}")
print(f"Solve time: {t_solve*1000:.2f}ms")

# Write back
for i, p in enumerate(pts):
    x = slvs.get_param_value(p['param'][0])
    y = slvs.get_param_value(p['param'][1])
    curve_data.points[i].position = (x, y, 0.0)

print("\nSolved positions:")
for i in range(4):
    print(f"  Point {i}: {tuple(curve_data.points[i].position)}")

# Verify distance
p0_pos = np.array(curve_data.points[0].position[:2])
p1_pos = np.array(curve_data.points[1].position[:2])
length = np.linalg.norm(p1_pos - p0_pos)
print(f"\nLine1 length: {length:.6f} (expected: 2.0)")
assert abs(length - 2.0) < 0.001, f"Distance constraint failed! Length: {length}"
print("PASS: Distance constraint satisfied!")


# ============================================================
# Test 3: Performance - iterative solve loop
# Simulate interactive editing: read from curve -> solve -> write back
# ============================================================
print("\n\n--- Test 3: Performance - iterative solve loop ---")

n_iterations = 100
times = []

for iteration in range(n_iterations):
    slvs.clear_sketch()
    wp = setup_workplane()

    t0 = time.perf_counter()

    # Read from curve
    pts = []
    for i in range(4):
        pos = curve_data.points[i].position
        group = 1 if i == 0 else 2
        pts.append(slvs.add_point_2d(group, float(pos[0]), float(pos[1]), wp))

    line1 = slvs.add_line_2d(2, pts[0], pts[1], wp)
    line2 = slvs.add_line_2d(2, pts[2], pts[3], wp)

    slvs.dragged(1, pts[0], wp)
    slvs.coincident(2, pts[1], pts[2], wp)
    slvs.distance(2, pts[0], pts[1], 2.0, wp)

    result = slvs.solve_sketch(2, False)

    # Write back to curve
    for i, p in enumerate(pts):
        x = slvs.get_param_value(p['param'][0])
        y = slvs.get_param_value(p['param'][1])
        curve_data.points[i].position = (x, y, 0.0)

    t_total = time.perf_counter() - t0
    times.append(t_total)

times = np.array(times) * 1000  # ms
print(f"  Iterations: {n_iterations}")
print(f"  Mean:   {times.mean():.3f}ms")
print(f"  Median: {np.median(times):.3f}ms")
print(f"  Min:    {times.min():.3f}ms")
print(f"  Max:    {times.max():.3f}ms")
print(f"  Total:  {times.sum():.1f}ms")
print("PASS: Performance test complete")


# ============================================================
# Test 4: Bulk read/write with foreach_get/set in solve loop
# ============================================================
print("\n\n--- Test 4: Bulk read/write via foreach_get/set ---")

slvs.clear_sketch()
wp = setup_workplane()

# Bulk read
n_points = len(curve_data.points)
pos_flat = np.zeros(n_points * 3, dtype=np.float32)
t0 = time.perf_counter()
curve_data.points.foreach_get("position", pos_flat)
t_read = time.perf_counter() - t0
positions = pos_flat.reshape(-1, 3)
print(f"  Bulk read {n_points} points: {t_read*1000:.4f}ms")

# Create solver entities from bulk data
pts = []
for i in range(n_points):
    group = 1 if i == 0 else 2
    pts.append(slvs.add_point_2d(group, float(positions[i][0]), float(positions[i][1]), wp))

line1 = slvs.add_line_2d(2, pts[0], pts[1], wp)
line2 = slvs.add_line_2d(2, pts[2], pts[3], wp)

slvs.dragged(1, pts[0], wp)
slvs.coincident(2, pts[1], pts[2], wp)
slvs.distance(2, pts[0], pts[1], 2.0, wp)

result = slvs.solve_sketch(2, False)

# Bulk write back
solved_positions = np.zeros((n_points, 3), dtype=np.float32)
for i, p in enumerate(pts):
    solved_positions[i][0] = slvs.get_param_value(p['param'][0])
    solved_positions[i][1] = slvs.get_param_value(p['param'][1])

t0 = time.perf_counter()
curve_data.points.foreach_set("position", solved_positions.ravel())
t_write = time.perf_counter() - t0
print(f"  Bulk write {n_points} points: {t_write*1000:.4f}ms")
print(f"  Solver result: {result}")
print("PASS: Bulk read/write works")


# ============================================================
# Test 5: update_tag and depsgraph
# ============================================================
print("\n\n--- Test 5: update_tag and depsgraph ---")
try:
    curve_data.points[1].position = (2.5, 0.0, 0.0)
    curve_data.update_tag()

    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()

    eval_obj = obj.evaluated_get(dg)
    eval_data = eval_obj.data
    print(f"  Evaluated point 1: {tuple(eval_data.points[1].position)}")
    print("PASS: Depsgraph update works")
except Exception as e:
    print(f"  FAILED: {e}")
    import traceback
    traceback.print_exc()


# Cleanup
bpy.data.objects.remove(obj)
bpy.data.hair_curves.remove(curve_data)

print("\n" + "=" * 60)
print("ALL ROUND-TRIP TESTS COMPLETE")
print("=" * 60)
