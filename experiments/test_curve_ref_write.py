"""Test CurveRef write and create capabilities."""
import bpy
import math

scene = bpy.context.scene
sse = scene.sketcher.entities
ssc = scene.sketcher.constraints

sse.ensure_origin_elements(bpy.context)
wp = sse.origin_plane_XY
sketch = sse.add_sketch(wp)
scene.sketcher.active_sketch_i = sketch.slvs_index

from bl_ext.blend.CAD_Sketcher.converters import ensure_sketch_curve_object
from bl_ext.blend.CAD_Sketcher.model.curve_ref import (
    PointRef, LineRef, ArcRef, CircleRef, curve_ref,
)

ensure_sketch_curve_object(sketch)

# --- PointRef.create ---
print("=== PointRef.create ===")
p0 = PointRef.create(sketch, (0, 0), fixed=True)
p1 = PointRef.create(sketch, (3, 0))
p2 = PointRef.create(sketch, (0, 4))

assert isinstance(p0, PointRef)
assert p0.valid
assert abs(p0.co.x) < 0.01
assert abs(p1.co.x - 3.0) < 0.01
assert abs(p2.co.y - 4.0) < 0.01
assert p0.fixed == True
assert p1.fixed == False
print(f"p0={p0}, co={p0.co}")
print(f"p1={p1}, co={p1.co}")
print(f"p2={p2}, co={p2.co}")

# --- PointRef.co setter ---
print("\n=== PointRef.co setter ===")
p1.co = (5, 0)
assert abs(p1.co.x - 5.0) < 0.01, f"Expected 5, got {p1.co.x}"
print(f"p1.co after set = {p1.co}")

p1.co = (3, 0)  # reset

# --- Flag setters ---
print("\n=== Flag setters ===")
p1.construction = True
assert p1.construction == True
p1.construction = False
assert p1.construction == False
print("construction setter works")

p1.visible = False
assert p1.visible == False
p1.visible = True
print("visible setter works")

# --- LineRef.create ---
print("\n=== LineRef.create ===")
line = LineRef.create(sketch, p0, p1)
assert isinstance(line, LineRef)
assert line.valid
assert line.p1 is not None
assert line.p2 is not None
assert abs(line.p1.co.x) < 0.01
assert abs(line.p2.co.x - 3.0) < 0.01
assert abs(line.length - 3.0) < 0.01
print(f"line={line}, length={line.length:.4f}")
print(f"line.p1={line.p1}, line.p2={line.p2}")

# --- CircleRef.create ---
print("\n=== CircleRef.create ===")
ct = PointRef.create(sketch, (5, 5))
circle = CircleRef.create(sketch, ct, radius=2.0)
assert isinstance(circle, CircleRef)
assert circle.valid
assert circle.is_circle()
assert circle.is_closed()
print(f"circle={circle}, radius={circle.radius:.4f}")
assert abs(circle.radius - 2.0) < 0.01, f"Expected radius 2.0, got {circle.radius}"
assert circle.ct is not None
assert abs(circle.ct.co.x - 5.0) < 0.01

# --- ArcRef.create ---
print("\n=== ArcRef.create ===")
arc_ct = PointRef.create(sketch, (0, 0))
arc_start = PointRef.create(sketch, (1, 0))
arc_end = PointRef.create(sketch, (0, 1))
arc = ArcRef.create(sketch, arc_ct, arc_start, arc_end)
assert isinstance(arc, ArcRef)
assert arc.valid
assert arc.is_arc()
assert not arc.is_circle()
print(f"arc={arc}, radius={arc.radius:.4f}, angle={math.degrees(arc.angle):.1f} deg")
assert abs(arc.radius - 1.0) < 0.01
assert abs(arc.angle - math.pi/2) < 0.1  # ~90 degrees

# --- remove ---
print("\n=== remove ===")
p_temp = PointRef.create(sketch, (99, 99))
temp_id = p_temp.curve_id
assert p_temp.valid
p_temp.remove()
assert not p_temp.valid
# Verify it's gone
check = curve_ref(sketch, temp_id)
assert not check.valid
print("remove works")

# --- Verify total curve count ---
cd = sketch.target_object.data
print(f"\nTotal curves: {len(cd.curves)}")

print("\nAll tests PASSED")
