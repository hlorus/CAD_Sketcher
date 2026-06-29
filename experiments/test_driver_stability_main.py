"""Test driver stability on main branch (without UIDs).

On main, constraint values are stored as value_store on the PropertyGroup.
Drivers target the collection index path, which shifts on deletion.
This test demonstrates the bug from issue #544.
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

# Record indices
idx1 = ssc.get_index(c1)
idx2 = ssc.get_index(c2)
idx3 = ssc.get_index(c3)

print(f"=== Initial state ===")
print(f"c1: index={idx1}, value={c1.value:.1f}")
print(f"c2: index={idx2}, value={c2.value:.1f}")
print(f"c3: index={idx3}, value={c3.value:.1f}")

# The driver path would be something like:
# scene.sketcher.constraints.distance[0].value_store
# scene.sketcher.constraints.distance[1].value_store
# scene.sketcher.constraints.distance[2].value_store

# Show what a driver would target
for i, c in enumerate(ssc.distance):
    print(f"  distance[{i}].value_store = {c.value_store:.1f}")

# Delete c2 (middle constraint)
print(f"\n=== Deleting c2 (index={idx2}) ===")
ssc.remove(c2)

# Check what happened to indices
print(f"\nRemaining distance constraints:")
for i, c in enumerate(ssc.distance):
    print(f"  distance[{i}].value_store = {c.value_store:.1f}")

# The problem: a driver targeting distance[2] (c3 with value 30.0)
# now points to nothing (only 2 constraints left).
# A driver targeting distance[1] used to point to c2 (20.0)
# but now points to c3 (30.0) — SHIFTED!

print(f"\n=== Bug demonstration ===")
print(f"A driver targeting distance[1] expected value 20.0 (c2)")
actual = ssc.distance[1].value_store if len(ssc.distance) > 1 else "OUT OF RANGE"
print(f"But now gets: {actual}")
if isinstance(actual, float) and abs(actual - 20.0) > 0.01:
    print(f"BUG CONFIRMED: Value shifted from 20.0 to {actual:.1f}")
elif actual == "OUT OF RANGE":
    print(f"BUG CONFIRMED: Index out of range")
else:
    print(f"No shift detected")

print(f"\nA driver targeting distance[2] expected value 30.0 (c3)")
if len(ssc.distance) > 2:
    print(f"Gets: {ssc.distance[2].value_store:.1f}")
else:
    print(f"BUG CONFIRMED: Index 2 out of range (only {len(ssc.distance)} constraints left)")
