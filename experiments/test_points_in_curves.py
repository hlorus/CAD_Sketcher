"""Verify that all points (including centers) are in curve data."""
import bpy

sse = bpy.context.scene.sketcher.entities
from bl_ext.blend.CAD_Sketcher.converters import SketchCurveType, add_native_point

origin = sse.add_point_3d((0, 0, 0), fixed=True)
nm3d = sse.add_normal_3d((1, 0, 0, 0), fixed=True)
wp = sse.add_workplane(origin, nm3d, fixed=True)
sketch = sse.add_sketch(wp)

# Standalone point
p_standalone = sse.add_point_2d((0.0, 0.0), sketch)
add_native_point(sketch, p_standalone, p_standalone.co)

# Line endpoints
p1 = sse.add_point_2d((1.0, 0.0), sketch)
add_native_point(sketch, p1, p1.co)
p2 = sse.add_point_2d((2.0, 0.0), sketch)
add_native_point(sketch, p2, p2.co)
from bl_ext.blend.CAD_Sketcher.converters import add_native_line
line = sse.add_line_2d(p1, p2, sketch)
add_native_line(sketch, line, p1.co, p2.co)

# Circle with center
ct = sse.add_point_2d((4.0, 0.0), sketch)
add_native_point(sketch, ct, ct.co)
nm2d = sse.add_normal_2d(sketch)
from bl_ext.blend.CAD_Sketcher.converters import add_native_circle
circle = sse.add_circle(nm2d, ct, 1.0, sketch)
add_native_circle(sketch, circle, ct.co, 1.0)

cd = sketch.target_object.data
type_attr = cd.attributes.get("sketch_type")
seg_attr = cd.attributes.get("segment_entity_index")

print(f"Total curves: {len(cd.curves)}")
points = 0
lines = 0
arcs = 0
circles = 0
for i in range(len(cd.curves)):
    ctype = type_attr.data[i].value if type_attr else -1
    entity_idx = seg_attr.data[i].value if seg_attr else -1
    entity = sse.get(entity_idx)
    n_pts = cd.curves[i].points_length

    type_name = {0: "POINT", 1: "LINE", 2: "ARC", 3: "CIRCLE"}.get(ctype, "?")
    print(f"  Curve {i}: type={type_name} pts={n_pts} entity={entity}")

    if ctype == SketchCurveType.POINT:
        points += 1
    elif ctype == SketchCurveType.LINE:
        lines += 1
    elif ctype == SketchCurveType.ARC:
        arcs += 1
    elif ctype == SketchCurveType.CIRCLE:
        circles += 1

print(f"\nSummary: {points} points, {lines} lines, {arcs} arcs, {circles} circles")
assert points == 4, f"Expected 4 points (standalone + 2 line endpoints + circle center), got {points}"
assert lines == 1, f"Expected 1 line, got {lines}"
assert circles == 1, f"Expected 1 circle, got {circles}"
print("PASS")
