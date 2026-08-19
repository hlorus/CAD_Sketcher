import math

import bpy
from bpy.props import (
    BoolProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import Context, Event, MeshEdge, Object, Operator
from mathutils import Vector
from mathutils.geometry import intersect_line_line, intersect_line_plane

from ..assets_manager import load_asset
from ..declarations import BLENDER_SELECT_TOOL, Operators
from ..global_data import LIB_NAME
from ..stateful_operator.state import state_from_args
from ..stateful_operator.utilities.register import register_stateops_factory
from ..utilities.view import get_picking_origin_dir, get_placement_pos
from .base_3d import Operator3d


def set_modifier_input(modifier, identifier, value):
    """Set a Geometry-Nodes modifier input by socket identifier.

    Blender <= 5.1 stores modifier inputs as ID-properties on the modifier
    itself (``modifier["Input_2"] = value``). Blender 5.2 dropped ID-property
    support from the modifier and exposes inputs through an RNA interface at
    ``modifier.properties.inputs.<identifier>.value`` instead; the old access
    now raises "id properties not supported for this type". Note attribute
    access on ``.inputs`` returns the typed wrapper with a writable ``value``,
    whereas subscripting it returns the raw ID-property group (no ``value``).
    """
    props = getattr(modifier, "properties", None)
    if props is not None and hasattr(props, "inputs"):
        getattr(props.inputs, identifier).value = value  # Blender 5.2+
    else:
        modifier[identifier] = value  # Blender <= 5.1


def get_modifier_input(modifier, identifier):
    """Read a Geometry-Nodes modifier input by socket identifier.

    Version-aware counterpart to ``set_modifier_input`` (see it for the 5.1 vs
    5.2 access split).
    """
    props = getattr(modifier, "properties", None)
    if props is not None and hasattr(props, "inputs"):
        return getattr(props.inputs, identifier).value  # Blender 5.2+
    return modifier[identifier]  # Blender <= 5.1


# Boolean operations, in the node group's Index Switch order: the operator's
# enum name maps to this integer index (see set/get_boolean_operation).
BOOLEAN_OPERATIONS = ("Difference", "Union", "Intersect")


def set_boolean_operation(modifier, identifier, name):
    """Set the boolean Operation input (an integer index into BOOLEAN_OPERATIONS)."""
    set_modifier_input(modifier, identifier, BOOLEAN_OPERATIONS.index(name))


def get_boolean_operation(modifier, identifier):
    """Read the boolean Operation input back as its name."""
    index = int(get_modifier_input(modifier, identifier))
    if 0 <= index < len(BOOLEAN_OPERATIONS):
        return BOOLEAN_OPERATIONS[index]
    return BOOLEAN_OPERATIONS[0]


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

    # Persisted target so the redo panel (which re-runs execute() on a fresh
    # instance, losing the transient pointer state) can re-resolve the object
    # and edit the existing modifier instead of failing. Not SKIP_SAVE: it must
    # survive redo; main() overwrites it every run so a stale value is harmless.
    target_name: StringProperty(options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        # Available without a preselection: the state machine lets the user pick
        # the target object in the viewport. (Objects are ray-pickable; an open
        # profile a ray can't hit must still be selected first.)
        return True

    def state_property(self, state_index):
        # Native Object/MeshEdge pointer states have no editable fallback
        # property; don't advertise the "" placeholder GenericEntityOp returns
        # for non-entity pointers (it breaks the redo panel and redo_states).
        return None

    def resolved_object(self):
        """The object to operate on: the live pointer, else the persisted name.

        On the interactive path the base Object state resolves ``self.object``;
        on the redo path that pointer is gone, so fall back to ``target_name``.
        """
        ob = self.object
        if ob is None and self.target_name:
            ob = bpy.data.objects.get(self.target_name)
        return ob

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
            o
            for o in context.selected_objects
            if o != active and self.is_valid_target(o)
        )
        return result

    def _check_constrain(self, context, index):
        return False

    def read_props(self, modifier):
        """Seed operator properties from an existing modifier's inputs.

        Called on invoke when the target already carries this tool's modifier,
        so re-invoking edits from the current values instead of snapping back to
        the defaults. Override to pull the relevant sockets; base is a no-op.
        """
        pass

    def invoke(self, context, event):
        # With a valid preselection the base Object state prefills from it; with
        # nothing selected we fall through to the modal state machine so the user
        # can pick the target in the viewport instead of being blocked. The state
        # description guides the pick, and gather_selection filters to valid
        # targets so an invalid preselection is simply not prefilled.
        selection = self.gather_selection(context)

        # If the prefill target already carries this tool's modifier, seed the
        # operator from its current values. Convenience only -- never let a
        # readback mishap (e.g. a changed node group) block the tool.
        target = selection[0] if selection else None
        if isinstance(target, Object):
            mod = target.modifiers.get(f"CAD_Sketcher {self.bl_label}")
            if mod and mod.node_group:
                try:
                    self.read_props(mod)
                except Exception:
                    pass

        return super().invoke(context, event)

    def init(self, context, event):
        for rType, rName in self.resources:
            if not load_asset(LIB_NAME, rType, rName):
                self.report({"ERROR"}, f'Cannot load asset "{rName}" from library')
                return False

        bpy.ops.ed.undo_push(message=f'Load Asset "{rName}"')
        return True

    def _modifier_name(self):
        """Name of this tool's modifier on the target.

        One per object by default (re-invoking edits it). Tools that can stack
        several instances on one object (e.g. Boolean, one per cutter) override
        this to return a distinct name per instance.
        """
        return f"CAD_Sketcher {self.bl_label}"

    def _ensure_modifier(self, context):
        """Create the modifier once, reuse on subsequent calls."""
        ob = self._obj.original
        mod_name = self._modifier_name()

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
        ob = self.resolved_object()
        if not self.is_valid_target(ob):
            self.report({"WARNING"}, self.invalid_target_msg)
            return False

        # Persist the target and keep a resolved reference for this run so
        # _ensure_modifier / set_props work on both the interactive and redo
        # paths without going through the (redo-transient) pointer state.
        self.target_name = ob.name
        self._obj = ob

        if not self._ensure_modifier(context):
            return False

        retval = self.set_props()
        ob.original.update_tag()
        return retval

    def set_props(self):
        pass


class View3D_OT_node_fill(Operator, NodeOperator):
    """Add a fill modifier node group to the object"""

    bl_idname = Operators.NodeFill
    bl_label = "Fill Profile"

    resources = (("node_groups", "Fill Mesh and Curve"),)

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
    return_to_tool = BLENDER_SELECT_TOOL

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
        set_modifier_input(m, "Input_2", self.offset)  # Size
        set_modifier_input(m, "Input_3", self.mirror)  # Mirror Extrude
        set_modifier_input(m, "Input_4", self.asymmetry)  # Asymmetry Override
        set_modifier_input(m, "Input_5", self.asymmetry_distance)  # Asymmetry Distance
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
    return_to_tool = BLENDER_SELECT_TOOL

    # Array offset in the object's local space (direction * spacing), captured
    # by a single interactive drag; direction and distance derive from it.
    offset: FloatVectorProperty(
        name="Offset", subtype="TRANSLATION", size=3, options={"SKIP_SAVE"}
    )
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
            "Offset",
            description="Drag to set the array direction and spacing",
            property="offset",
            state_func="get_offset",
            interactive=True,
            axis_lock=True,
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

    def get_offset(self, context: Context, coords):
        # The drag offset (origin -> cursor) in the object's local space; the
        # local origin is (0,0,0), so the local hit point is the offset.
        # Return a Vector (not a tuple) so it's set as one vector property value.
        obj = self.object.original
        origin = obj.matrix_world.translation
        inv = obj.matrix_world.inverted()
        ray_o, ray_dir = get_picking_origin_dir(context, coords)

        # X/Y/Z lock: constrain to a global axis line through the origin, using
        # the point on that line closest to the view ray (view-angle robust).
        if self._axis_lock is not None:
            axis = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))[self._axis_lock]
            res = intersect_line_line(
                origin, origin + Vector(axis), ray_o, ray_o + ray_dir
            )
            if res is None:
                return Vector((0.0, 0.0, 0.0))
            return inv @ res[0]

        # Free drag: project onto the view-facing plane through the origin.
        view_dir = context.region_data.view_rotation @ Vector((0.0, 0.0, -1.0))
        hit = intersect_line_plane(ray_o, ray_o + ray_dir, origin, view_dir)
        if hit is None:
            return Vector((0.0, 0.0, 0.0))
        return inv @ hit

    def get_count(self, context: Context, coords):
        retval = super().state_func(context, coords)
        return abs(retval) + 2

    def set_props(self):
        offset = Vector(self.offset)
        if offset.length > 1e-6:
            direction = offset.normalized()
            distance = offset.length
        else:
            direction = Vector((1.0, 0.0, 0.0))
            distance = 0.0

        m = self.modifier
        set_modifier_input(m, "Input_21", tuple(direction))  # Direction
        set_modifier_input(m, "Input_22", self.count)  # Count
        set_modifier_input(m, "Input_23", distance)  # Spacing / Total distance
        set_modifier_input(m, "Input_24", self.use_total_distance)  # Use Total Distance
        set_modifier_input(m, "Input_25", self.align_rotation)  # Align Rotation
        set_modifier_input(m, "Input_26", self.merge)  # Merge by Distance
        set_modifier_input(m, "Input_29", self.merge_distance)  # Merge Distance
        set_modifier_input(m, "Input_30", self.flip)  # Flip Direction
        return True

    def draw_settings(self, context):
        layout = self.layout

        layout.prop(self, "offset")
        layout.prop(self, "flip")
        layout.prop(self, "use_total_distance")
        layout.prop(self, "align_rotation")
        layout.prop(self, "merge")
        sub = layout.column()
        sub.enabled = self.merge
        sub.prop(self, "merge_distance")


class View3D_OT_node_revolve(Operator, NodeOperator):
    """Revolve a 2D profile around a picked axis"""

    bl_idname = Operators.NodeRevolve
    bl_label = "Revolve"

    NODEGROUP_NAME = "CAD Sketcher Revolve"
    resources = (("node_groups", "CAD Sketcher Revolve"),)
    return_to_tool = BLENDER_SELECT_TOOL

    invalid_target_msg = "Select a sketch, curve or mesh profile to revolve"

    angle: FloatProperty(
        name="Angle",
        subtype="ANGLE",
        default=math.tau,
        min=-math.tau,
        max=math.tau,
        options={"SKIP_SAVE"},
    )
    angular_resolution: FloatProperty(
        name="Angular Resolution",
        description="Maximum angle per segment; the step count adapts to the "
        "revolve angle to keep a consistent smoothness",
        subtype="ANGLE",
        default=math.radians(2),
        min=math.radians(0.5),
        soft_max=math.radians(90),
    )
    flip: BoolProperty(name="Flip Direction")

    # Raw picked axis (object space, un-flipped), persisted so the redo panel
    # can re-apply the revolve without the transient axis pointer. Not
    # SKIP_SAVE: must survive redo; a fresh invoke re-picks before main() runs.
    axis_origin: FloatVectorProperty(size=3, subtype="XYZ", options={"HIDDEN"})
    axis_direction: FloatVectorProperty(size=3, subtype="XYZ", options={"HIDDEN"})

    states = (
        *BASE_STATES,
        state_from_args(
            "Axis",
            description="Click a mesh edge or curve/sketch line to revolve around",
            pointer="axis",
            types=(MeshEdge,),
            use_create=False,
        ),
    )

    def is_valid_target(self, obj):
        # Curves and sketches, plus mesh profiles (edge paths) -- the node group
        # converts mesh edges to a curve, so a poly-line/silhouette mesh works
        # too, matching Blender's Screw modifier.
        return obj is not None and obj.type in {"CURVE", "CURVES", "MESH"}

    def get_point(self, context, index):
        # The axis is a picked edge, resolved to endpoints in set_props; there
        # is no entity to return here.
        return None

    def pick_element(self, context, coords):
        # Mesh edges pick through the framework (object-agnostic now). Curves
        # aren't ray-castable, so fall back to the shared screen-space
        # curve-segment pick -- the same one the hover gizmo uses, so the
        # highlight and the pick agree.
        result = super().pick_element(context, coords)
        if result is not None:
            return result
        from ..utilities.view import curve_segment_under_cursor

        radius = 12.0 * context.preferences.system.ui_scale
        hit = curve_segment_under_cursor(context, coords, radius)
        if hit is not None:
            obj, point_index = hit
            self.state_data["type"] = MeshEdge
            return obj.name, point_index
        return None

    def _axis_endpoints(self):
        """World endpoints of the picked axis edge (mesh or curve), or None."""
        try:
            ob_name, index = self.get_state_pointer(index=1, implicit=True)
        except Exception:
            return None
        ob = bpy.data.objects.get(ob_name)
        if ob is None:
            return None
        if ob.type in {"CURVE", "CURVES"}:
            pts = getattr(ob.data, "points", None)
            if pts is None or index + 1 >= len(pts):
                return None
            mw = ob.matrix_world
            return mw @ Vector(pts[index].position), mw @ Vector(
                pts[index + 1].position
            )
        eob = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
        me = eob.data
        if not hasattr(me, "edges") or index >= len(me.edges):
            return None
        i0, i1 = me.edges[index].vertices
        mw = eob.matrix_world
        return mw @ Vector(me.vertices[i0].co), mw @ Vector(me.vertices[i1].co)

    def read_props(self, modifier):
        # Seed the angle/resolution from the existing revolve so re-invoking on
        # the same object continues from its current sweep. The axis is re-picked
        # each run (and flip isn't stored in the modifier), so neither is read.
        self.angle = get_modifier_input(modifier, "Socket_3")
        self.angular_resolution = get_modifier_input(modifier, "Socket_4")

    def _has_stored_axis(self):
        return Vector(self.axis_direction).length > 1e-9

    def main(self, context):
        # Need an axis: either freshly picked (interactive) or persisted from a
        # previous run (redo). Without one the modifier would sit on the node
        # group's default axis and generate a bogus revolve.
        if self._axis_endpoints() is None and not self._has_stored_axis():
            return False
        return super().main(context)

    def set_props(self):
        ends = self._axis_endpoints()
        if ends is not None:
            # Fresh pick: derive the raw axis in object space and persist it so a
            # later redo can reuse it without the (now-gone) axis pointer.
            w0, w1 = ends
            inv = self._obj.original.matrix_world.inverted()
            origin = inv @ w0
            direction = (inv @ w1) - origin
            if direction.length < 1e-9:
                return False
            direction.normalize()
            self.axis_origin = origin
            self.axis_direction = direction
        elif self._has_stored_axis():
            # Redo path: reuse the persisted axis.
            origin = Vector(self.axis_origin)
            direction = Vector(self.axis_direction)
        else:
            self.report({"WARNING"}, "Pick a revolve axis (an edge or line)")
            return False

        # Apply flip at write time (not baked into the stored axis) so toggling
        # it in the redo panel works.
        final_dir = -direction if self.flip else direction

        m = self.modifier
        set_modifier_input(m, "Socket_1", tuple(origin))  # Axis Origin
        set_modifier_input(m, "Socket_2", tuple(final_dir))  # Axis Direction
        set_modifier_input(m, "Socket_3", self.angle)  # Angle
        set_modifier_input(m, "Socket_4", self.angular_resolution)  # Angular Resolution
        return True

    def draw_settings(self, context):
        layout = self.layout
        row = layout.row(align=True)
        row.prop(self, "angle")
        row.prop(self, "flip", text="", icon="ARROW_LEFTRIGHT")
        layout.prop(self, "angular_resolution")


class View3D_OT_node_boolean(Operator, NodeOperator):
    """Nondestructively boolean the active object with a cutter object"""

    bl_idname = Operators.NodeBoolean
    bl_label = "Boolean"

    NODEGROUP_NAME = "CAD Sketcher Boolean"
    # Built programmatically (not shipped as an asset); see init().
    resources = ()

    invalid_target_msg = "Pick a body (mesh or sketch) to receive the boolean"

    # Two object states: the body (receives the modifier) and the cutter. Both
    # can be preselected (body active, cutter also selected) or picked in the
    # viewport, matching the other node tools.
    states = (
        *BASE_STATES,
        state_from_args(
            "Cutter",
            description="Pick the object to boolean the body with",
            pointer="cutter",
            types=(Object,),
            use_create=False,
        ),
    )

    operation: bpy.props.EnumProperty(
        name="Operation",
        items=(
            ("Difference", "Difference", "Subtract the cutter from the body"),
            ("Union", "Union", "Merge the cutter into the body"),
            ("Intersect", "Intersect", "Keep only the overlap"),
        ),
        default="Difference",
    )
    self_intersection: BoolProperty(name="Self Intersection", default=True)
    hole_tolerant: BoolProperty(name="Hole Tolerant", default=False)

    # A solid cutter would hide the boolean result, so switch its viewport
    # display (wireframe by default, like Bool Tool). display_type is a draw-only
    # property, so setting it is cheap and does not rebuild the depsgraph.
    cutter_display: bpy.props.EnumProperty(
        name="Cutter Display",
        items=(
            ("WIRE", "Wire", "Show the cutter as wireframe so the result is visible"),
            ("SOLID", "Solid", "Leave the cutter shaded solid"),
        ),
        default="WIRE",
    )

    # Persist the picked cutter so the redo panel can re-apply and edit it (the
    # pointer state, like the base object pointer, is transient across redo).
    cutter_name: StringProperty(name="Cutter")

    # Both operands may be a mesh or a sketch (Curves).
    def is_valid_target(self, obj):
        return obj is not None and obj.type in {"MESH", "CURVE", "CURVES"}

    def get_point(self, context, index):
        # Object pointer states carry no implicit point.
        return None

    def invoke(self, context, event):
        # Editing: when the body and the cutter are both preselected and that
        # cutter already has a boolean on the body, seed the operator from it so
        # re-invoking edits the existing boolean (like Extrude) instead of
        # resetting it to defaults. Seeding must happen here, once, before the
        # redo panel -- doing it in main()/execute() would clobber a redo-panel
        # edit on the next re-run. The cutter is only known at invoke when it is
        # preselected, so interactive cutter-picking is always treated as create.
        selection = self.gather_selection(context)
        if selection:
            body = selection[0]
            for other in selection[1:]:
                mod = body.modifiers.get(f"CAD_Sketcher Boolean {other.name}")
                if mod and mod.node_group:
                    try:
                        self.read_props(mod)
                    except Exception:
                        pass
                    break
        return super().invoke(context, event)

    def init(self, context: Context, event: Event):
        # Build the boolean node group in place of loading an asset.
        from ..utilities.boolean_nodes import build_boolean_node_group

        build_boolean_node_group()
        bpy.ops.ed.undo_push(message="Add Boolean")
        return True

    def _resolve_cutter(self, context: Context):
        """The cutter object: the picked pointer, else the persisted name (redo).

        Mirrors ``resolved_object`` for the body: the ``cutter`` pointer state
        carries the interactive/prefilled pick, and ``cutter_name`` restores it
        on the redo path where the pointer is gone.
        """
        cutter = getattr(self, "cutter", None)
        if cutter is None and self.cutter_name:
            cutter = bpy.data.objects.get(self.cutter_name)
        return cutter

    def _modifier_name(self):
        # One modifier per cutter, so several booleans stack on the same body
        # instead of overwriting each other. Re-applying with the same cutter
        # edits its existing modifier (same name); a new cutter adds another.
        return f"CAD_Sketcher Boolean {self._cutter.name}"

    def read_props(self, modifier):
        ids = self._input_ids(modifier.node_group)
        self.operation = get_boolean_operation(modifier, ids["Operation"])
        self.self_intersection = get_modifier_input(modifier, ids["Self Intersection"])
        self.hole_tolerant = get_modifier_input(modifier, ids["Hole Tolerant"])

    def main(self, context: Context):
        from ..utilities.boolean_nodes import build_boolean_node_group

        build_boolean_node_group()  # ensure it exists on the redo path too

        cutter = self._resolve_cutter(context)
        if cutter is None:
            self.report({"WARNING"}, "Pick a cutter object to boolean with")
            return False
        # A non-geometry cutter (empty, light, camera) yields no mesh, so the
        # boolean would silently do nothing. Reject it with a clear message.
        if not self.is_valid_target(cutter):
            self.report({"WARNING"}, "The cutter must be a mesh or sketch object")
            return False
        # Adding this boolean makes the body read the cutter's geometry (body
        # depends on cutter). If the cutter already depends on the body through
        # other CAD Sketcher booleans -- including the cutter being the body
        # itself -- that closes a depsgraph dependency cycle, which crashes
        # Blender. Refuse before creating the modifier.
        body = self.resolved_object()
        if self._creates_cycle(body, cutter):
            self.report(
                {"WARNING"},
                "That cutter depends on the body; it would create a dependency cycle",
            )
            return False
        self.cutter_name = cutter.name
        self._cutter = cutter
        # Reveal the result: a solid cutter sitting over the body would hide it.
        cutter.display_type = self.cutter_display
        return super().main(context)

    @staticmethod
    def _input_ids(node_group):
        return {
            s.name: s.identifier
            for s in node_group.interface.items_tree
            if getattr(s, "in_out", "") == "INPUT"
        }

    @classmethod
    def _boolean_cutters(cls, obj):
        """Objects ``obj`` reads as cutters through its CAD Sketcher booleans."""
        from ..utilities.boolean_nodes import BOOLEAN_NODE_GROUP

        cutters = []
        for m in obj.modifiers:
            group = getattr(m, "node_group", None)
            if m.type != "NODES" or group is None or group.name != BOOLEAN_NODE_GROUP:
                continue
            ids = cls._input_ids(group)
            cutter = get_modifier_input(m, ids["Cutter"])
            if cutter is not None:
                cutters.append(cutter)
        return cutters

    @classmethod
    def _creates_cycle(cls, body, cutter):
        """Whether making ``body`` read ``cutter`` closes a boolean dependency
        cycle, i.e. ``cutter`` already depends (transitively) on ``body``.

        Also true when ``cutter is body`` (a self-reference is a length-0 cycle).
        """
        stack = [cutter]
        seen = set()
        while stack:
            obj = stack.pop()
            if obj == body:
                return True
            if obj in seen:
                continue
            seen.add(obj)
            stack.extend(cls._boolean_cutters(obj))
        return False

    def set_props(self):
        m = self.modifier
        ids = self._input_ids(m.node_group)
        set_modifier_input(m, ids["Cutter"], self._cutter)
        set_boolean_operation(m, ids["Operation"], self.operation)
        set_modifier_input(m, ids["Self Intersection"], self.self_intersection)
        set_modifier_input(m, ids["Hole Tolerant"], self.hole_tolerant)
        return True

    def draw_settings(self, context):
        layout = self.layout
        layout.prop_search(self, "cutter_name", bpy.data, "objects", text="Cutter")
        layout.prop(self, "operation")
        layout.prop(self, "cutter_display")
        layout.prop(self, "self_intersection")
        layout.prop(self, "hole_tolerant")


register, unregister = register_stateops_factory(
    (
        View3D_OT_node_extrude,
        View3D_OT_node_array_linear,
        View3D_OT_node_revolve,
        View3D_OT_node_boolean,
    )
)
