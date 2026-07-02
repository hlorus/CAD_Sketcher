"""Test that relationship attributes are set correctly."""
import bpy

sse = bpy.context.scene.sketcher.entities
from bl_ext.blend.CAD_Sketcher.converters import (
    add_native_point, add_native_line, add_native_circle, SketchCurveType,
)

origin = sse.add_point_3d((0, 0, 0), fixed=True)
nm3d = sse.add_normal_3d((1, 0, 0, 0), fixed=True)
wp = sse.add_workplane(origin, nm3d, fixed=True)
sketch = sse.add_sketch(wp)

# Create points and line
p1 = sse.add_point_2d((0.0, 0.0), sketch)
cid_p1 = add_native_point(sketch, p1, p1.co)

p2 = sse.add_point_2d((1.0, 0.0), sketch)
cid_p2 = add_native_point(sketch, p2, p2.co)

line = sse.add_line_2d(p1, p2, sketch)
cid_line = add_native_line(sketch, line, p1.co, p2.co,
                           start_point_id=cid_p1, end_point_id=cid_p2)

# Create circle with center
ct = sse.add_point_2d((3.0, 0.0), sketch)
cid_ct = add_native_point(sketch, ct, ct.co)
nm2d = sse.add_normal_2d(sketch)
circle = sse.add_circle(nm2d, ct, 1.0, sketch)
cid_circle = add_native_circle(sketch, circle, ct.co, 1.0,
                               center_point_id=cid_ct)

cd = sketch.target_object.data
type_attr = cd.attributes.get("sketch_type")
cid_attr = cd.attributes.get("curve_id")
sp_attr = cd.attributes.get("start_point_id")
ep_attr = cd.attributes.get("end_point_id")
cp_attr = cd.attributes.get("center_point_id")

print(f"Curves: {len(cd.curves)}")
for i in range(len(cd.curves)):
    ctype = type_attr.data[i].value
    cid = cid_attr.data[i].value
    sp = sp_attr.data[i].value
    ep = ep_attr.data[i].value
    cp = cp_attr.data[i].value
    name = {0:"POINT",1:"LINE",2:"ARC",3:"CIRCLE"}.get(ctype, "?")
    refs = []
    if sp: refs.append(f"start={sp}")
    if ep: refs.append(f"end={ep}")
    if cp: refs.append(f"center={cp}")
    print(f"  {i}: type={name} id={cid} {' '.join(refs)}")

# Verify
assert sp_attr.data[2].value == cid_p1, "Line start_point_id wrong"
assert ep_attr.data[2].value == cid_p2, "Line end_point_id wrong"
assert cp_attr.data[4].value == cid_ct, "Circle center_point_id wrong"
print("\nPASS: All relationships correct")
