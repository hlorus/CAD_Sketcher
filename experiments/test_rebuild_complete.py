"""Test that DirectConverter rebuild produces correct sketch_type for all entities."""
import bpy
from bl_ext.blend.CAD_Sketcher.converters import DirectConverter, SketchCurveType

sse = bpy.context.scene.sketcher.entities

origin = sse.add_point_3d((0, 0, 0), fixed=True)
nm3d = sse.add_normal_3d((1, 0, 0, 0), fixed=True)
wp = sse.add_workplane(origin, nm3d, fixed=True)
sketch = sse.add_sketch(wp)

p1 = sse.add_point_2d((0.0, 0.0), sketch)
p2 = sse.add_point_2d((1.0, 0.0), sketch)
line = sse.add_line_2d(p1, p2, sketch)

nm2d = sse.add_normal_2d(sketch)
ct = sse.add_point_2d((3.0, 0.0), sketch)
circle = sse.add_circle(nm2d, ct, 1.0, sketch)

# Full rebuild via DirectConverter
if sketch.target_object:
    sketch.target_object.data.remove_curves()
else:
    curve = bpy.data.hair_curves.new(sketch.name)
    sketch.target_object = bpy.data.objects.new(sketch.name, curve)
    bpy.context.scene.collection.objects.link(sketch.target_object)

conv = DirectConverter(bpy.context.scene, sketch)
conv.to_bezier(sketch.target_object.data)

cd = sketch.target_object.data
type_attr = cd.attributes.get("sketch_type")
seg_attr = cd.attributes.get("segment_entity_index")

print(f"After DirectConverter rebuild: {len(cd.curves)} curves")
points = lines = circles = 0
for i in range(len(cd.curves)):
    ctype = type_attr.data[i].value if type_attr else -1
    name = {0:"POINT",1:"LINE",2:"ARC",3:"CIRCLE"}.get(ctype, "?")
    entity = sse.get(seg_attr.data[i].value) if seg_attr else None
    print(f"  Curve {i}: type={name} pts={cd.curves[i].points_length} entity={entity}")
    if ctype == 0: points += 1
    elif ctype == 1: lines += 1
    elif ctype == 3: circles += 1

assert points == 3, f"Expected 3 points, got {points}"
assert lines == 1, f"Expected 1 line, got {lines}"
assert circles == 1, f"Expected 1 circle, got {circles}"
print("PASS: DirectConverter rebuild has correct sketch_type for all entities")
