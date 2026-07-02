"""Examine how different entity types are represented in native curve data."""
import bpy
import math

sse = bpy.context.scene.sketcher.entities

origin = sse.add_point_3d((0, 0, 0), fixed=True)
nm3d = sse.add_normal_3d((1, 0, 0, 0), fixed=True)
wp = sse.add_workplane(origin, nm3d, fixed=True)
sketch = sse.add_sketch(wp)

# Add a line
p1 = sse.add_point_2d((0.0, 0.0), sketch)
p2 = sse.add_point_2d((1.0, 0.0), sketch)
line = sse.add_line_2d(p1, p2, sketch)

# Add a circle
nm2d = sse.add_normal_2d(sketch)
ct = sse.add_point_2d((3.0, 0.0), sketch)
circle = sse.add_circle(nm2d, ct, 1.0, sketch)

# Skip arc for now — entity.radius fails during add_native_circle
# because entity pointers aren't set up yet at that point
arc = None

cd = sketch.target_object.data
print(f"Total curves: {len(cd.curves)}")
print(f"Total points: {len(cd.points)}")

seg_attr = cd.attributes.get("segment_entity_index")
con_attr = cd.attributes.get("construction")
cyc_attr = cd.attributes.get("cyclic")

for i in range(len(cd.curves)):
    curve = cd.curves[i]
    entity_idx = seg_attr.data[i].value if seg_attr else -1
    entity = sse.get(entity_idx)
    cyclic = cyc_attr.data[i].value if cyc_attr else False

    print(f"\nCurve {i}: {entity} (points={curve.points_length}, cyclic={cyclic})")

    first = curve.points[0].index
    for j in range(curve.points_length):
        pt_idx = first + j
        pos = tuple(cd.points[pt_idx].position)
        print(f"  Point {j}: position={pos}")

        # Check handle attributes
        hl = cd.attributes.get("handle_left")
        hr = cd.attributes.get("handle_right")
        if hl:
            print(f"           handle_left={tuple(hl.data[pt_idx].vector)}")
        if hr:
            print(f"           handle_right={tuple(hr.data[pt_idx].vector)}")

print("\n--- Entity details ---")
print(f"Line: {line}, is_line={line.is_line()}, is_curve={line.is_curve()}")
print(f"Circle: {circle}, is_line={circle.is_line()}, is_curve={circle.is_curve()}, is_closed={circle.is_closed()}")

for e in (circle,):
    if hasattr(e, "bezier_segment_count"):
        print(f"{e}: bezier_segment_count={e.bezier_segment_count()}")
    if hasattr(e, "bezier_point_count"):
        print(f"{e}: bezier_point_count={e.bezier_point_count()}")
