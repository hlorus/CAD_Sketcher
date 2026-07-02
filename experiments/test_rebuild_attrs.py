"""Test if update_geometry (DirectConverter) sets segment_entity_index correctly."""
import bpy

sse = bpy.context.scene.sketcher.entities

# Setup
origin = sse.add_point_3d((0, 0, 0), fixed=True)
nm = sse.add_normal_3d((1, 0, 0, 0), fixed=True)
wp = sse.add_workplane(origin, nm, fixed=True)
sketch = sse.add_sketch(wp)

p1 = sse.add_point_2d((0.0, 0.0), sketch)
p2 = sse.add_point_2d((1.0, 0.0), sketch)
p3 = sse.add_point_2d((1.0, 1.0), sketch)
line1 = sse.add_line_2d(p1, p2, sketch)
line2 = sse.add_line_2d(p2, p3, sketch)

print(f"line1.slvs_index = {line1.slvs_index}")
print(f"line2.slvs_index = {line2.slvs_index}")

# Check incremental add results
cd = sketch.target_object.data
print(f"\n--- After incremental add ---")
print(f"Curves: {len(cd.curves)}")
seg = cd.attributes.get("segment_entity_index")
if seg:
    for i in range(len(seg.data)):
        print(f"  Curve {i}: segment_entity_index = {seg.data[i].value}")

ei = cd.attributes.get("entity_index")
if ei:
    for i in range(len(ei.data)):
        print(f"  Point {i}: entity_index = {ei.data[i].value}")

# Now simulate what update_geometry does (full rebuild)
from bl_ext.blend.CAD_Sketcher.converters import DirectConverter
cd.remove_curves()
conv = DirectConverter(bpy.context.scene, sketch)
conv.to_bezier(cd)

print(f"\n--- After DirectConverter rebuild ---")
print(f"Curves: {len(cd.curves)}")
seg = cd.attributes.get("segment_entity_index")
if seg:
    for i in range(len(seg.data)):
        print(f"  Curve {i}: segment_entity_index = {seg.data[i].value}")

ei = cd.attributes.get("entity_index")
if ei:
    for i in range(len(ei.data)):
        print(f"  Point {i}: entity_index = {ei.data[i].value}")

# Verify they match the actual entity indices
print(f"\n--- Verification ---")
if seg:
    for i in range(len(seg.data)):
        idx = seg.data[i].value
        entity = sse.get(idx)
        print(f"  Curve {i}: index={idx}, entity={entity}")
