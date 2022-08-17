class GenericStateTool:
    """Base for WorkSpaceTools that expose a StatefulOperator"""

    @classmethod
    def bl_description(cls, context, item, keymap):

        # Get description from operator
        op_name = cls.bl_operator if hasattr(cls, "bl_operator") else ""
        if op_name:
            import _bpy
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

            rna_type = _bpy.ops.get_rna_type(op_name)
            return rna_type.description
        return cls.__doc__
