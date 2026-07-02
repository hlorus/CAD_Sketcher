"""Dump arc handle data for arcs of various angles."""
import bpy
import math
from mathutils import Vector

sse = bpy.context.scene.sketcher.entities
from bl_ext.blend.CAD_Sketcher.converters import DirectConverter
from bl_ext.blend.CAD_Sketcher.draw_handler import _bezier_evaluate

origin = sse.add_point_3d((0, 0, 0), fixed=True)
nm3d = sse.add_normal_3d((1, 0, 0, 0), fixed=True)
wp = sse.add_workplane(origin, nm3d, fixed=True)
sketch = sse.add_sketch(wp)

# Create arcs of different angles
# Arc center at (0,0), radius 1
# For a 120-degree arc: start at (1,0), end at angle 120
for angle_deg in [60, 90, 120, 180, 270]:
    angle_rad = math.radians(angle_deg)
    nm2d = sse.add_normal_2d(sketch)
    ct = sse.add_point_2d((0.0, 0.0), sketch)
    p1 = sse.add_point_2d((1.0, 0.0), sketch)
    p2 = sse.add_point_2d((math.cos(angle_rad), math.sin(angle_rad)), sketch)
    # add_arc will create entity but add_native_circle may fail — that's OK
    arc = sse.add_arc(nm2d, ct, p1, p2, sketch)

# Rebuild with DirectConverter
if sketch.target_object:
    sketch.target_object.data.remove_curves()
else:
    import bpy
    curve = bpy.data.hair_curves.new(sketch.name)
    sketch.target_object = bpy.data.objects.new(sketch.name, curve)
    bpy.context.scene.collection.objects.link(sketch.target_object)

conv = DirectConverter(bpy.context.scene, sketch)
conv.to_bezier(sketch.target_object.data)

cd = sketch.target_object.data
seg_attr = cd.attributes.get("segment_entity_index")
cyc_attr = cd.attributes.get("cyclic")
hl = cd.attributes.get("handle_left")
hr = cd.attributes.get("handle_right")

print(f"Total curves: {len(cd.curves)}")

angles = [60, 90, 120, 180, 270]
for ci in range(len(cd.curves)):
    curve = cd.curves[ci]
    np = curve.points_length
    cyclic = cyc_attr.data[ci].value if cyc_attr else False
    angle = angles[ci] if ci < len(angles) else "?"

    print(f"\n--- Arc {angle}° (points={np}, cyclic={cyclic}) ---")
    first = curve.points[0].index
    for j in range(np):
        idx = first + j
        pos = Vector(cd.points[idx].position)
        h_l = Vector(hl.data[idx].vector)
        h_r = Vector(hr.data[idx].vector)
        print(f"  Pt {j}: pos=({pos.x:.4f}, {pos.y:.4f}) "
              f"hl=({h_l.x:.4f}, {h_l.y:.4f}) "
              f"hr=({h_r.x:.4f}, {h_r.y:.4f})")

    # Tessellate and check radius deviation
    n_segs = np if cyclic else np - 1
    max_err = 0
    for s in range(n_segs):
        i0 = s
        i1 = (s + 1) % np
        pts = _bezier_evaluate(
            Vector(cd.points[first + i0].position),
            Vector(hr.data[first + i0].vector),
            Vector(hl.data[first + i1].vector),
            Vector(cd.points[first + i1].position),
            steps=12,
        )
        for p in pts:
            err = abs(Vector(p[:2]).length - 1.0)
            max_err = max(max_err, err)

    print(f"  Max radius deviation: {max_err:.6f} {'OK' if max_err < 0.01 else 'BAD!'}")
