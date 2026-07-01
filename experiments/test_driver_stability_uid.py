"""Test driver stability using UIDs (fix for issue #544).

With UID-based driver paths like scene["slvs:c:{uid}"], constraint values
are accessed by their unique identifier rather than collection index.
This ensures drivers remain stable even when other constraints are deleted.
"""
import bpy

scene = bpy.data.scenes.new("DriverTestUID")
bpy.context.window.scene = scene

sse = scene.sketcher.entities
ssc = scene.sketcher.constraints

sse.ensure_origin_elements(bpy.context)
wp = sse.origin_plane_XY
sketch = sse.add_sketch(wp)
scene.sketcher.active_sketch_i = sketch.slvs_index

# Create 3 distance constraints
p0 = sse.add_point_2d((0, 0), sketch, fixed=True)

p1 = sse.add_point_2d((1, 0), sketch)
c1 = ssc.add_distance(p0, p1, sketch=sketch, init=True)

p2 = sse.add_point_2d((0, 2), sketch)
c2 = ssc.add_distance(p0, p2, sketch=sketch, init=True)

p3 = sse.add_point_2d((3, 0), sketch)
c3 = ssc.add_distance(p0, p3, sketch=sketch, init=True)

# Set distinct values
c1.value = 10.0
c2.value = 20.0
c3.value = 30.0

# Get UIDs
uid1 = getattr(c1, "constraint_uid", "")
uid2 = getattr(c2, "constraint_uid", "")
uid3 = getattr(c3, "constraint_uid", "")

print(f"=== Initial state ===")
print(f"c1: uid={uid1}, value={c1.value:.1f}")
print(f"c2: uid={uid2}, value={c2.value:.1f}")
print(f"c3: uid={uid3}, value={c3.value:.1f}")

# Show what a UID-based driver would target
print(f"\n=== UID-based driver paths ===")
for i, c in enumerate(ssc.distance):
    uid = getattr(c, "constraint_uid", "")
    value = scene.get(f"slvs:c:{uid}", 0.0)
    print(f"  scene['slvs:c:{uid}'] = {value:.1f}")

# Delete c2 (middle constraint)
print(f"\n=== Deleting c2 (uid={uid2}) ===")
ssc.remove(c2)

# Check that UID-based paths still resolve correctly
print(f"\n=== UID-based paths after deletion ===")
print(f"A driver targeting scene['slvs:c:{uid1}'] still gets: {scene.get(f'slvs:c:{uid1}', 'NOT FOUND'):.1f}")
print(f"A driver targeting scene['slvs:c:{uid2}'] now gets: {scene.get(f'slvs:c:{uid2}', 'DELETED (expected)')}")
print(f"A driver targeting scene['slvs:c:{uid3}'] still gets: {scene.get(f'slvs:c:{uid3}', 'NOT FOUND'):.1f}")

# Verify stability
val1_after = scene.get(f"slvs:c:{uid1}", None)
val3_after = scene.get(f"slvs:c:{uid3}", None)

print(f"\n=== Stability check ===")
if val1_after is not None and abs(val1_after - 10.0) < 0.01:
    print(f"PASS: UID {uid1} still references value 10.0")
else:
    print(f"FAIL: UID {uid1} value shifted to {val1_after}")

if val3_after is not None and abs(val3_after - 30.0) < 0.01:
    print(f"PASS: UID {uid3} still references value 30.0")
else:
    print(f"FAIL: UID {uid3} value shifted to {val3_after}")

if scene.get(f"slvs:c:{uid2}") is None:
    print(f"PASS: UID {uid2} correctly removed with deleted constraint")
else:
    print(f"FAIL: UID {uid2} still exists unexpectedly")
