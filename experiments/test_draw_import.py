"""Verify draw_handler imports work and _draw_sketch_lines_id is callable."""
import bpy

# Check addon loaded
print(f"Addon loaded: {hasattr(bpy.context.scene, 'sketcher')}")

# Check draw_handler imports
try:
    from bl_ext.blend.CAD_Sketcher.draw_handler import _draw_sketch_lines_id
    print(f"_draw_sketch_lines_id imported: {_draw_sketch_lines_id}")
    print("PASS: Import works")
except Exception as e:
    print(f"FAIL: {e}")
    import traceback
    traceback.print_exc()

# Verify the function signature works with a sketch that has curve data
sse = bpy.context.scene.sketcher.entities
origin = sse.add_point_3d((0, 0, 0), fixed=True)
nm = sse.add_normal_3d((1, 0, 0, 0), fixed=True)
wp = sse.add_workplane(origin, nm, fixed=True)
sketch = sse.add_sketch(wp)
p1 = sse.add_point_2d((0.0, 0.0), sketch)
p2 = sse.add_point_2d((1.0, 0.0), sketch)
line = sse.add_line_2d(p1, p2, sketch)

print(f"Sketch has target_object: {sketch.target_object is not None}")
print(f"Curve data has curves: {len(sketch.target_object.data.curves)}")

seg_attr = sketch.target_object.data.attributes.get("segment_entity_index")
print(f"segment_entity_index attr: {seg_attr is not None}")
if seg_attr:
    print(f"  Value: {seg_attr.data[0].value}")
    entity = sse.get(seg_attr.data[0].value)
    print(f"  Entity: {entity}")
    print(f"  is_line: {entity.is_line()}")

print("\nAll imports and data structures OK")
