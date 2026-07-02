"""Test which method actually makes GN modifier re-evaluate visually.

Run INTERACTIVELY in Blender (paste in text editor), not headless.
Creates a curve with GN modifier, then tries different update methods.
Watch if the viewport mesh changes position.
"""
import bpy
import numpy as np
from bl_ext.blend.CAD_Sketcher.assets_manager import load_asset
from bl_ext.blend.CAD_Sketcher import global_data

# Setup
curve_data = bpy.data.hair_curves.new("RefreshTest")
obj = bpy.data.objects.new("RefreshTestObj", curve_data)
bpy.context.scene.collection.objects.link(obj)

curve_data.add_curves([2])
curve_data.set_types(type="BEZIER")
curve_data.points[0].position = (0.0, 0.0, 0.0)
curve_data.points[1].position = (1.0, 0.0, 0.0)

# Add the CAD Sketcher Convert modifier
mod = obj.modifiers.new("CAD Sketcher Convert", "NODES")
load_asset(global_data.LIB_NAME, "node_groups", "CAD Sketcher Convert")
mod.node_group = bpy.data.node_groups["CAD Sketcher Convert"]

# Ensure initial eval
bpy.context.view_layer.update()

print("Initial setup done. Point 1 at (1, 0, 0)")
print("Now run each test block one at a time and check viewport:\n")

# === TEST A: per-point assignment + tags ===
def test_a():
    curve_data.points[1].position = (3.0, 0.0, 0.0)
    curve_data.update_tag()
    obj.update_tag()
    print("Test A: per-point + update_tag. Check viewport.")

# === TEST B: foreach_set on points ===
def test_b():
    pos = np.array([0, 0, 0, 5, 0, 0], dtype=np.float32)
    curve_data.points.foreach_set("position", pos)
    curve_data.update_tag()
    obj.update_tag()
    print("Test B: foreach_set on points. Check viewport.")

# === TEST C: foreach_set on attribute ===
def test_c():
    pos_attr = curve_data.attributes.get("position")
    if pos_attr:
        pos = np.array([0, 0, 0, 7, 0, 0], dtype=np.float32)
        pos_attr.data.foreach_set("vector", pos)
    curve_data.update_tag()
    obj.update_tag()
    print("Test C: foreach_set on position attribute. Check viewport.")

# === TEST D: remove + re-add curves ===
def test_d():
    # Save point counts
    counts = [curve_data.curves[i].points_length for i in range(len(curve_data.curves))]
    curve_data.remove_curves()
    curve_data.add_curves(counts)
    curve_data.set_types(type="BEZIER")
    curve_data.points[0].position = (0.0, 0.0, 0.0)
    curve_data.points[1].position = (9.0, 0.0, 0.0)
    print("Test D: remove + re-add. Check viewport.")

# === TEST E: view_layer.update ===
def test_e():
    curve_data.points[1].position = (4.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    print("Test E: view_layer.update(). Check viewport.")

# Run tests - uncomment one at a time
test_a()
#test_b()
#test_c()
#test_d()
#test_e()
