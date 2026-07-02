"""Debug arc tessellation for 120° arc."""
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

# 120° arc, center (0,0), radius 1
angle = math.radians(120)
nm2d = sse.add_normal_2d(sketch)
ct = sse.add_point_2d((0.0, 0.0), sketch)
p1 = sse.add_point_2d((1.0, 0.0), sketch)
p2 = sse.add_point_2d((math.cos(angle), math.sin(angle)), sketch)
arc = sse.add_arc(nm2d, ct, p1, p2, sketch)

# Rebuild
if sketch.target_object:
    sketch.target_object.data.remove_curves()
else:
    curve = bpy.data.hair_curves.new(sketch.name)
    sketch.target_object = bpy.data.objects.new(sketch.name, curve)
    bpy.context.scene.collection.objects.link(sketch.target_object)

conv = DirectConverter(bpy.context.scene, sketch)
conv.to_bezier(sketch.target_object.data)

cd = sketch.target_object.data
curve = cd.curves[0]
np = curve.points_length
first = curve.points[0].index

hl = cd.attributes.get("handle_left")
hr = cd.attributes.get("handle_right")

print(f"120° arc: {np} points")

# Tessellate each segment and show deviation
for s in range(np - 1):
    i0 = first + s
    i1 = first + s + 1

    p0 = Vector(cd.points[i0].position)
    p1v = Vector(cd.points[i1].position)
    h0r = Vector(hr.data[i0].vector)
    h1l = Vector(hl.data[i1].vector)

    print(f"\nSegment {s}:")
    print(f"  p0=({p0.x:.4f}, {p0.y:.4f})")
    print(f"  handle_right[{s}]=({h0r.x:.4f}, {h0r.y:.4f})  offset from p0=({h0r.x-p0.x:.4f}, {h0r.y-p0.y:.4f})")
    print(f"  handle_left[{s+1}]=({h1l.x:.4f}, {h1l.y:.4f})  offset from p1=({h1l.x-p1v.x:.4f}, {h1l.y-p1v.y:.4f})")
    print(f"  p1=({p1v.x:.4f}, {p1v.y:.4f})")

    pts = _bezier_evaluate(p0, h0r, h1l, p1v, steps=8)
    print(f"  Tessellated:")
    for i, p in enumerate(pts):
        r = Vector(p[:2]).length
        expected_angle = math.atan2(p[1], p[0])
        print(f"    t={i/8:.3f}: ({p.x:.4f}, {p.y:.4f}) r={r:.4f} err={abs(r-1):.4f}")
