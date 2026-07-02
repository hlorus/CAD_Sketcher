"""Test bezier tessellation produces correct points for a circle."""
import bpy
from mathutils import Vector

sse = bpy.context.scene.sketcher.entities
from bl_ext.blend.CAD_Sketcher.draw_handler import _bezier_evaluate

# Setup a circle
origin = sse.add_point_3d((0, 0, 0), fixed=True)
nm3d = sse.add_normal_3d((1, 0, 0, 0), fixed=True)
wp = sse.add_workplane(origin, nm3d, fixed=True)
sketch = sse.add_sketch(wp)
nm2d = sse.add_normal_2d(sketch)
ct = sse.add_point_2d((0.0, 0.0), sketch)
circle = sse.add_circle(nm2d, ct, 1.0, sketch)

cd = sketch.target_object.data
curve = cd.curves[0]  # The circle
first = curve.points[0].index
n_points = curve.points_length

print(f"Circle: {n_points} points, cyclic=True")

hl = cd.attributes.get("handle_left")
hr = cd.attributes.get("handle_right")

# Tessellate first segment
p0 = Vector(cd.points[first].position)
h0r = Vector(hr.data[first].vector)
h1l = Vector(hl.data[first + 1].vector)
p1 = Vector(cd.points[first + 1].position)

print(f"\nSegment 0: {tuple(p0)} -> {tuple(p1)}")
print(f"  handle_right[0] = {tuple(h0r)}")
print(f"  handle_left[1] = {tuple(h1l)}")

pts = _bezier_evaluate(p0, h0r, h1l, p1, steps=4)
print(f"  Tessellated ({len(pts)} points):")
for i, p in enumerate(pts):
    # Check distance from origin (should be ~1.0 for a unit circle)
    dist = p.length
    print(f"    {i}: ({p.x:.4f}, {p.y:.4f}) dist={dist:.4f}")

# Tessellate full circle
print(f"\nFull circle tessellation (8 steps per segment):")
import math
max_err = 0
for seg in range(n_points):
    i0 = seg
    i1 = (seg + 1) % n_points
    pts = _bezier_evaluate(
        Vector(cd.points[first + i0].position),
        Vector(hr.data[first + i0].vector),
        Vector(hl.data[first + i1].vector),
        Vector(cd.points[first + i1].position),
        steps=8,
    )
    for p in pts:
        err = abs(p.length - 1.0)
        max_err = max(max_err, err)

print(f"  Max deviation from unit circle: {max_err:.6f}")
assert max_err < 0.003, f"Tessellation error too large: {max_err}"
print("  PASS: Circle tessellation is accurate")
