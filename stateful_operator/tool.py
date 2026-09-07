class GenericStateTool:
    """Base for WorkSpaceTools that expose a StatefulOperator"""

    @classmethod
    def bl_description(cls, context, item, keymap):

        # Get description from operator
        op_name = cls.bl_operator if hasattr(cls, "bl_operator") else ""
        if op_name:
            import bpy

            from .utilities.generic import get_subclasses

            func = None
            for op in get_subclasses():
                if not hasattr(op, "bl_idname"):
                    continue
                if op.bl_idname != op_name:
                    continue

                func = op.description
                break

            if func:
                return func(context, None)

            # Resolve the operator's RNA description through the public bpy.ops
            # API (bl_operator is a "category.name" string, so split and walk it)
            # rather than the private _bpy module, which extensions.blender.org
            # disallows.
            category, name = op_name.split(".")
            rna_type = getattr(getattr(bpy.ops, category), name).get_rna_type()
            return rna_type.description
        return cls.__doc__
