"""Check available update methods on Curves and Object."""
import bpy

curve_data = bpy.data.hair_curves.new("APITest")
obj = bpy.data.objects.new("APITestObj", curve_data)

# Check update_tag signature
print("=== ID.update_tag ===")
print(bpy.types.ID.update_tag.__doc__)

print("\n=== Object.update_tag ===")
print(obj.update_tag.__doc__)

print("\n=== Curves methods with 'update' or 'tag' ===")
for attr in dir(curve_data):
    if 'update' in attr.lower() or 'tag' in attr.lower():
        print(f"  {attr}")

print("\n=== Object methods with 'update' or 'tag' ===")
for attr in dir(obj):
    if 'update' in attr.lower() or 'tag' in attr.lower():
        print(f"  {attr}")

print("\n=== depsgraph methods ===")
dg = bpy.context.evaluated_depsgraph_get()
for attr in dir(dg):
    if not attr.startswith('_') and ('update' in attr.lower() or 'tag' in attr.lower()):
        print(f"  {attr}: {getattr(dg, attr).__doc__[:100] if hasattr(getattr(dg, attr), '__doc__') and getattr(dg, attr).__doc__ else ''}")

print("\n=== view_layer methods ===")
vl = bpy.context.view_layer
for attr in dir(vl):
    if not attr.startswith('_') and 'update' in attr.lower():
        print(f"  {attr}")

bpy.data.objects.remove(obj)
bpy.data.hair_curves.remove(curve_data)
