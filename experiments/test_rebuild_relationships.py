"""Test that DirectConverter rebuild sets relationship attributes."""
import bpy

sse = bpy.context.scene.sketcher.entities
from bl_ext.blend.CAD_Sketcher.converters import DirectConverter

origin = sse.add_point_3d((0, 0, 0), fixed=True)
nm3d = sse.add_normal_3d((1, 0, 0, 0), fixed=True)
wp = sse.add_workplane(origin, nm3d, fixed=True)
sketch = sse.add_sketch(wp)

p1 = sse.add_point_2d((0, 0), sketch)
p2 = sse.add_point_2d((1, 0), sketch)
line = sse.add_line_2d(p1, p2, sketch)

# Rebuild via DirectConverter
if sketch.target_object:
    sketch.target_object.data.remove_curves()
else:
    curve = bpy.data.hair_curves.new(sketch.name)
    sketch.target_object = bpy.data.objects.new(sketch.name, curve)
    bpy.context.scene.collection.objects.link(sketch.target_object)

conv = DirectConverter(bpy.context.scene, sketch)
conv.to_bezier(sketch.target_object.data)

cd = sketch.target_object.data
sp = cd.attributes.get("start_point_id")
ep = cd.attributes.get("end_point_id")
type_attr = cd.attributes.get("sketch_type")
cid = cd.attributes.get("curve_id")

print(f"Curves: {len(cd.curves)}")
for i in range(len(cd.curves)):
    t = type_attr.data[i].value if type_attr else -1
    c = cid.data[i].value if cid else 0
    s = sp.data[i].value if sp else 0
    e = ep.data[i].value if ep else 0
    name = {0:"PT",1:"LN",2:"ARC",3:"CIR"}.get(t,"?")
    refs = f"start={s} end={e}" if s or e else ""
    print(f"  {i}: type={name} id={c} {refs}")

# Find the line curve
line_idx = None
for i in range(len(cd.curves)):
    if type_attr.data[i].value == 1:  # LINE
        line_idx = i
        break

assert line_idx is not None, "No line found"
assert sp.data[line_idx].value != 0, f"start_point_id not set on line"
assert ep.data[line_idx].value != 0, f"end_point_id not set on line"
print("\nPASS: DirectConverter sets relationship attributes")
