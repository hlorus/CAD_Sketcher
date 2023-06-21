import glob

import bpy
from bpy.types import Operator, Object, Context
from bpy.props import FloatProperty
from mathutils import Vector

from .base_3d import Operator3d
from ..declarations import Operators
from ..utilities.view import get_placement_pos
from ..stateful_operator.utilities.register import register_stateops_factory
from ..stateful_operator.state import state_from_args


def load_asset(library, asset_type, asset):
    """Loads an asset of given type from a specified library
    Returns True if it is loaded or already present in file"""

    # Check if the asset is already present in file
    if asset in [a.name for a in getattr(bpy.data, asset_type)]:
        return True

    prefs = bpy.context.preferences
    fp = prefs.filepaths.asset_libraries[library].path

    for file in glob.glob(fp + "/*.blend"):
        with bpy.data.libraries.load(file, assets_only=True) as (data_from, data_to):
            coll = getattr(data_from, asset_type)
            if not asset in coll:
                continue
            getattr(data_to, asset_type).append(asset)

        group = bpy.data.node_groups.get("Extrude")
        group.use_fake_user = True

        return True
    return False


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
            use_create=False,
        ),
        state_from_args(
            "Offset",
            description="Offset vector to apply to the selection of entities",
            property="offset",
            state_func="get_offset",
            interactive=True,
        ),
    )

    NODEGROUP_NAME = "Extrude"

    def get_offset(self, context: Context, coords):
        pos = get_placement_pos(context, coords)
        if pos is None:
            return 0.0

        mat = self.object.original.matrix_world.inverted()
        delta = (mat @ Vector(pos)).z
        return delta

    # Somhow doesn't seem to work, might be an undo problem
    def init(self, context, event):
        if not load_asset("resources", "node_groups", "Extrude"):
            self.report({"ERROR"}, f"Cannot load asset \"{self.NODEGROUP_NAME}\" from library")
            return False

        bpy.ops.ed.undo_push(message=f"Load Asset \"{self.NODEGROUP_NAME}\"")
        return True

    def main(self, context):
        ob = self.object.original
        offset = self.offset
        
        # Add a modifier to object
        modifier = ob.modifiers.new("CAD_Sketcher Extrude", "NODES")

        # Add nodegroup to modifier
        nodegroup = bpy.data.node_groups.get(self.NODEGROUP_NAME)
        modifier.node_group = nodegroup

        # Set offset
        modifier["Input_2"] = offset
        ob.update_tag()

        return True


register, unregister = register_stateops_factory((View3D_OT_node_extrude,))
