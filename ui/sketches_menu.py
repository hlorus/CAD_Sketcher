from bpy.types import Menu, Context

from ..declarations import Menus, Operators


class VIEW3D_MT_sketches(Menu):
    bl_label = "Sketches"
    bl_idname = Menus.Sketches

    def draw(self, context: Context):
        layout = self.layout
        sse = context.scene.sketcher.entities
        layout.operator(Operators.AddSketch).wait_for_input = True

        if len(sse.sketches):
            layout.separator()

        for i, sk in enumerate(sse.sketches):
            layout.operator(
                Operators.SetActiveSketch, text=sk.name
            ).index = sk.slvs_index
