"""Test workplane empty creation and solver reading from it."""
import bpy
import math
from mathutils import Matrix, Vector, Quaternion

sse = bpy.context.scene.sketcher.entities
from bl_ext.blend.CAD_Sketcher.converters import (
    ensure_workplane_empty, add_native_point, add_native_line,
)
from bl_ext.blend.CAD_Sketcher.curve_solver import solve_sketch_from_curves

# Setup sketch on XY plane
origin = sse.add_point_3d((0, 0, 0), fixed=True)
nm3d = sse.add_normal_3d((1, 0, 0, 0), fixed=True)
wp = sse.add_workplane(origin, nm3d, fixed=True)
sketch = sse.add_sketch(wp)
bpy.context.scene.sketcher.active_sketch_i = sketch.slvs_index

# Ensure workplane empty
wp_obj = ensure_workplane_empty(sketch)
print(f"Workplane empty: {wp_obj.name}")
print(f"  Location: {tuple(wp_obj.matrix_world.translation)}")
print(f"  Rotation: {tuple(wp_obj.matrix_world.to_quaternion())}")

# Verify it matches entity workplane
entity_mat = sketch.wp.matrix_basis
print(f"  Entity wp location: {tuple(entity_mat.translation)}")
print(f"  Matrices match: {wp_obj.matrix_world == entity_mat}")

# Create geometry
p1 = sse.add_point_2d((0.0, 0.0), sketch, fixed=True)
cid_p1 = add_native_point(sketch, p1, p1.co)
p2 = sse.add_point_2d((1.0, 0.3), sketch)
cid_p2 = add_native_point(sketch, p2, p2.co)
line = sse.add_line_2d(p1, p2, sketch)
from bl_ext.blend.CAD_Sketcher.converters import get_curve_id_for_entity
add_native_line(sketch, line, p1.co, p2.co,
                start_point_id=cid_p1, end_point_id=cid_p2)

# Add horizontal constraint
ssc = bpy.context.scene.sketcher.constraints
ssc.add_horizontal(line, sketch=sketch, curve_id_1=3)  # line curve_id

# Solve — should read workplane from empty
print(f"\nSolving with workplane from empty...")
ok = solve_sketch_from_curves(bpy.context, sketch)
print(f"Result: {'OK' if ok else 'FAILED'}")

cd = sketch.target_object.data
p2_pos = cd.points[cd.curves[1].points[0].index].position
print(f"p2 after solve: ({p2_pos[0]:.4f}, {p2_pos[1]:.4f})")
assert abs(p2_pos[1]) < 0.01, f"Horizontal constraint failed! y={p2_pos[1]}"

# Verify workplane_object persists
assert sketch.workplane_object == wp_obj
print(f"\nWorkplane object persists: {sketch.workplane_object.name}")

print("\nPASS")
