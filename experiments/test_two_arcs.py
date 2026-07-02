"""Test creating two arcs sequentially - reproduces crash on second arc."""
import bpy
import math
import traceback

sse = bpy.context.scene.sketcher.entities
from bl_ext.blend.CAD_Sketcher.converters import (
    add_native_point, add_native_circle, update_native_curves,
    sync_curve_selection,
)
from bl_ext.blend.CAD_Sketcher.solver import solve_system

origin = sse.add_point_3d((0, 0, 0), fixed=True)
nm3d = sse.add_normal_3d((1, 0, 0, 0), fixed=True)
wp = sse.add_workplane(origin, nm3d, fixed=True)
sketch = sse.add_sketch(wp)

print("=== Creating first arc ===")
try:
    ct1 = sse.add_point_2d((0.0, 0.0), sketch)
    add_native_point(sketch, ct1, ct1.co)
    p1 = sse.add_point_2d((1.0, 0.0), sketch)
    add_native_point(sketch, p1, p1.co)
    p2 = sse.add_point_2d((0.0, 1.0), sketch)
    add_native_point(sketch, p2, p2.co)
    nm2d = sse.add_normal_2d(sketch)
    arc1 = sse.add_arc(nm2d, ct1, p1, p2, sketch)
    add_native_circle(sketch, arc1, ct1.co, arc1.radius, is_arc=True)
    print(f"  Arc1 created. Curves: {len(sketch.target_object.data.curves)}")
except Exception as e:
    print(f"  FAILED: {e}")
    traceback.print_exc()

# Simulate what draw_cb does
print("\n=== Simulating draw_cb (update + sync) ===")
try:
    update_native_curves(bpy.context.scene)
    sync_curve_selection(bpy.context.scene)
    print("  OK")
except Exception as e:
    print(f"  FAILED: {e}")
    traceback.print_exc()

# Simulate solve
print("\n=== Solving ===")
try:
    solve_system(bpy.context, sketch=sketch)
    print("  OK")
except Exception as e:
    print(f"  FAILED: {e}")
    traceback.print_exc()

# Simulate draw_cb again
print("\n=== Simulating draw_cb again ===")
try:
    update_native_curves(bpy.context.scene)
    sync_curve_selection(bpy.context.scene)
    print(f"  OK. Curves: {len(sketch.target_object.data.curves)}")
except Exception as e:
    print(f"  FAILED: {e}")
    traceback.print_exc()

print("\n=== Creating second arc ===")
try:
    ct2 = sse.add_point_2d((3.0, 0.0), sketch)
    add_native_point(sketch, ct2, ct2.co)
    p3 = sse.add_point_2d((4.0, 0.0), sketch)
    add_native_point(sketch, p3, p3.co)
    p4 = sse.add_point_2d((3.0, 1.0), sketch)
    add_native_point(sketch, p4, p4.co)
    nm2d_2 = sse.add_normal_2d(sketch)
    arc2 = sse.add_arc(nm2d_2, ct2, p3, p4, sketch)
    print(f"  add_arc done. About to call add_native_circle...")
    add_native_circle(sketch, arc2, ct2.co, arc2.radius, is_arc=True)
    print(f"  Arc2 created. Curves: {len(sketch.target_object.data.curves)}")
except Exception as e:
    print(f"  FAILED: {e}")
    traceback.print_exc()

# One more draw_cb cycle
print("\n=== Final draw_cb ===")
try:
    update_native_curves(bpy.context.scene)
    sync_curve_selection(bpy.context.scene)
    print(f"  OK. Curves: {len(sketch.target_object.data.curves)}")
except Exception as e:
    print(f"  FAILED: {e}")
    traceback.print_exc()

print("\nDONE - no crash")
