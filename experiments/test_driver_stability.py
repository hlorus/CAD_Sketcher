"""Test that constraint driver endpoints remain stable after deletion.

Reproduces issue #544: drivers associated to dimensional constraints
shift when constraints are created/deleted because they target the
collection index which changes.

The fix (PR #557) uses stable UIDs as scene custom property keys,
so drivers target scene["slvs:c:<uid>"] which doesn't shift.
"""
import bpy

scene = bpy.data.scenes.new("DriverTest")
bpy.context.window.scene = scene

sse = scene.sketcher.entities
ssc = scene.sketcher.constraints

sse.ensure_origin_elements(bpy.context)
wp = sse.origin_plane_XY
sketch = sse.add_sketch(wp)
scene.sketcher.active_sketch_i = sketch.slvs_index

# Create 3 lines with distance constraints
p0 = sse.add_point_2d((0, 0), sketch, fixed=True)

p1 = sse.add_point_2d((1, 0), sketch)
line1 = sse.add_line_2d(p0, p1, sketch)
c1 = ssc.add_distance(p0, p1, sketch=sketch, init=True)

p2 = sse.add_point_2d((0, 2), sketch)
line2 = sse.add_line_2d(p0, p2, sketch)
c2 = ssc.add_distance(p0, p2, sketch=sketch, init=True)

p3 = sse.add_point_2d((3, 0), sketch)
line3 = sse.add_line_2d(p0, p3, sketch)
c3 = ssc.add_distance(p0, p3, sketch=sketch, init=True)

# Record UIDs and values
uid1 = c1.constraint_uid
uid2 = c2.constraint_uid
uid3 = c3.constraint_uid

print(f"=== Initial state ===")
print(f"c1: uid={uid1}, value={c1.value:.1f}")
print(f"c2: uid={uid2}, value={c2.value:.1f}")
print(f"c3: uid={uid3}, value={c3.value:.1f}")

key1 = f"slvs:c:{uid1}"
key2 = f"slvs:c:{uid2}"
key3 = f"slvs:c:{uid3}"

# Verify scene properties exist
assert key1 in scene, f"Key {key1} not in scene"
assert key2 in scene, f"Key {key2} not in scene"
assert key3 in scene, f"Key {key3} not in scene"

# Set distinct values via scene properties (simulating drivers)
scene[key1] = 10.0
scene[key2] = 20.0
scene[key3] = 30.0

print(f"\n=== After setting via scene props ===")
print(f"c1.value={c1.value:.1f} (expect 10.0)")
print(f"c2.value={c2.value:.1f} (expect 20.0)")
print(f"c3.value={c3.value:.1f} (expect 30.0)")

assert abs(c1.value - 10.0) < 0.01, f"c1.value={c1.value}, expected 10.0"
assert abs(c2.value - 20.0) < 0.01, f"c2.value={c2.value}, expected 20.0"
assert abs(c3.value - 30.0) < 0.01, f"c3.value={c3.value}, expected 30.0"

# Delete c2 (middle constraint) — this is what causes the bug in #544
print(f"\n=== Deleting c2 (uid={uid2}) ===")
ssc.remove(c2)

# Verify c2's scene property was cleaned up
assert key2 not in scene, f"Key {key2} should be removed after deletion"

# Verify c1 and c3 still have correct values (NOT shifted)
print(f"c1 value via scene[{key1}]: {scene.get(key1, 'MISSING')}")
print(f"c3 value via scene[{key3}]: {scene.get(key3, 'MISSING')}")

assert key1 in scene, f"c1's key should still exist"
assert key3 in scene, f"c3's key should still exist"
assert abs(float(scene[key1]) - 10.0) < 0.01, f"c1 value shifted! Got {scene[key1]}"
assert abs(float(scene[key3]) - 30.0) < 0.01, f"c3 value shifted! Got {scene[key3]}"

# Verify constraint objects still read correct values
# After deletion, c3 may have shifted index but its UID-based value should be stable
remaining = list(ssc.dimensional)
print(f"\nRemaining dimensional constraints: {len(remaining)}")
for c in remaining:
    uid = c.constraint_uid
    key = f"slvs:c:{uid}"
    print(f"  uid={uid}, value={c.value:.1f}, scene[key]={scene.get(key, 'MISSING')}")

print("\nPASS: Driver endpoints remain stable after constraint deletion")
