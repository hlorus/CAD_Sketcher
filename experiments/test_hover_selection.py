"""Test the full hover/selection data flow without GPU rendering.

Validates: global_data state → sync_curve_selection → curve attributes → color resolution
"""
import bpy

sse = bpy.context.scene.sketcher.entities
from bl_ext.blend.CAD_Sketcher import global_data
from bl_ext.blend.CAD_Sketcher.converters import sync_curve_selection
from bl_ext.blend.CAD_Sketcher.draw_handler import _get_line_color
from bl_ext.blend.CAD_Sketcher.utilities.preferences import get_prefs

print("=" * 60)
print("HOVER / SELECTION DATA FLOW TEST")
print("=" * 60)

# Setup
origin = sse.add_point_3d((0, 0, 0), fixed=True)
nm = sse.add_normal_3d((1, 0, 0, 0), fixed=True)
wp = sse.add_workplane(origin, nm, fixed=True)
sketch = sse.add_sketch(wp)

p1 = sse.add_point_2d((0.0, 0.0), sketch, fixed=True)
p2 = sse.add_point_2d((1.0, 0.0), sketch)
p3 = sse.add_point_2d((1.0, 1.0), sketch)
line1 = sse.add_line_2d(p1, p2, sketch)
line2 = sse.add_line_2d(p2, p3, sketch)

cd = sketch.target_object.data
ts = get_prefs().theme_settings.entity

def get_attrs():
    sel = cd.attributes.get("selected")
    hov = cd.attributes.get("hover")
    return (
        [sel.data[i].value for i in range(len(sel.data))],
        [hov.data[i].value for i in range(len(hov.data))],
    )

def color_name(col):
    """Match color tuple to theme setting name."""
    for name in ("default", "selected", "selected_highlight", "highlight", "fixed"):
        if tuple(getattr(ts, name)) == tuple(col):
            return name
    return f"unknown{tuple(col)}"

# --- Test 1: Default state ---
print("\n--- Test 1: Default state ---")
global_data.selected.clear()
global_data.hover = -1
sync_curve_selection(bpy.context.scene)
sel, hov = get_attrs()
print(f"  selected: {sel}, hover: {hov}")
c0 = _get_line_color(bpy.context, False, sel[0], hov[0], False)
c1 = _get_line_color(bpy.context, False, sel[1], hov[1], False)
print(f"  line1 color: {color_name(c0)}")
print(f"  line2 color: {color_name(c1)}")
assert color_name(c0) == "default"
assert color_name(c1) == "default"
print("  PASS")

# --- Test 2: Hover line1 ---
print("\n--- Test 2: Hover line1 ---")
global_data.hover = line1.slvs_index
sync_curve_selection(bpy.context.scene)
sel, hov = get_attrs()
print(f"  selected: {sel}, hover: {hov}")
c0 = _get_line_color(bpy.context, False, sel[0], hov[0], False)
c1 = _get_line_color(bpy.context, False, sel[1], hov[1], False)
print(f"  line1 color: {color_name(c0)}")
print(f"  line2 color: {color_name(c1)}")
assert color_name(c0) == "highlight"
assert color_name(c1) == "default"
print("  PASS")

# --- Test 3: Select line1, unhover ---
print("\n--- Test 3: Select line1 ---")
global_data.selected.append(line1.slvs_index)
global_data.hover = -1
sync_curve_selection(bpy.context.scene)
sel, hov = get_attrs()
print(f"  selected: {sel}, hover: {hov}")
c0 = _get_line_color(bpy.context, False, sel[0], hov[0], False)
c1 = _get_line_color(bpy.context, False, sel[1], hov[1], False)
print(f"  line1 color: {color_name(c0)}")
print(f"  line2 color: {color_name(c1)}")
assert color_name(c0) == "selected"
assert color_name(c1) == "default"
print("  PASS")

# --- Test 4: Select line1 + hover line1 ---
print("\n--- Test 4: Select + hover line1 ---")
global_data.hover = line1.slvs_index
sync_curve_selection(bpy.context.scene)
sel, hov = get_attrs()
c0 = _get_line_color(bpy.context, False, sel[0], hov[0], False)
print(f"  line1 color: {color_name(c0)}")
assert color_name(c0) == "selected_highlight"
print("  PASS")

# --- Test 5: Select line1 + hover line2 ---
print("\n--- Test 5: Select line1, hover line2 ---")
global_data.hover = line2.slvs_index
sync_curve_selection(bpy.context.scene)
sel, hov = get_attrs()
c0 = _get_line_color(bpy.context, False, sel[0], hov[0], False)
c1 = _get_line_color(bpy.context, False, sel[1], hov[1], False)
print(f"  line1 color: {color_name(c0)}")
print(f"  line2 color: {color_name(c1)}")
assert color_name(c0) == "selected"
assert color_name(c1) == "highlight"
print("  PASS")

# --- Test 6: Fixed line ---
print("\n--- Test 6: Fixed line ---")
global_data.selected.clear()
global_data.hover = -1
fix_attr = cd.attributes.get("fixed")
fix_attr.data[0].value = True
sync_curve_selection(bpy.context.scene)
sel, hov = get_attrs()
c0 = _get_line_color(bpy.context, False, sel[0], hov[0], True)
print(f"  line1 color: {color_name(c0)}")
assert color_name(c0) == "fixed"
fix_attr.data[0].value = False
print("  PASS")

# --- Test 7: Construction line ---
print("\n--- Test 7: Construction line ---")
c0 = _get_line_color(bpy.context, True, False, False, False)
print(f"  construction color: {color_name(c0)}")
assert color_name(c0) == "default"  # construction affects style (dashed), not color
print("  PASS (construction affects dash style, not color)")

# --- Test 8: Multiple selection (SET/ADD) ---
print("\n--- Test 8: Both lines selected ---")
global_data.selected.clear()
global_data.selected.append(line1.slvs_index)
global_data.selected.append(line2.slvs_index)
global_data.hover = -1
sync_curve_selection(bpy.context.scene)
sel, hov = get_attrs()
print(f"  selected: {sel}, hover: {hov}")
c0 = _get_line_color(bpy.context, False, sel[0], hov[0], False)
c1 = _get_line_color(bpy.context, False, sel[1], hov[1], False)
print(f"  line1 color: {color_name(c0)}")
print(f"  line2 color: {color_name(c1)}")
assert color_name(c0) == "selected"
assert color_name(c1) == "selected"
print("  PASS")

# --- Test 9: Deselect one (SUBTRACT) ---
print("\n--- Test 9: Deselect line1 (subtract) ---")
global_data.selected.remove(line1.slvs_index)
sync_curve_selection(bpy.context.scene)
sel, hov = get_attrs()
print(f"  selected: {sel}")
c0 = _get_line_color(bpy.context, False, sel[0], hov[0], False)
c1 = _get_line_color(bpy.context, False, sel[1], hov[1], False)
print(f"  line1 color: {color_name(c0)}")
print(f"  line2 color: {color_name(c1)}")
assert color_name(c0) == "default"
assert color_name(c1) == "selected"
print("  PASS")

print("\n" + "=" * 60)
print("ALL HOVER/SELECTION TESTS PASS")
print("=" * 60)
