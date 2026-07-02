"""Test constraint value storage in headless mode."""
import bpy

sse = bpy.context.scene.sketcher.entities
ssc = bpy.context.scene.sketcher.constraints
scene = bpy.context.scene

# Setup
sse.ensure_origin_elements(bpy.context)
origin = sse.add_point_3d((0, 0, 0), fixed=True)
nm = sse.add_normal_3d((1, 0, 0, 0), fixed=True)
wp = sse.add_workplane(origin, nm, fixed=True)
sketch = sse.add_sketch(wp)
scene.sketcher.active_sketch_i = sketch.slvs_index

# Create geometry
p1 = sse.add_point_2d((0.0, 0.0), sketch, fixed=True)
p2 = sse.add_point_2d((1.0, 0.0), sketch)

# Add distance constraint
c = ssc.add_distance(p1, p2, sketch=sketch, init=True)

print(f"=== After creation ===")
print(f"constraint_uid: '{c.constraint_uid}'")
print(f"value_store: {c.value_store}")
print(f"c.value: {c.value}")

uid = c.constraint_uid
key = f"slvs:c:{uid}"
print(f"scene key: '{key}'")
print(f"key in scene: {key in scene}")
if key in scene:
    print(f"scene[key]: {scene[key]}")

# Try setting value
print(f"\n=== Setting c.value = 3.0 ===")
c.value = 3.0
print(f"c.value after set: {c.value}")
if key in scene:
    print(f"scene[key] after set: {scene[key]}")
else:
    print(f"scene[key]: NOT FOUND")

# Try setting scene property directly
print(f"\n=== Setting scene[key] = 5.0 ===")
if key in scene:
    scene[key] = 5.0
    print(f"scene[key] after set: {scene[key]}")
    print(f"c.value after scene set: {c.value}")

# Solve
print(f"\n=== Solving ===")
from bl_ext.blend.CAD_Sketcher.solver import solve_system
ok = solve_system(bpy.context, sketch=sketch)
print(f"Solve result: {ok}")
print(f"p2.co after solve: {tuple(p2.co)}")
print(f"line length: {(p2.co - p1.co).length:.4f}")
