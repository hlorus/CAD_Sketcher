"""Test tag methods one at a time."""
import bpy

cd = bpy.data.hair_curves.new("TagTest")
obj = bpy.data.objects.new("TagTestObj", cd)
bpy.context.scene.collection.objects.link(obj)
cd.add_curves([2])
cd.set_types(type="BEZIER")
cd.points[0].position = (0, 0, 0)
cd.points[1].position = (1, 0, 0)

# Check available methods on ID
print("update_tag methods:")
try:
    cd.update_tag()
    print("  cd.update_tag(): OK")
except Exception as e:
    print(f"  cd.update_tag(): {e}")

try:
    obj.update_tag()
    print("  obj.update_tag(): OK")
except Exception as e:
    print(f"  obj.update_tag(): {e}")

# Check if there's id_tag_update on bpy.data
print("\nbpy.data methods with 'tag':")
for attr in dir(bpy.data):
    if 'tag' in attr.lower():
        print(f"  bpy.data.{attr}")

# Check depsgraph
print("\ndepsgraph methods:")
dg = bpy.context.evaluated_depsgraph_get()
for attr in sorted(dir(dg)):
    if not attr.startswith('_'):
        print(f"  dg.{attr}")

# Try depsgraph.id_type_updated
print("\nid_type_updated check:")
try:
    result = dg.id_type_updated('CURVES')
    print(f"  id_type_updated('CURVES'): {result}")
except Exception as e:
    print(f"  Error: {e}")

bpy.data.objects.remove(obj)
bpy.data.hair_curves.remove(cd)
print("\nDONE")
