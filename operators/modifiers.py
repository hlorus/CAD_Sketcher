
import bpy
from bpy.types import Operator, Object, Context, MeshEdge, MeshPolygon
from bpy.props import FloatProperty, IntProperty, FloatVectorProperty
from mathutils import Vector

from .base_3d import Operator3d
from ..assets_manager import load_asset
from ..global_data import LIB_NAME
from ..declarations import Operators
from ..utilities.view import get_placement_pos
from ..stateful_operator.utilities.register import register_stateops_factory
from ..stateful_operator.state import state_from_args


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
        return True

    def _check_constrain(self, context, index):
        return False

    def init(self, context, event):
        for rType, rName in self.resources:
            if not load_asset(LIB_NAME, rType, rName):
                self.report({"ERROR"}, f'Cannot load asset "{rName}" from library')
                return False

        bpy.ops.ed.undo_push(message=f'Load Asset "{rName}"')
        return True

    def _ensure_modifier(self, context):
        """Create the modifier once, reuse on subsequent calls."""
        ob = self.object.original
        mod_name = f"CAD_Sketcher {self.bl_label}"

        self.modifier = ob.modifiers.get(mod_name)
        if self.modifier:
            return True

        self.modifier = ob.modifiers.new(mod_name, "NODES")
        nodegroup = bpy.data.node_groups.get(self.NODEGROUP_NAME)
        if not nodegroup:
            self.report({"Error"}, f"Unable to load node group {self.NODEGROUP_NAME}")
            return False
        self.modifier.node_group = nodegroup
        return True

    def main(self, context):
        if not self._ensure_modifier(context):
            return False

        retval = self.set_props()
        self.object.original.update_tag()
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

    resources = (("node_groups", "CAD Sketcher Extrude"),)
    NODEGROUP_NAME = "CAD Sketcher Extrude"

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

    NODEGROUP_NAME = "CAD Sketcher Linear Array"
    resources = (("node_groups", "CAD Sketcher Linear Array"),)

    direction: FloatVectorProperty(name="Direction", size=3)
    distance: FloatProperty(name="Distance")
    count: IntProperty(name="Count", default=2, min=2)

    states = (
        *BASE_STATES,
        state_from_args(
            "Alignment",
            description="Direction of the linear array",
            pointer="alignment",
            types=(Object, MeshEdge, MeshPolygon),
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

    def gather_selection(self, context):
        selected = list(context.selected_objects)
        selected.sort(key=lambda o: o.type == 'EMPTY')
        return selected

    def get_count(self, context: Context, coords):
        retval = super().state_func(context, coords)
        return abs(retval) + 2

    def set_props(self):

        # Direction
        if not self.properties.is_property_set("direction"):
            if isinstance(self.alignment, MeshPolygon):
                self.direction = self.alignment.normal
            elif isinstance(self.alignment, MeshEdge):
                ob_name = self.get_state_data(0)["object_name"]
                ob = bpy.data.objects[ob_name]
                mat = ob.matrix_world.inverted()
                verts = [mat @ ob.data.vertices[i].co for i in self.alignment.vertices]
                self.direction = (verts[1] - verts[0]).normalized()
            elif isinstance(self.alignment, Object) and self.alignment.type == 'EMPTY':
                self.direction = self.alignment.matrix_world.to_3x3().col[2].normalized()

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
    (View3D_OT_node_extrude, View3D_OT_node_array_linear)
)
