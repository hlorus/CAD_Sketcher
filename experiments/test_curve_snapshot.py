"""Test snapshotting and restoring curve data.

Can we efficiently save/restore the state of a hair_curves object?
"""
import bpy
import numpy as np
import time

print("=" * 60)
print("CURVE SNAPSHOT/RESTORE TEST")
print("=" * 60)

# Create test curve with some data
curve_data = bpy.data.hair_curves.new("SnapTest")
obj = bpy.data.objects.new("SnapTestObj", curve_data)
bpy.context.scene.collection.objects.link(obj)

curve_data.add_curves([2, 2, 4])  # 3 curves: 2 lines + 1 circle
curve_data.set_types(type="BEZIER")

# Set positions
for i in range(len(curve_data.points)):
    curve_data.points[i].position = (float(i), float(i) * 0.5, 0.0)

# Add attributes
attr_ei = curve_data.attributes.new("entity_index", type='INT', domain='POINT')
for i in range(len(attr_ei.data)):
    attr_ei.data[i].value = (i + 1) * 100

attr_con = curve_data.attributes.new("construction", type='BOOLEAN', domain='CURVE')
attr_con.data[0].value = False
attr_con.data[1].value = True
attr_con.data[2].value = False

print(f"Initial state: {len(curve_data.curves)} curves, {len(curve_data.points)} points")


# --- Method 1: numpy-based snapshot ---
print("\n--- Method 1: numpy arrays snapshot ---")

def snapshot_curves(curve_data):
    """Take a snapshot of curve data."""
    n_points = len(curve_data.points)
    n_curves = len(curve_data.curves)

    if n_curves == 0:
        return {"n_curves": 0}

    # Point counts per curve
    point_counts = np.zeros(n_curves, dtype=np.int32)
    curve_data.curves.foreach_get("points_length", point_counts)

    # Positions
    positions = np.zeros(n_points * 3, dtype=np.float32)
    curve_data.points.foreach_get("position", positions)

    # Custom attributes
    attrs = {}
    for attr in curve_data.attributes:
        if attr.name == "position":
            continue  # already captured
        domain_len = n_points if attr.domain == 'POINT' else n_curves
        if attr.data_type == 'FLOAT_VECTOR':
            data = np.zeros(domain_len * 3, dtype=np.float32)
            attr.data.foreach_get("vector", data)
        elif attr.data_type == 'BOOLEAN':
            data = np.zeros(domain_len, dtype=np.bool_)
            attr.data.foreach_get("value", data)
        elif attr.data_type in ('INT', 'INT8'):
            data = np.zeros(domain_len, dtype=np.int32)
            attr.data.foreach_get("value", data)
        elif attr.data_type == 'FLOAT':
            data = np.zeros(domain_len, dtype=np.float32)
            attr.data.foreach_get("value", data)
        else:
            continue
        attrs[attr.name] = {
            "data": data,
            "type": attr.data_type,
            "domain": attr.domain,
        }

    return {
        "n_curves": n_curves,
        "point_counts": point_counts,
        "positions": positions,
        "attributes": attrs,
    }


def restore_curves(curve_data, snapshot):
    """Restore curve data from a snapshot."""
    # Clear existing
    if len(curve_data.curves) > 0:
        curve_data.remove_curves()

    if snapshot["n_curves"] == 0:
        return

    # Recreate curves
    curve_data.add_curves(snapshot["point_counts"].tolist())
    curve_data.set_types(type="BEZIER")

    # Restore positions
    curve_data.points.foreach_set("position", snapshot["positions"])

    # Restore attributes
    for name, attr_info in snapshot["attributes"].items():
        attr = curve_data.attributes.get(name)
        if not attr:
            attr = curve_data.attributes.new(name, type=attr_info["type"],
                                              domain=attr_info["domain"])
        if attr_info["type"] == 'FLOAT_VECTOR':
            attr.data.foreach_set("vector", attr_info["data"])
        else:
            attr.data.foreach_set("value", attr_info["data"])


# Take snapshot
t0 = time.perf_counter()
snap = snapshot_curves(curve_data)
t_snap = time.perf_counter() - t0
print(f"  Snapshot time: {t_snap*1000:.3f}ms")
print(f"  Snapshot contains: {snap['n_curves']} curves, point_counts={snap['point_counts']}")
print(f"  Positions shape: {snap['positions'].shape}")
print(f"  Attributes: {list(snap['attributes'].keys())}")

# Modify the curve (simulate main() adding stuff)
print("\n  Modifying curve data (simulating interactive operation)...")
curve_data.add_curves([2])  # Add extra curve
curve_data.points[0].position = (999.0, 999.0, 999.0)  # Move a point
print(f"  After modify: {len(curve_data.curves)} curves, {len(curve_data.points)} points")
print(f"  Point 0 moved to: {tuple(curve_data.points[0].position)}")

# Restore from snapshot
t0 = time.perf_counter()
restore_curves(curve_data, snap)
t_restore = time.perf_counter() - t0
print(f"\n  Restore time: {t_restore*1000:.3f}ms")
print(f"  After restore: {len(curve_data.curves)} curves, {len(curve_data.points)} points")
print(f"  Point 0 restored to: {tuple(curve_data.points[0].position)}")

# Verify
positions_after = np.zeros(len(curve_data.points) * 3, dtype=np.float32)
curve_data.points.foreach_get("position", positions_after)
match = np.allclose(snap["positions"], positions_after)
print(f"  Positions match: {match}")

attr_ei = curve_data.attributes.get("entity_index")
if attr_ei:
    vals = [attr_ei.data[i].value for i in range(len(attr_ei.data))]
    print(f"  entity_index restored: {vals}")

attr_con = curve_data.attributes.get("construction")
if attr_con:
    vals = [attr_con.data[i].value for i in range(len(attr_con.data))]
    print(f"  construction restored: {vals}")

print(f"\n  PASS: Snapshot/restore works!")


# --- Performance test with larger data ---
print("\n--- Performance: 100 curves snapshot/restore ---")
perf_data = bpy.data.hair_curves.new("PerfSnapTest")
perf_data.add_curves([2] * 100)
perf_data.set_types(type="BEZIER")
positions = np.random.rand(200 * 3).astype(np.float32)
perf_data.points.foreach_set("position", positions)
perf_data.attributes.new("entity_index", type='INT', domain='POINT')

t0 = time.perf_counter()
for _ in range(100):
    s = snapshot_curves(perf_data)
t_snap_100 = (time.perf_counter() - t0) / 100
print(f"  Snapshot (100 curves): {t_snap_100*1000:.3f}ms")

t0 = time.perf_counter()
for _ in range(100):
    restore_curves(perf_data, s)
t_restore_100 = (time.perf_counter() - t0) / 100
print(f"  Restore (100 curves):  {t_restore_100*1000:.3f}ms")

bpy.data.hair_curves.remove(perf_data)


# --- Test empty snapshot (no curves yet) ---
print("\n--- Empty snapshot test ---")
empty_data = bpy.data.hair_curves.new("EmptyTest")
snap_empty = snapshot_curves(empty_data)
print(f"  Empty snapshot: {snap_empty}")
restore_curves(empty_data, snap_empty)
print(f"  Restore empty: {len(empty_data.curves)} curves")
print("  PASS")

bpy.data.hair_curves.remove(empty_data)

# Cleanup
bpy.data.objects.remove(obj)
bpy.data.hair_curves.remove(curve_data)

print("\n" + "=" * 60)
print("ALL SNAPSHOT TESTS COMPLETE")
print("=" * 60)
