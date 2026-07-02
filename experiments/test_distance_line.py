"""Reproduce the exact failing test_distance test case."""
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

c1 = ssc.add_distance(line, None, sketch=sketch, init=True)

print(f"constraint_uid: {c1.constraint_uid}")
print(f"c1.value: {c1.value}")

key = f"slvs:c:{c1.constraint_uid}"
print(f"key in scene: {key in scene}")
if key in scene:
    print(f"scene[key]: {scene[key]}")

# Solve
from bl_ext.blend.CAD_Sketcher.solver import solve_system
ok = solve_system(bpy.context, sketch=sketch)
print(f"\nSolve: {ok}")
print(f"line.length: {line.length}")
print(f"c1.value after solve: {c1.value}")

# Check if value reached solver
print(f"\nExpected: line.length ~= 2.0")
print(f"Got: line.length = {line.length:.4f}")
if abs(line.length - 2.0) < 0.01:
    print("PASS")
else:
    print("FAIL")
