"""Test selection/hover sync to curve attributes."""
import bpy

sse = bpy.context.scene.sketcher.entities
from bl_ext.blend.CAD_Sketcher import global_data
from bl_ext.blend.CAD_Sketcher.converters import sync_curve_selection

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

cd = sketch.target_object.data
print(f"line1.slvs_index = {line1.slvs_index}")
print(f"line2.slvs_index = {line2.slvs_index}")

# Test 1: No selection
sync_curve_selection(bpy.context.scene)
sel = cd.attributes.get("selected")
hov = cd.attributes.get("hover")
print(f"\n--- No selection ---")
print(f"  selected: {[sel.data[i].value for i in range(len(sel.data))]}")
print(f"  hover: {[hov.data[i].value for i in range(len(hov.data))]}")

# Test 2: Select line1
global_data.selected.append(line1.slvs_index)
sync_curve_selection(bpy.context.scene)
print(f"\n--- line1 selected ---")
print(f"  selected: {[sel.data[i].value for i in range(len(sel.data))]}")

# Test 3: Also hover line2
global_data.hover = line2.slvs_index
sync_curve_selection(bpy.context.scene)
print(f"\n--- line1 selected, line2 hovered ---")
print(f"  selected: {[sel.data[i].value for i in range(len(sel.data))]}")
print(f"  hover: {[hov.data[i].value for i in range(len(hov.data))]}")

# Test 4: Deselect all
global_data.selected.clear()
global_data.hover = -1
sync_curve_selection(bpy.context.scene)
print(f"\n--- All cleared ---")
print(f"  selected: {[sel.data[i].value for i in range(len(sel.data))]}")
print(f"  hover: {[hov.data[i].value for i in range(len(hov.data))]}")

print("\nPASS")
