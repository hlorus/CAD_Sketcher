import bpy
print(f"Addon loaded: {hasattr(bpy.context.scene, 'sketcher')}")
print(f"Entities: {bpy.context.scene.sketcher.entities}")
