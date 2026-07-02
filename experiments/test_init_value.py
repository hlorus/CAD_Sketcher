"""Debug _get_init_value for distance constraint."""
import bpy

scene = bpy.data.scenes.new("TestScene")
bpy.context.window.scene = scene
sse = scene.sketcher.entities
ssc = scene.sketcher.constraints

sse.ensure_origin_elements(bpy.context)
wp = sse.origin_plane_XY
sketch = sse.add_sketch(wp)
scene.sketcher.active_sketch_i = sketch.slvs_index

p0 = sse.add_point_2d((0, 0), sketch)
p0.fixed = True
p1 = sse.add_point_2d((-2, 0), sketch)
line = sse.add_line_2d(p0, p1, sketch)

# Manually create constraint step by step
c = ssc.distance.add()
c.entity1_i = line.slvs_index
if sketch is not None:
    c.sketch_i = sketch.slvs_index

print(f"Before _init_constraint:")
print(f"  entity1: {c.entity1}")
print(f"  entity1.is_line(): {c.entity1.is_line() if c.entity1 else 'N/A'}")

# Call _init_constraint
ssc._init_constraint(c)
print(f"\nAfter _init_constraint:")
print(f"  uid: {c.constraint_uid}")
key = f"slvs:c:{c.constraint_uid}"
print(f"  scene[key]: {scene.get(key, 'NOT FOUND')}")

# Call assign_init_props
print(f"\nCalling assign_init_props...")
c.assign_init_props()
print(f"  c.value: {c.value}")
print(f"  scene[key]: {scene.get(key, 'NOT FOUND')}")

# Check _get_init_value directly
print(f"\nDirect _get_init_value:")
print(f"  result: {c._get_init_value(None)}")
