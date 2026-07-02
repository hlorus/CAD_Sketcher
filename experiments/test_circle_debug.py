"""Debug circle curve data after DirectConverter rebuild."""
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

nm2d = sse.add_normal_2d(sketch)
ct = sse.add_point_2d((0.0, 0.0), sketch)
circle = sse.add_circle(nm2d, ct, 1.0, sketch)

# Rebuild with DirectConverter
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
cyc = cd.attributes.get("cyclic")
is_cyclic = cyc.data[0].value if cyc else False

hl = cd.attributes.get("handle_left")
hr = cd.attributes.get("handle_right")

print(f"Circle: {np} points, cyclic={is_cyclic}")

for j in range(np):
    idx = first + j
    pos = Vector(cd.points[idx].position)
    h_l = Vector(hl.data[idx].vector)
    h_r = Vector(hr.data[idx].vector)
    angle = math.degrees(math.atan2(pos.y, pos.x))
    print(f"  Pt {j}: pos=({pos.x:.4f}, {pos.y:.4f}) angle={angle:.1f}°")
    print(f"    hl=({h_l.x:.4f}, {h_l.y:.4f}) hr=({h_r.x:.4f}, {h_r.y:.4f})")

# Now compare with add_native_circle result
print(f"\n--- Compare with add_native_circle ---")
# Create fresh
sse2 = bpy.context.scene.sketcher.entities
nm2d_b = sse2.add_normal_2d(sketch)
ct_b = sse2.add_point_2d((5.0, 0.0), sketch)
circle_b = sse2.add_circle(nm2d_b, ct_b, 1.0, sketch)

# The add_native_circle should have added a curve
# Find it - it's the last curve
cd2 = sketch.target_object.data
n_curves = len(cd2.curves)
print(f"Total curves after add: {n_curves}")

if n_curves >= 2:
    curve2 = cd2.curves[n_curves - 1]
    np2 = curve2.points_length
    first2 = curve2.points[0].index
    print(f"add_native_circle result: {np2} points")
    for j in range(np2):
        idx = first2 + j
        pos = Vector(cd2.points[idx].position)
        h_l = Vector(hl.data[idx].vector)
        h_r = Vector(hr.data[idx].vector)
        print(f"  Pt {j}: pos=({pos.x:.4f}, {pos.y:.4f})")
        print(f"    hl=({h_l.x:.4f}, {h_l.y:.4f}) hr=({h_r.x:.4f}, {h_r.y:.4f})")

# Tessellate the DirectConverter circle and check
print(f"\n--- Tessellation check (DirectConverter circle) ---")
n_segs = np  # cyclic
max_err = 0
worst_seg = -1
for s in range(n_segs):
    i0 = s
    i1 = (s + 1) % np
    p0 = Vector(cd.points[first + i0].position)
    p1 = Vector(cd.points[first + i1].position)
    h0r = Vector(hr.data[first + i0].vector)
    h1l = Vector(hl.data[first + i1].vector)

    pts = _bezier_evaluate(p0, h0r, h1l, p1, steps=12)
    seg_err = 0
    for p in pts:
        err = abs(Vector(p[:2]).length - 1.0)
        seg_err = max(seg_err, err)
    max_err = max(max_err, seg_err)
    if seg_err > 0.001:
        worst_seg = s
    print(f"  Seg {s} ({math.degrees(math.atan2(p0.y,p0.x)):.0f}°→{math.degrees(math.atan2(p1.y,p1.x)):.0f}°): max_err={seg_err:.6f}")

print(f"\nOverall max deviation: {max_err:.6f}")
