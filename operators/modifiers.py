import glob

import bpy
from bpy.types import Operator, Object, Context, MeshEdge, MeshPolygon
from bpy.props import FloatProperty, IntProperty, FloatVectorProperty
from mathutils import Vector

from .base_3d import Operator3d
from ..global_data import LIB_NAME
from ..declarations import Operators
from ..utilities.view import get_placement_pos
from ..stateful_operator.utilities.register import register_stateops_factory
from ..stateful_operator.state import state_from_args
from ..model.types import SlvsLine3D, SlvsLine2D, SlvsWorkplane


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

        group = getattr(bpy.data, "node_groups").get(asset)
        group.use_fake_user = True

        return True
    return False


BASE_STATES = (
    state_from_args(
        "Object",
        description="Base object to add the nodegroup",
        pointer="object",
        types=(Object,),
        use_create=False,
    ),
)


class NodeOperator(Operator3d):
    """Base class for all node-based operators"""

    bl_options = {"UNDO", "REGISTER"}

    resources = ()

    @classmethod
    def poll(cls, context):
        if not context.active_object:
            return False
        # if context.scene.sketcher.active_sketch_i != -1:
        #     return False
        return True

    def init(self, context, event):
        for rType, rName in self.resources:
            if not load_asset(LIB_NAME, rType, rName):
                self.report({"ERROR"}, f'Cannot load asset "{rName}" from library')
                return False

        bpy.ops.ed.undo_push(message=f'Load Asset "{rName}"')
        return True

    def main(self, context):
        ob = self.object.original

        # Add a modifier to object
        self.modifier = ob.modifiers.new(f"CAD_Sketcher {self.NODEGROUP_NAME}", "NODES")

        # Add nodegroup to modifier
        nodegroup = bpy.data.node_groups.get(self.NODEGROUP_NAME)
        if not nodegroup:
            self.report({"Error"}, f"Unable to load node group {self.NODEGROUP_NAME}")
        self.modifier.node_group = nodegroup

        retval = self.set_props()
        ob.update_tag()
        return retval

    def set_props(self):
        pass


class View3D_OT_node_fill(Operator, NodeOperator):
    """Add a fill modifier node group to the object"""

    bl_idname = Operators.NodeFill
    bl_label = "Fill Profile"

    resources = (
        ("node_groups", "Fill Mesh and Curve"),
    )

    states = BASE_STATES

    @property
    def NODEGROUP_NAME(self):
        return "Fill Mesh and Curve"


class View3D_OT_node_extrude(Operator, NodeOperator):
    """Add an extrude modifier node group"""

    bl_idname = Operators.NodeExtrude
    bl_label = "Extrude"

    resources = (("node_groups", "Extrude"),)
    NODEGROUP_NAME = "Extrude"

    offset: FloatProperty(name="Offset", subtype="DISTANCE", options={"SKIP_SAVE"})

    states = (
        *BASE_STATES,
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

    def set_props(self):
        # Set offset
        self.modifier["Input_2"] = self.offset

        return True


class View3D_OT_node_array_linear(Operator, NodeOperator):
    """Add a linear array of the selected element"""

    bl_idname = Operators.NodeArrayLinear
    bl_label = "Linear Array"

    NODEGROUP_NAME = "Linear Array"
    resources = (("node_groups", "Linear Array"),)

    direction: FloatVectorProperty(name="Direction", size=3)
    distance: FloatProperty(name="Distance")
    count: IntProperty(name="Count", default=2, min=2)

    states = (
        *BASE_STATES,
        state_from_args(
            "Alignment",
            description="Direction of the linear array",
            pointer="alignment",
            types=(SlvsLine2D, SlvsLine3D, SlvsWorkplane, MeshEdge, MeshPolygon),
            use_create=False,
        ),
        state_from_args(
            "Distance",
            description="Distance between individual elements",
            property="distance",
            interactive=True,
        ),
        state_from_args(
            "Count",
            description="Amount of created elements",
            property="count",
            interactive=True,
            optional=True,
            state_func="get_count",
        ),
    )


    def get_count(self, context: Context, coords):
        retval = super().state_func(context, coords)
        return abs(retval) + 2


    def set_props(self):

        # Direction
        if not self.properties.is_property_set("direction"):
            # Note: Only update direction from alignment once, otherwise the direction
            # property is overwritten when changed from the redo panel

            if isinstance(self.alignment, (MeshPolygon, SlvsWorkplane)):
                self.direction = self.alignment.normal
            if isinstance(self.alignment, MeshEdge):
                ob_name = self.get_state_data(0)["object_name"]
                ob = bpy.data.objects[ob_name]
                mat = ob.matrix_world.inverted()
                verts = [mat @ ob.data.vertices[i].co for i in self.alignment.vertices]
                self.direction = (verts[1] - verts[0]).normalized()

            if isinstance(self.alignment, (SlvsLine3D, SlvsLine2D)):
                self.direction = self.alignment.orientation()

        self.modifier["Input_21"][:] = self.direction

        # Distance
        self.modifier["Input_23"] = self.distance

        # Count
        self.modifier["Input_22"] = self.count

        return True

    def draw_settings(self, context):
        layout = self.layout

        # Add the direction property which is not displayed as part of the states
        layout.prop(self, "direction")



register, unregister = register_stateops_factory(
    (View3D_OT_node_extrude, View3D_OT_node_fill, View3D_OT_node_array_linear)
)
