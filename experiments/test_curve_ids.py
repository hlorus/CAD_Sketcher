"""Test curve_id allocation and lookup."""
import bpy

sse = bpy.context.scene.sketcher.entities
from bl_ext.blend.CAD_Sketcher.converters import (
    add_native_point, add_native_line, add_native_circle,
    get_curve_index, invalidate_curve_id_cache, remove_native_curve,
)

origin = sse.add_point_3d((0, 0, 0), fixed=True)
nm3d = sse.add_normal_3d((1, 0, 0, 0), fixed=True)
wp = sse.add_workplane(origin, nm3d, fixed=True)
sketch = sse.add_sketch(wp)

print(f"Initial next_curve_id: {sketch.next_curve_id}")

# Create entities + native curves
p1 = sse.add_point_2d((0.0, 0.0), sketch)
cid_p1 = add_native_point(sketch, p1, p1.co)

p2 = sse.add_point_2d((1.0, 0.0), sketch)
cid_p2 = add_native_point(sketch, p2, p2.co)

line = sse.add_line_2d(p1, p2, sketch)
cid_line = add_native_line(sketch, line, p1.co, p2.co)

nm2d = sse.add_normal_2d(sketch)
ct = sse.add_point_2d((3.0, 0.0), sketch)
cid_ct = add_native_point(sketch, ct, ct.co)
circle = sse.add_circle(nm2d, ct, 1.0, sketch)
cid_circle = add_native_circle(sketch, circle, ct.co, 1.0)

print(f"\nAllocated curve_ids:")
print(f"  p1: {cid_p1}, p2: {cid_p2}, line: {cid_line}, ct: {cid_ct}, circle: {cid_circle}")
print(f"  next_curve_id: {sketch.next_curve_id}")

# Verify curve_id attribute values
cd = sketch.target_object.data
cid_attr = cd.attributes.get("curve_id")
print(f"\nCurve data: {len(cd.curves)} curves")
for i in range(len(cd.curves)):
    print(f"  Curve {i}: curve_id={cid_attr.data[i].value}")

# Test lookup
print(f"\nLookup tests:")
for cid in (cid_p1, cid_p2, cid_line, cid_ct, cid_circle):
    idx = get_curve_index(sketch, cid)
    print(f"  curve_id={cid} → curve_index={idx}")

# Test stability after removal
print(f"\nRemoving p1 (entity_index={p1.slvs_index})...")
remove_native_curve(sketch, p1.slvs_index)
print(f"Curves after removal: {len(cd.curves)}")

# Lookup should still work for remaining curves
for cid in (cid_p2, cid_line, cid_ct, cid_circle):
    idx = get_curve_index(sketch, cid)
    actual_cid = cid_attr.data[idx].value if idx is not None else None
    print(f"  curve_id={cid} → index={idx}, verified={actual_cid == cid}")

# p1's curve_id should not be found
idx = get_curve_index(sketch, cid_p1)
print(f"  curve_id={cid_p1} (removed) → index={idx}")
assert idx is None, f"Removed curve_id should return None, got {idx}"

print("\nPASS")
