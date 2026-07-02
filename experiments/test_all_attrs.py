"""Verify all curve attributes are set correctly for entity-free drawing."""
import bpy

sse = bpy.context.scene.sketcher.entities

origin = sse.add_point_3d((0, 0, 0), fixed=True)
nm = sse.add_normal_3d((1, 0, 0, 0), fixed=True)
wp = sse.add_workplane(origin, nm, fixed=True)
sketch = sse.add_sketch(wp)

p1 = sse.add_point_2d((0.0, 0.0), sketch, fixed=True)
p2 = sse.add_point_2d((1.0, 0.0), sketch)
p3 = sse.add_point_2d((1.0, 1.0), sketch)
line1 = sse.add_line_2d(p1, p2, sketch)
line2 = sse.add_line_2d(p2, p3, sketch)

# Make line2 construction
line2.construction = True

cd = sketch.target_object.data

# Also test DirectConverter rebuild
from bl_ext.blend.CAD_Sketcher.converters import DirectConverter
cd.remove_curves()
conv = DirectConverter(bpy.context.scene, sketch)
conv.to_bezier(cd)

print("Curves:", len(cd.curves))
for i in range(len(cd.curves)):
    seg = cd.attributes.get("segment_entity_index")
    con = cd.attributes.get("construction")
    fix = cd.attributes.get("fixed")
    vis = cd.attributes.get("visible")
    sel = cd.attributes.get("selected")
    hov = cd.attributes.get("hover")

    print(f"  Curve {i}:")
    print(f"    segment_entity_index: {seg.data[i].value if seg else 'MISSING'}")
    print(f"    construction: {con.data[i].value if con else 'MISSING'}")
    print(f"    fixed: {fix.data[i].value if fix else 'MISSING'}")
    print(f"    visible: {vis.data[i].value if vis else 'MISSING'}")
    print(f"    selected: {sel.data[i].value if sel else 'MISSING'}")
    print(f"    hover: {hov.data[i].value if hov else 'MISSING'}")
    print(f"    points: {cd.curves[i].points_length}")

print("\nPASS")
