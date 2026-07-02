"""Test Blender's native curve (hair_curves) API capabilities.

Run with: flatpak run org.blender.Blender --background --python experiments/test_curve_api.py
"""
import bpy
import time

print("=" * 60)
print(f"Blender {bpy.app.version_string}")
print("=" * 60)

# --- Test 1: Create hair_curves object ---
print("\n--- Test 1: Create hair_curves object ---")
try:
    curve_data = bpy.data.hair_curves.new("TestCurves")
    obj = bpy.data.objects.new("TestCurveObj", curve_data)
    bpy.context.scene.collection.objects.link(obj)
    print(f"Created: {obj.name} with data type: {type(curve_data)}")
    print(f"Data name: {curve_data.name}")
except Exception as e:
    print(f"FAILED: {e}")

# --- Test 2: Add curves with points ---
print("\n--- Test 2: Add curves (2 lines, 2 points each) ---")
try:
    point_counts = [2, 2]  # Two curves, each with 2 points
    curve_data.add_curves(point_counts)
    print(f"Curve count: {len(curve_data.curves)}")
    print(f"Point count: {len(curve_data.points)}")
    for i, curve in enumerate(curve_data.curves):
        print(f"  Curve {i}: {curve.points_length} points, first_point_index={curve.first_point_index}")
except Exception as e:
    print(f"FAILED: {e}")

# --- Test 3: Set point positions ---
print("\n--- Test 3: Set point positions ---")
try:
    # Line 1: (0,0,0) -> (1,0,0)
    curve_data.points[0].position = (0.0, 0.0, 0.0)
    curve_data.points[1].position = (1.0, 0.0, 0.0)
    # Line 2: (1,0,0) -> (1,1,0)
    curve_data.points[2].position = (1.0, 0.0, 0.0)
    curve_data.points[3].position = (1.0, 1.0, 0.0)

    for i, pt in enumerate(curve_data.points):
        print(f"  Point {i}: position={tuple(pt.position)}")
    print("OK: Per-point write works")
except Exception as e:
    print(f"FAILED: {e}")

# --- Test 4: Read positions back ---
print("\n--- Test 4: Read positions back ---")
try:
    positions = [tuple(pt.position) for pt in curve_data.points]
    print(f"  Positions: {positions}")
    assert positions[1][:3] == (1.0, 0.0, 0.0), "Position mismatch!"
    print("OK: Read-back matches")
except Exception as e:
    print(f"FAILED: {e}")

# --- Test 5: foreach_get/set performance ---
print("\n--- Test 5: foreach_get/set bulk access ---")
try:
    import numpy as np

    # Bulk read
    n = len(curve_data.points)
    pos = np.zeros(n * 3, dtype=np.float32)
    curve_data.points.foreach_get("position", pos)
    pos = pos.reshape(-1, 3)
    print(f"  foreach_get positions:\n    {pos}")

    # Bulk write
    pos[0] = [0.5, 0.5, 0.0]  # Move first point
    curve_data.points.foreach_set("position", pos.ravel())
    print(f"  After foreach_set, point 0: {tuple(curve_data.points[0].position)}")
    print("OK: Bulk access works")
except Exception as e:
    print(f"FAILED: {e}")

# --- Test 6: Modify single point (incremental update) ---
print("\n--- Test 6: Incremental single-point update ---")
try:
    curve_data.points[0].position = (0.0, 0.0, 0.0)
    print(f"  Point 0 after update: {tuple(curve_data.points[0].position)}")
    print("OK: Single point update works without rebuild")
except Exception as e:
    print(f"FAILED: {e}")

# --- Test 7: Custom attributes ---
print("\n--- Test 7: Custom attributes ---")
try:
    # Add integer attribute on points
    attr = curve_data.point_attributes.new("entity_index", type='INT', domain='POINT')
    print(f"  Created attribute: {attr.name}, type={attr.data_type}, domain={attr.domain}")

    # Set values
    for i in range(len(curve_data.points)):
        attr.data[i].value = i * 10

    # Read back
    vals = [attr.data[i].value for i in range(len(curve_data.points))]
    print(f"  Values: {vals}")

    # Add curve-level attribute
    attr2 = curve_data.curve_attributes.new("constraint_type", type='INT', domain='CURVE')
    for i in range(len(curve_data.curves)):
        attr2.data[i].value = i + 1
    vals2 = [attr2.data[i].value for i in range(len(curve_data.curves))]
    print(f"  Curve-level values: {vals2}")
    print("OK: Custom attributes work")
except Exception as e:
    print(f"FAILED: {e}")

# --- Test 8: Performance - create many curves and update ---
print("\n--- Test 8: Performance test ---")
try:
    perf_data = bpy.data.hair_curves.new("PerfTest")

    # Create 1000 lines (2 points each)
    n_curves = 1000
    t0 = time.perf_counter()
    perf_data.add_curves([2] * n_curves)
    t_create = time.perf_counter() - t0

    # Bulk set positions
    import numpy as np
    positions = np.random.rand(n_curves * 2, 3).astype(np.float32)
    t0 = time.perf_counter()
    perf_data.points.foreach_set("position", positions.ravel())
    t_set = time.perf_counter() - t0

    # Bulk read
    out = np.zeros(n_curves * 2 * 3, dtype=np.float32)
    t0 = time.perf_counter()
    perf_data.points.foreach_get("position", out)
    t_get = time.perf_counter() - t0

    # Single point update
    t0 = time.perf_counter()
    for i in range(100):
        perf_data.points[i].position = (float(i), 0.0, 0.0)
    t_single = time.perf_counter() - t0

    print(f"  Create {n_curves} curves: {t_create*1000:.2f}ms")
    print(f"  Bulk set {n_curves*2} points: {t_set*1000:.2f}ms")
    print(f"  Bulk read {n_curves*2} points: {t_get*1000:.2f}ms")
    print(f"  100 single-point updates: {t_single*1000:.2f}ms")

    bpy.data.hair_curves.remove(perf_data)
    print("OK: Performance test complete")
except Exception as e:
    print(f"FAILED: {e}")

# --- Test 9: Remove and re-add curves (can we do partial updates?) ---
print("\n--- Test 9: Partial curve removal ---")
try:
    # Check if we can remove specific curves
    if hasattr(curve_data, 'remove_curves'):
        print(f"  remove_curves exists")
        # Check signature
        help_str = str(curve_data.remove_curves.__doc__) if curve_data.remove_curves.__doc__ else "no docs"
        print(f"  Docs: {help_str}")
    else:
        print("  No remove_curves method")
except Exception as e:
    print(f"FAILED: {e}")

# --- Test 10: update_tag ---
print("\n--- Test 10: update_tag ---")
try:
    curve_data.update_tag()
    print("OK: update_tag() works")
except Exception as e:
    print(f"FAILED: {e}")

# Cleanup
bpy.data.objects.remove(obj)
bpy.data.hair_curves.remove(curve_data)

print("\n" + "=" * 60)
print("ALL TESTS COMPLETE")
print("=" * 60)
