"""Test if tagging with GEOMETRY refresh type triggers GN re-eval."""
import bpy

cd = bpy.data.hair_curves.new("TagTest")
obj = bpy.data.objects.new("TagTestObj", cd)
bpy.context.scene.collection.objects.link(obj)

cd.add_curves([2])
cd.set_types(type="BEZIER")
cd.points[0].position = (0, 0, 0)
cd.points[1].position = (1, 0, 0)

# Check what update_tag accepts
print("=== ID.update_tag signature ===")
import inspect
try:
    sig = inspect.signature(cd.update_tag)
    print(f"  Signature: {sig}")
except:
    print("  Can't inspect")

# Try different tag approaches
print("\n=== Testing tag methods ===")

# Method 1: tag with refresh set
for refresh in [{'OBJECT'}, {'DATA'}, {'TIME'}, {'OBJECT', 'DATA'}, {'OBJECT', 'DATA', 'TIME'}]:
    try:
        cd.update_tag(refresh=refresh)
        print(f"  update_tag(refresh={refresh}): OK")
    except TypeError as e:
        print(f"  update_tag(refresh={refresh}): {e}")

# Method 2: tag_update on depsgraph
print("\n=== depsgraph.id_tag_update ===")
try:
    dg = bpy.context.evaluated_depsgraph_get()
    if hasattr(dg, 'id_tag_update'):
        print(f"  id_tag_update exists")
    for attr in dir(dg):
        if 'tag' in attr.lower() or 'update' in attr.lower():
            print(f"  dg.{attr}")
except Exception as e:
    print(f"  Error: {e}")

# Method 3: check if Curves has any geometry-specific update
print("\n=== Curves-specific methods ===")
for attr in dir(cd):
    if 'update' in attr.lower() or 'tag' in attr.lower() or 'notify' in attr.lower() or 'invalidate' in attr.lower():
        print(f"  cd.{attr}")

# Method 4: check bpy.msgbus
print("\n=== msgbus ===")
try:
    print(f"  bpy.msgbus: {dir(bpy.msgbus)}")
except:
    print("  No msgbus")

bpy.data.objects.remove(obj)
bpy.data.hair_curves.remove(cd)
