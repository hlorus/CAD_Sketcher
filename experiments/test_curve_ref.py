"""Test CurveRef typed subclasses in headless Blender."""
import bpy
import math

scene = bpy.context.scene
sse = scene.sketcher.entities
ssc = scene.sketcher.constraints

sse.ensure_origin_elements(bpy.context)
wp = sse.origin_plane_XY
sketch = sse.add_sketch(wp)
scene.sketcher.active_sketch_i = sketch.slvs_index

# Create geometry
p0 = sse.add_point_2d((0, 0), sketch, fixed=True)
p1 = sse.add_point_2d((3, 0), sketch)
p2 = sse.add_point_2d((0, 4), sketch)
line = sse.add_line_2d(p0, p1, sketch)
ct_pt = sse.add_point_2d((5, 5), sketch)
arc = sse.add_arc(sketch.wp.nm, ct_pt, p0, p1, sketch)

# Build native curves
from bl_ext.blend.CAD_Sketcher.converters import (
    DirectConverter, get_curve_id_for_entity, ensure_sketch_curve_object,
)
curve_data = ensure_sketch_curve_object(sketch)
conv = DirectConverter(scene, sketch)
conv.to_bezier(curve_data)

# Get curve_ids
cid_p0 = get_curve_id_for_entity(sketch, p0.slvs_index)
cid_p1 = get_curve_id_for_entity(sketch, p1.slvs_index)
cid_p2 = get_curve_id_for_entity(sketch, p2.slvs_index)
cid_line = get_curve_id_for_entity(sketch, line.slvs_index)
cid_arc = get_curve_id_for_entity(sketch, arc.slvs_index)

# Test factory
from bl_ext.blend.CAD_Sketcher.model.curve_ref import (
    curve_ref, CurveRef, PointRef, LineRef, ArcRef, CircleRef,
)

ref_p0 = curve_ref(sketch, cid_p0)
ref_p1 = curve_ref(sketch, cid_p1)
ref_p2 = curve_ref(sketch, cid_p2)
ref_line = curve_ref(sketch, cid_line)
ref_arc = curve_ref(sketch, cid_arc)

# --- Type checks ---
print("=== Type checks ===")
assert isinstance(ref_p0, PointRef), f"Expected PointRef, got {type(ref_p0)}"
assert isinstance(ref_line, LineRef), f"Expected LineRef, got {type(ref_line)}"
assert isinstance(ref_arc, ArcRef), f"Expected ArcRef, got {type(ref_arc)}"
print(f"p0: {ref_p0}")
print(f"line: {ref_line}")
print(f"arc: {ref_arc}")

assert ref_p0.is_point() and not ref_p0.is_line()
assert ref_line.is_line() and not ref_line.is_point()
assert ref_arc.is_curve() and ref_arc.is_arc() and not ref_arc.is_circle()

# --- PointRef ---
print("\n=== PointRef ===")
assert abs(ref_p0.co.x) < 0.01
assert abs(ref_p1.co.x - 3.0) < 0.01
assert abs(ref_p2.co.y - 4.0) < 0.01
print(f"p0.co={ref_p0.co}, p1.co={ref_p1.co}, p2.co={ref_p2.co}")

# PointRef should NOT have p1/p2/ct/radius
assert not hasattr(ref_p0, "p1"), "PointRef should not have p1"
assert not hasattr(ref_p0, "radius"), "PointRef should not have radius"
print("PointRef correctly lacks line/arc properties")

# --- LineRef ---
print("\n=== LineRef ===")
lp1 = ref_line.p1
lp2 = ref_line.p2
assert isinstance(lp1, PointRef), f"line.p1 should be PointRef, got {type(lp1)}"
assert isinstance(lp2, PointRef), f"line.p2 should be PointRef, got {type(lp2)}"
print(f"line.p1.co={lp1.co}, line.p2.co={lp2.co}")

dvec = ref_line.direction_vec()
print(f"line.direction_vec()={dvec}")
assert abs(dvec.x - 1.0) < 0.01, f"Expected (1,0), got {dvec}"

mid = ref_line.midpoint()
print(f"line.midpoint()={mid}")
assert abs(mid.x - 1.5) < 0.01

print(f"line.length={ref_line.length:.4f}")
assert abs(ref_line.length - 3.0) < 0.01

nm = ref_line.normal()
print(f"line.normal()={nm}")
assert abs(nm.x) < 0.01 and abs(abs(nm.y) - 1.0) < 0.01

# LineRef should NOT have ct/radius/angle
assert not hasattr(ref_line, "ct"), "LineRef should not have ct"
assert not hasattr(ref_line, "radius"), "LineRef should not have radius"
print("LineRef correctly lacks arc properties")

# --- ArcRef ---
print("\n=== ArcRef ===")
ct = ref_arc.ct
assert isinstance(ct, PointRef), f"arc.ct should be PointRef, got {type(ct)}"
print(f"arc.ct.co={ct.co}")
assert abs(ct.co.x - 5.0) < 0.01

start = ref_arc.start
end = ref_arc.end
print(f"arc.start={start}, arc.end={end}")
assert start is not None
assert end is not None

print(f"arc.radius={ref_arc.radius:.4f}")
assert ref_arc.radius > 0

print(f"arc.angle={math.degrees(ref_arc.angle):.1f} deg")
assert ref_arc.angle > 0

print(f"arc.start_angle={math.degrees(ref_arc.start_angle):.1f} deg")

pt = ref_arc.point_on_curve(ref_arc.angle / 2)
print(f"arc.point_on_curve(half)={pt}")

# ArcRef should NOT have direction_vec/midpoint/length
assert not hasattr(ref_arc, "direction_vec"), "ArcRef should not have direction_vec"
assert not hasattr(ref_arc, "midpoint"), "ArcRef should not have midpoint"
print("ArcRef correctly lacks line properties")

# --- Invalid ref ---
print("\n=== Invalid ref ===")
ref_bad = curve_ref(sketch, 9999)
assert isinstance(ref_bad, CurveRef)
assert not isinstance(ref_bad, (PointRef, LineRef, ArcRef, CircleRef))
assert not ref_bad.valid
print(f"Invalid ref: {ref_bad}, valid={ref_bad.valid}")

# --- Equality ---
print("\n=== Equality ===")
ref_p0b = curve_ref(sketch, cid_p0)
assert ref_p0 == ref_p0b
assert ref_p0 != ref_p1

# --- wp_matrix ---
print(f"\n=== wp_matrix ===")
print(f"wp_matrix={ref_p0.wp_matrix}")

print("\nAll tests PASSED")
