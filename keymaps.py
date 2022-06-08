import bpy


addon_keymaps = []

def register():
    wm = bpy.context.window_manager
    if wm.keyconfigs.addon:
        km = wm.keyconfigs.addon.keymaps.new(name='Object Mode', space_type='EMPTY')

        # Select
        kmi = km.keymap_items.new('wm.tool_set_by_id', 'ESC', 'PRESS', shift=True)
        kmi.properties.name = "sketcher.slvs_select"
        addon_keymaps.append((km, kmi))

        # Add Sketch
        kmi = km.keymap_items.new('view3d.slvs_add_sketch', 'A', 'PRESS', ctrl=True, shift=True)
        kmi.properties.wait_for_input = True
        addon_keymaps.append((km, kmi))

def unregister():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        for km, kmi in addon_keymaps:
            km.keymap_items.remove(kmi)
            addon_keymaps.clear()
