"""Create an assembly: a group of parts with a transform of its own."""

from bpy.types import Context, Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..utilities.part import create_assembly, join_assembly, part_root_of


class View3D_OT_slvs_add_assembly(Operator):
    """Add an assembly, taking the selected parts into it."""

    bl_idname = Operators.AddAssembly
    bl_label = "Add Assembly"
    bl_description = "Group parts under an assembly that can be moved as a whole"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: Context):
        assembly = create_assembly(context)

        # Selected parts join it straight away; anything else can be dragged in
        # later, since membership is just parenting.
        roots = []
        for obj in context.selected_objects:
            root = part_root_of(obj)
            if root is not None and root not in roots:
                roots.append(root)
        for root in roots:
            join_assembly(assembly, root)

        from ..utilities.collections import sync_part_collections

        sync_part_collections(context.scene)
        self.report({"INFO"}, f"Assembly with {len(roots)} part(s)")
        return {"FINISHED"}


register, unregister = register_classes_factory((View3D_OT_slvs_add_assembly,))
