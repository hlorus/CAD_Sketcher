import bpy
from bpy.types import Operator, Object, Context
from bpy.props import FloatProperty
from mathutils import Vector

from .base_3d import Operator3d
from ..declarations import Operators
from ..utilities.view import get_placement_pos
from ..stateful_operator.utilities.register import register_stateops_factory
from ..stateful_operator.state import state_from_args


class View3D_OT_node_extrude(Operator, Operator3d):
    """Add an extrude modifier node group"""

    bl_idname = Operators.NodeExtrude
    bl_label = "Extrude"
    bl_options = {"UNDO", "REGISTER"}

    offset: FloatProperty(name="Offset", subtype="DISTANCE", options={"SKIP_SAVE"})

    states = (
        state_from_args(
            "Profile",
            description="Profile to extrude",
            pointer="object",
            types=(Object,),
            use_create=False,  # Should be the default, No?
        ),
        state_from_args(
            "Offset",
            description="Offset vector to apply to the selection of entities",
            property="offset",
            state_func="get_offset",
            interactive=True,
        ),
    )

    def get_offset(self, context: Context, coords):
        pos = get_placement_pos(context, coords)
        if pos is None:
            return 0.0

        mat = self.object.original.matrix_world.inverted()
        delta = (mat @ Vector(pos)).z
        return delta

    def main(self, context):
        ob = self.object.original
        offset = self.offset

        # Add a modifier to object
        mod = ob.modifiers.new("CADSketcher Extrude", "NODES")

        # Get node group from asset library
        path_resources = (
            context.preferences.filepaths.asset_libraries["resources"].path
            + "/assets.blend"
        )
        with bpy.data.libraries.load(str(path_resources), assets_only=True) as (
            data_from,
            data_to,
        ):
            data_to.node_groups.append("Extrude")

        # Add nodegroup to modifier
        group = bpy.data.node_groups.get("Extrude")
        mod.node_group = group

        # Set offset
        mod["Input_2"] = offset
        ob.update_tag()

        return True


register, unregister = register_stateops_factory((View3D_OT_node_extrude,))
