"""Test the curve-based solver."""
import bpy
import numpy as np
from mathutils import Vector

sse = bpy.context.scene.sketcher.entities
ssc = bpy.context.scene.sketcher.constraints
from bl_ext.blend.CAD_Sketcher.converters import (
    add_native_point, add_native_line, SketchCurveType,
)
from bl_ext.blend.CAD_Sketcher.curve_solver import solve_sketch_from_curves

# Setup
origin = sse.add_point_3d((0, 0, 0), fixed=True)
nm3d = sse.add_normal_3d((1, 0, 0, 0), fixed=True)
wp = sse.add_workplane(origin, nm3d, fixed=True)
sketch = sse.add_sketch(wp)

# Activate sketch
bpy.context.scene.sketcher.active_sketch_i = sketch.slvs_index

# Create two lines with a gap (p2 != p3)
p1 = sse.add_point_2d((0.0, 0.0), sketch, fixed=True)
cid_p1 = add_native_point(sketch, p1, p1.co)

p2 = sse.add_point_2d((1.0, 0.0), sketch)
cid_p2 = add_native_point(sketch, p2, p2.co)

p3 = sse.add_point_2d((1.5, 0.0), sketch)
cid_p3 = add_native_point(sketch, p3, p3.co)

p4 = sse.add_point_2d((1.5, 1.0), sketch)
cid_p4 = add_native_point(sketch, p4, p4.co)

line1 = sse.add_line_2d(p1, p2, sketch)
cid_line1 = add_native_line(sketch, line1, p1.co, p2.co,
                            start_point_id=cid_p1, end_point_id=cid_p2)

line2 = sse.add_line_2d(p3, p4, sketch)
cid_line2 = add_native_line(sketch, line2, p3.co, p4.co,
                            start_point_id=cid_p3, end_point_id=cid_p4)

cd = sketch.target_object.data
print("=== Before solve ===")
print(f"p2 curve pos: {tuple(cd.points[cd.curves[1].points[0].index].position)}")
print(f"p3 curve pos: {tuple(cd.points[cd.curves[2].points[0].index].position)}")

# Add horizontal constraint on line1
ssc.add_horizontal(line1, sketch=sketch)

# Move p2 off-horizontal to test
p2.co = (1.0, 0.3)
# Update curve to match
from bl_ext.blend.CAD_Sketcher.converters import get_curve_index
idx = get_curve_index(sketch, cid_p2)
cd.points[cd.curves[idx].points[0].index].position = (1.0, 0.3, 0.0)

print(f"\np2 moved to (1.0, 0.3)")

# Solve using curve solver
print("\n=== Solving with CurveSolver ===")
ok = solve_sketch_from_curves(bpy.context, sketch)
print(f"Result: {'OK' if ok else 'FAILED'}")

# Check curve positions
print(f"\np2 curve pos after solve: {tuple(cd.points[cd.curves[1].points[0].index].position)}")
p2_y = cd.points[cd.curves[1].points[0].index].position[1]
print(f"p2.y = {p2_y:.4f} (should be ~0 from horizontal constraint)")

# Also check entity was synced back
print(f"p2 entity co: {tuple(p2.co)}")

if abs(p2_y) < 0.01:
    print("\nPASS: Horizontal constraint solved from curve data!")
else:
    print(f"\nFAIL: p2.y = {p2_y}, expected ~0")
