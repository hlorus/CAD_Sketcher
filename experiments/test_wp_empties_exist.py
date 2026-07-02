"""Check if origin workplane empties exist and are set up correctly."""
import bpy
from bl_ext.blend.CAD_Sketcher.converters import (
    ensure_origin_workplane_empties, WP_ID_XY, WP_ID_XZ, WP_ID_YZ, WP_ID_MAP,
)

ensure_origin_workplane_empties(bpy.context)

sketcher = bpy.context.scene.sketcher
print(f"show_origin: {sketcher.show_origin}")
print(f"wp_xy: {sketcher.wp_xy}")
print(f"wp_xz: {sketcher.wp_xz}")
print(f"wp_yz: {sketcher.wp_yz}")
print(f"\nWP_ID_MAP: {WP_ID_MAP}")
print(f"WP_ID_XY: {hex(WP_ID_XY)}")
print(f"WP_ID_XZ: {hex(WP_ID_XZ)}")
print(f"WP_ID_YZ: {hex(WP_ID_YZ)}")

for name, obj in [("XY", sketcher.wp_xy), ("XZ", sketcher.wp_xz), ("YZ", sketcher.wp_yz)]:
    if obj:
        print(f"\n{name}: {obj.name}")
        print(f"  matrix_world: {obj.matrix_world}")
        print(f"  location: {tuple(obj.matrix_world.translation)}")
        print(f"  in scene: {obj.name in bpy.context.scene.collection.objects}")

# Check if IDs fit in 24 bits (RGB encoding)
from bl_ext.blend.CAD_Sketcher.utilities.index import index_to_rgb, rgb_to_index
for wp_id in (WP_ID_XY, WP_ID_XZ, WP_ID_YZ):
    r, g, b = index_to_rgb(wp_id)
    back = rgb_to_index(r, g, b)
    print(f"\nWP_ID {hex(wp_id)}: RGB=({r:.4f},{g:.4f},{b:.4f}) → back={hex(back)} match={back==wp_id}")
