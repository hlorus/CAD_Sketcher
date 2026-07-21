
import bpy
from bpy.types import Operator, Object, Context, MeshEdge, MeshPolygon
from bpy.props import BoolProperty, FloatProperty, IntProperty, FloatVectorProperty
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


def is_2d_profile(obj):
    """A sketch or curve object — a valid 2D profile to extrude (not a 3D mesh)."""
    return obj is not None and obj.type in {"CURVE", "CURVES"}


class NodeOperator(Operator3d):
    """Base class for all node-based operators"""

    bl_options = {"UNDO", "REGISTER"}

    resources = ()

    # Message shown when the resolved target fails is_valid_target().
    invalid_target_msg = "Invalid target object"

    @classmethod
    def poll(cls, context):
        if not context.active_object:
            return False
        return True

    def is_valid_target(self, obj):
        """Whether ``obj`` may receive this node modifier. Override to restrict."""
        return obj is not None

    def gather_selection(self, context):
        # Source for the framework's prefill-from-selection: the base Object
        # state is filled from this list on invoke (wait_for_input paths). Put
        # the active object first and drop invalid targets so, e.g., a mesh is
        # never prefilled for a tool that only accepts sketches.
        active = context.active_object
        result = [active] if active and self.is_valid_target(active) else []
        result.extend(
            o for o in context.selected_objects
            if o != active and self.is_valid_target(o)
        )
        return result

    def _check_constrain(self, context, index):
        return False

    def invoke(self, context, event):
        # Follow the stateful prefill-from-selection flow: if nothing valid is
        # selected to prefill the base Object state, cancel instead of dropping
        # into an object-pick (a sketch/curve isn't reliably pickable in the
        # viewport). gather_selection already filters to valid targets.
        if self.wait_for_input and not self.gather_selection(context):
            self.report({"WARNING"}, self.invalid_target_msg)
            return {"CANCELLED"}
        return super().invoke(context, event)

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
        if not self.is_valid_target(self.object):
            self.report({"WARNING"}, self.invalid_target_msg)
            return False

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

    invalid_target_msg = "Select a sketch or curve to extrude (2D profile)"

    def is_valid_target(self, obj):
        return is_2d_profile(obj)

    offset: FloatProperty(name="Offset", subtype="DISTANCE", options={"SKIP_SAVE"})
    mirror: BoolProperty(name="Mirror Extrude")
    asymmetry: BoolProperty(name="Asymmetric")
    asymmetry_distance: FloatProperty(name="Asymmetry Distance", subtype="DISTANCE")

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
        m = self.modifier
        m["Input_2"] = self.offset               # Size
        m["Input_3"] = self.mirror               # Mirror Extrude
        m["Input_4"] = self.asymmetry            # Asymmetry Override
        m["Input_5"] = self.asymmetry_distance   # Asymmetry Distance
        return True

    def draw_settings(self, context):
        layout = self.layout
        layout.prop(self, "mirror")
        layout.prop(self, "asymmetry")
        sub = layout.column()
        sub.enabled = self.asymmetry
        sub.prop(self, "asymmetry_distance")


class View3D_OT_node_array_linear(Operator, NodeOperator):
    """Add a linear array of the selected element"""

    bl_idname = Operators.NodeArrayLinear
    bl_label = "Linear Array"

    NODEGROUP_NAME = "CAD Sketcher Linear Array"
    resources = (("node_groups", "CAD Sketcher Linear Array"),)

    direction: FloatVectorProperty(name="Direction", size=3)
    distance: FloatProperty(name="Distance")
    count: IntProperty(name="Count", default=2, min=2)
    flip: BoolProperty(name="Flip Direction")
    use_total_distance: BoolProperty(
        name="Use Total Distance",
        description="Treat distance as the total span rather than per-item spacing",
    )
    align_rotation: BoolProperty(name="Align Rotation")
    merge: BoolProperty(name="Merge by Distance")
    merge_distance: FloatProperty(
        name="Merge Distance", default=0.001, min=0.0, subtype="DISTANCE"
    )

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
        # Active object is the array base; any other selected object feeds the
        # Alignment state (empties last so a mesh wins the base if both picked).
        active = context.active_object
        others = [o for o in context.selected_objects if o != active]
        others.sort(key=lambda o: o.type == 'EMPTY')
        return ([active] if active else []) + others

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

        m = self.modifier
        m["Input_21"][:] = self.direction        # Direction
        m["Input_22"] = self.count               # Count
        m["Input_23"] = self.distance            # Spacing / Total distance
        m["Input_24"] = self.use_total_distance  # Use Total Distance
        m["Input_25"] = self.align_rotation      # Align Rotation
        m["Input_26"] = self.merge               # Merge by Distance
        m["Input_29"] = self.merge_distance      # Merge Distance
        m["Input_30"] = self.flip                # Flip Direction
        return True

    def draw_settings(self, context):
        layout = self.layout

        # Direction is resolved from the alignment pick, not a state property.
        layout.prop(self, "direction")
        layout.prop(self, "flip")
        layout.prop(self, "use_total_distance")
        layout.prop(self, "align_rotation")
        layout.prop(self, "merge")
        sub = layout.column()
        sub.enabled = self.merge
        sub.prop(self, "merge_distance")



register, unregister = register_stateops_factory(
    (View3D_OT_node_extrude, View3D_OT_node_array_linear)
)
