"""Test depsgraph.debug_tag_update."""
import bpy

cd = bpy.data.hair_curves.new("TagTest")
obj = bpy.data.objects.new("TagTestObj", cd)
bpy.context.scene.collection.objects.link(obj)
cd.add_curves([2])
cd.set_types(type="BEZIER")
cd.points[0].position = (0, 0, 0)
cd.points[1].position = (1, 0, 0)

dg = bpy.context.evaluated_depsgraph_get()
dg.update()

# Move point
cd.points[1].position = (2, 0, 0)

print("debug_tag_update doc:", dg.debug_tag_update.__doc__)

# Try it
try:
    dg.debug_tag_update()
    print("debug_tag_update(): OK")
except Exception as e:
    print(f"debug_tag_update(): {e}")

# Check if evaluated data sees the change
dg.update()
eval_obj = obj.evaluated_get(dg)
eval_cd = eval_obj.data
print(f"Eval point 1: {tuple(eval_cd.points[1].position)}")

bpy.data.objects.remove(obj)
bpy.data.hair_curves.remove(cd)
