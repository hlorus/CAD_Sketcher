"""Code-built ``CAD Sketcher Linear Array`` node group (was a binary asset).

``build_array_node_group`` rebuilds the linear-array group in code, replacing the
copy that used to ship in ``resources/assets.blend`` -- mirroring the boolean,
convert, extrude and revolve groups. The graph is a faithful transcription of the
shipped asset (identical nodes, socket defaults and links, reroutes kept, cosmetic
frames dropped), so the evaluated output is unchanged.

Node properties, socket defaults and links are addressed by name (and, where a
node repeats a socket name like Math's two "Value" inputs, by occurrence) and set
defensively: a socket or property that only exists on newer Blender is skipped,
so the same graph builds on every supported version (the asset used to rely on
Blender's file-load version migration for this; a code build must do it itself).
"""

import bpy

ARRAY_NODE_GROUP = "CAD Sketcher Linear Array"
# Bump when the built graph changes so groups baked into saved files rebuild.
ARRAY_VERSION = 1


def _input_ids(node_group):
    """Map input socket name -> identifier (values are written by name)."""
    return {
        s.name: s.identifier
        for s in node_group.interface.items_tree
        if getattr(s, "in_out", "") == "INPUT"
    }


def _snapshot_modifier_inputs(node_group):
    """Capture every modifier bound to ``node_group`` as (modifier, {name: value}).

    Rebuilding in place reassigns socket identifiers, and modifier inputs are keyed
    by identifier, so values are re-applied by the stable socket *name* afterwards
    -- otherwise upgrading from the old binary asset silently resets every array.
    """
    from ..operators.modifiers import get_modifier_input

    names = {
        s.identifier: s.name
        for s in node_group.interface.items_tree
        if getattr(s, "in_out", "") == "INPUT"
    }
    saved = []
    for obj in bpy.data.objects:
        for mod in obj.modifiers:
            if (
                getattr(mod, "type", None) != "NODES"
                or mod.node_group is not node_group
            ):
                continue
            values = {}
            for identifier, name in names.items():
                try:
                    value = get_modifier_input(mod, identifier)
                except Exception:
                    continue
                values[name] = tuple(value) if hasattr(value, "__len__") else value
            if values:
                saved.append((mod, values))
    return saved


def _restore_modifier_inputs(node_group, saved):
    """Re-apply snapshot values (see ``_snapshot_modifier_inputs``) by name."""
    from ..operators.modifiers import set_modifier_input

    ids = _input_ids(node_group)
    for mod, values in saved:
        for name, value in values.items():
            identifier = ids.get(name)
            if identifier is None:
                continue
            try:
                set_modifier_input(mod, identifier, value)
            except Exception:
                pass


def _socket(sockets, name, occurrence):
    """The ``occurrence``-th socket named ``name`` (or None if absent)."""
    k = 0
    for s in sockets:
        if s.name == name:
            if k == occurrence:
                return s
            k += 1
    return None


# Records sockets a build couldn't resolve on this Blender (see build_array_node_group).
_skips = []


def _set(node, attr, value):
    """Set a node property, ignoring it if this Blender lacks it."""
    try:
        setattr(node, attr, value)
    except Exception:
        pass


def _seti(node, name, occurrence, value):
    """Set an input socket default by (name, occurrence), if it exists."""
    socket = _socket(node.inputs, name, occurrence)
    if socket is not None:
        try:
            socket.default_value = value
        except Exception:
            pass
    else:
        _skips.append(f"default {node.name}.in[{name!r}#{occurrence}]")


def _link(links, from_node, from_name, from_occ, to_node, to_name, to_occ):
    """Link two sockets addressed by (name, occurrence); skip if either is absent."""
    a = _socket(from_node.outputs, from_name, from_occ)
    b = _socket(to_node.inputs, to_name, to_occ)
    if a is not None and b is not None:
        links.new(a, b)
    else:
        miss = []
        if a is None:
            miss.append(f"{from_node.name}.out[{from_name!r}#{from_occ}]")
        if b is None:
            miss.append(f"{to_node.name}.in[{to_name!r}#{to_occ}]")
        _skips.append("link " + " -> ".join(miss))


def _build_graph(ng):
    """Populate the freshly cleared group with the array node graph (generated)."""
    iface = ng.interface
    s = iface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    s = iface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    s = iface.new_socket("Direction", in_out="INPUT", socket_type="NodeSocketVector")
    s.default_value = (0.0, 0.0, 1.0)
    s.subtype = "NONE"
    s.min_value = 0.0
    s.max_value = 1.0
    s = iface.new_socket("Count", in_out="INPUT", socket_type="NodeSocketInt")
    s.default_value = 5
    s.subtype = "NONE"
    s.min_value = 1
    s.max_value = 10000
    s = iface.new_socket(
        "Spacing / Total distance", in_out="INPUT", socket_type="NodeSocketFloat"
    )
    s.default_value = 3.0
    s.subtype = "NONE"
    s.min_value = 0.0
    s.max_value = 3.4028234663852886e38
    s = iface.new_socket("Flip Direciton", in_out="INPUT", socket_type="NodeSocketBool")
    s.default_value = False
    s = iface.new_socket(
        "Use Total Distance", in_out="INPUT", socket_type="NodeSocketBool"
    )
    s.default_value = False
    s = iface.new_socket("Align Rotation", in_out="INPUT", socket_type="NodeSocketBool")
    s.default_value = False
    s = iface.new_socket(
        "Merge by Distance", in_out="INPUT", socket_type="NodeSocketBool"
    )
    s.default_value = False
    s = iface.new_socket(
        "Merge Distance", in_out="INPUT", socket_type="NodeSocketFloat"
    )
    s.default_value = 0.001
    s.subtype = "DISTANCE"
    s.min_value = 0.0
    s.max_value = 3.4028234663852886e38
    s = iface.new_socket(
        "Realize Instances", in_out="INPUT", socket_type="NodeSocketBool"
    )
    s.default_value = True
    s = iface.new_socket("Show Axies", in_out="INPUT", socket_type="NodeSocketBool")
    s.default_value = False

    nodes = ng.nodes
    n = {}
    x = nodes.new("NodeGroupInput")
    x.name = "Group Input"
    n["Group Input"] = x
    x = nodes.new("NodeGroupOutput")
    x.name = "Group Output"
    n["Group Output"] = x
    x = nodes.new("ShaderNodeVectorMath")
    x.name = "Vector Math.002"
    n["Vector Math.002"] = x
    _set(x, "operation", "SCALE")
    _seti(x, "Scale", 0, -1.0)
    x = nodes.new("NodeReroute")
    x.name = "Reroute.022"
    n["Reroute.022"] = x
    _set(x, "socket_idname", "NodeSocketVectorEuler")
    x = nodes.new("NodeReroute")
    x.name = "Reroute.023"
    n["Reroute.023"] = x
    _set(x, "socket_idname", "NodeSocketVectorEuler")
    x = nodes.new("NodeReroute")
    x.name = "Reroute.034"
    n["Reroute.034"] = x
    _set(x, "socket_idname", "NodeSocketVector")
    x = nodes.new("NodeReroute")
    x.name = "Reroute.024"
    n["Reroute.024"] = x
    _set(x, "socket_idname", "NodeSocketVector")
    x = nodes.new("NodeReroute")
    x.name = "Reroute.035"
    n["Reroute.035"] = x
    _set(x, "socket_idname", "NodeSocketVector")
    x = nodes.new("NodeReroute")
    x.name = "Reroute"
    n["Reroute"] = x
    _set(x, "socket_idname", "NodeSocketGeometry")
    x = nodes.new("NodeReroute")
    x.name = "Reroute.001"
    n["Reroute.001"] = x
    _set(x, "socket_idname", "NodeSocketVector")
    x = nodes.new("NodeReroute")
    x.name = "Reroute.015"
    n["Reroute.015"] = x
    _set(x, "socket_idname", "NodeSocketVector")
    x = nodes.new("NodeReroute")
    x.name = "Reroute.004"
    n["Reroute.004"] = x
    _set(x, "socket_idname", "NodeSocketGeometry")
    x = nodes.new("ShaderNodeSeparateXYZ")
    x.name = "Separate XYZ.001"
    n["Separate XYZ.001"] = x
    x = nodes.new("GeometryNodeInputPosition")
    x.name = "Position.001"
    n["Position.001"] = x
    x = nodes.new("NodeReroute")
    x.name = "Reroute.011"
    n["Reroute.011"] = x
    _set(x, "socket_idname", "NodeSocketGeometry")
    x = nodes.new("ShaderNodeMath")
    x.name = "Math"
    n["Math"] = x
    _set(x, "operation", "SUBTRACT")
    x = nodes.new("ShaderNodeMath")
    x.name = "Math.004"
    n["Math.004"] = x
    _set(x, "operation", "DIVIDE")
    _seti(x, "Value", 1, 2.0)
    x = nodes.new("ShaderNodeMath")
    x.name = "Math.005"
    n["Math.005"] = x
    _set(x, "use_clamp", True)
    x = nodes.new("NodeReroute")
    x.name = "Reroute.005"
    n["Reroute.005"] = x
    _set(x, "socket_idname", "NodeSocketFloat")
    x = nodes.new("NodeReroute")
    x.name = "Reroute.006"
    n["Reroute.006"] = x
    _set(x, "socket_idname", "NodeSocketFloat")
    x = nodes.new("ShaderNodeMath")
    x.name = "Math.008"
    n["Math.008"] = x
    _set(x, "operation", "MULTIPLY")
    _seti(x, "Value", 1, -1.0)
    x = nodes.new("ShaderNodeMath")
    x.name = "Math.002"
    n["Math.002"] = x
    _set(x, "operation", "SUBTRACT")
    x = nodes.new("GeometryNodeAttributeStatistic")
    x.name = "Attribute Statistic.002"
    n["Attribute Statistic.002"] = x
    x = nodes.new("ShaderNodeMath")
    x.name = "Math.009"
    n["Math.009"] = x
    _set(x, "operation", "DIVIDE")
    _seti(x, "Value", 1, 2.0)
    x = nodes.new("ShaderNodeMath")
    x.name = "Math.010"
    n["Math.010"] = x
    x = nodes.new("NodeReroute")
    x.name = "Reroute.007"
    n["Reroute.007"] = x
    _set(x, "socket_idname", "NodeSocketFloat")
    x = nodes.new("NodeReroute")
    x.name = "Reroute.008"
    n["Reroute.008"] = x
    _set(x, "socket_idname", "NodeSocketFloat")
    x = nodes.new("ShaderNodeMath")
    x.name = "Math.003"
    n["Math.003"] = x
    _set(x, "operation", "SUBTRACT")
    x = nodes.new("GeometryNodeAttributeStatistic")
    x.name = "Attribute Statistic.003"
    n["Attribute Statistic.003"] = x
    x = nodes.new("ShaderNodeMath")
    x.name = "Math.017"
    n["Math.017"] = x
    _set(x, "operation", "DIVIDE")
    _seti(x, "Value", 1, 2.0)
    x = nodes.new("ShaderNodeMath")
    x.name = "Math.018"
    n["Math.018"] = x
    x = nodes.new("NodeReroute")
    x.name = "Reroute.009"
    n["Reroute.009"] = x
    _set(x, "socket_idname", "NodeSocketFloat")
    x = nodes.new("NodeReroute")
    x.name = "Reroute.010"
    n["Reroute.010"] = x
    _set(x, "socket_idname", "NodeSocketFloat")
    x = nodes.new("ShaderNodeMath")
    x.name = "Math.019"
    n["Math.019"] = x
    _set(x, "operation", "MULTIPLY")
    _seti(x, "Value", 1, -1.0)
    x = nodes.new("GeometryNodeAttributeStatistic")
    x.name = "Attribute Statistic.001"
    n["Attribute Statistic.001"] = x
    x = nodes.new("ShaderNodeMath")
    x.name = "Math.012"
    n["Math.012"] = x
    _set(x, "operation", "MULTIPLY")
    _seti(x, "Value", 1, -1.0)
    x = nodes.new("GeometryNodeSwitch")
    x.name = "Switch.004"
    n["Switch.004"] = x
    x = nodes.new("GeometryNodeSwitch")
    x.name = "Switch.006"
    n["Switch.006"] = x
    x = nodes.new("GeometryNodeSwitch")
    x.name = "Switch.007"
    n["Switch.007"] = x
    x = nodes.new("FunctionNodeInputBool")
    x.name = "Boolean"
    n["Boolean"] = x
    _set(x, "boolean", True)
    x = nodes.new("FunctionNodeInputBool")
    x.name = "Boolean.001"
    n["Boolean.001"] = x
    x = nodes.new("FunctionNodeInputBool")
    x.name = "Boolean.002"
    n["Boolean.002"] = x
    _set(x, "boolean", True)
    x = nodes.new("NodeReroute")
    x.name = "Reroute.012"
    n["Reroute.012"] = x
    _set(x, "socket_idname", "NodeSocketVector")
    x = nodes.new("NodeReroute")
    x.name = "Reroute.013"
    n["Reroute.013"] = x
    _set(x, "socket_idname", "NodeSocketVector")
    x = nodes.new("ShaderNodeCombineXYZ")
    x.name = "Combine XYZ"
    n["Combine XYZ"] = x
    x = nodes.new("GeometryNodeTransform")
    x.name = "Transform"
    n["Transform"] = x
    x = nodes.new("NodeReroute")
    x.name = "Reroute.028"
    n["Reroute.028"] = x
    _set(x, "socket_idname", "NodeSocketInt")
    x = nodes.new("NodeReroute")
    x.name = "Reroute.003"
    n["Reroute.003"] = x
    _set(x, "socket_idname", "NodeSocketGeometry")
    x = nodes.new("ShaderNodeVectorMath")
    x.name = "Vector Math.001"
    n["Vector Math.001"] = x
    _set(x, "operation", "SCALE")
    x = nodes.new("NodeReroute")
    x.name = "Reroute.031"
    n["Reroute.031"] = x
    _set(x, "socket_idname", "NodeSocketVector")
    x = nodes.new("NodeReroute")
    x.name = "Reroute.029"
    n["Reroute.029"] = x
    _set(x, "socket_idname", "NodeSocketInt")
    x = nodes.new("GeometryNodeMeshLine")
    x.name = "Mesh Line.002"
    n["Mesh Line.002"] = x
    x = nodes.new("GeometryNodeMeshLine")
    x.name = "Mesh Line.003"
    n["Mesh Line.003"] = x
    _set(x, "mode", "END_POINTS")
    x = nodes.new("NodeReroute")
    x.name = "Reroute.033"
    n["Reroute.033"] = x
    _set(x, "socket_idname", "NodeSocketVector")
    x = nodes.new("NodeReroute")
    x.name = "Reroute.032"
    n["Reroute.032"] = x
    _set(x, "socket_idname", "NodeSocketVector")
    x = nodes.new("NodeReroute")
    x.name = "Reroute.030"
    n["Reroute.030"] = x
    _set(x, "socket_idname", "NodeSocketInt")
    x = nodes.new("NodeReroute")
    x.name = "Reroute.020"
    n["Reroute.020"] = x
    _set(x, "socket_idname", "NodeSocketGeometry")
    x = nodes.new("FunctionNodeAlignEulerToVector")
    x.name = "Align Euler to Vector"
    n["Align Euler to Vector"] = x
    x = nodes.new("GeometryNodeInstanceOnPoints")
    x.name = "Instance on Points.001"
    n["Instance on Points.001"] = x
    x = nodes.new("GeometryNodeSwitch")
    x.name = "Switch.002"
    n["Switch.002"] = x
    _set(x, "input_type", "GEOMETRY")
    x = nodes.new("GeometryNodeRotateInstances")
    x.name = "Rotate Instances"
    n["Rotate Instances"] = x
    x = nodes.new("NodeGroupInput")
    x.name = "Group Input.001"
    n["Group Input.001"] = x
    x = nodes.new("GeometryNodeSwitch")
    x.name = "Switch"
    n["Switch"] = x
    _set(x, "input_type", "GEOMETRY")
    x = nodes.new("GeometryNodeRealizeInstances")
    x.name = "Realize Instances"
    n["Realize Instances"] = x
    _set(x, "realize_to_point_domain", True)
    x = nodes.new("NodeGroupInput")
    x.name = "Group Input.002"
    n["Group Input.002"] = x
    x = nodes.new("GeometryNodeSwitch")
    x.name = "Switch.001"
    n["Switch.001"] = x
    _set(x, "input_type", "GEOMETRY")
    x = nodes.new("GeometryNodeMergeByDistance")
    x.name = "Merge by Distance"
    n["Merge by Distance"] = x
    x = nodes.new("NodeGroupInput")
    x.name = "Group Input.003"
    n["Group Input.003"] = x
    x = nodes.new("GeometryNodeSetPosition")
    x.name = "Set Position"
    n["Set Position"] = x
    x = nodes.new("NodeReroute")
    x.name = "Reroute.014"
    n["Reroute.014"] = x
    _set(x, "socket_idname", "NodeSocketVector")
    x = nodes.new("NodeReroute")
    x.name = "Reroute.027"
    n["Reroute.027"] = x
    _set(x, "socket_idname", "NodeSocketVector")
    x = nodes.new("NodeReroute")
    x.name = "Reroute.019"
    n["Reroute.019"] = x
    _set(x, "socket_idname", "NodeSocketGeometry")
    x = nodes.new("NodeGroupInput")
    x.name = "Group Input.005"
    n["Group Input.005"] = x
    x = nodes.new("GeometryNodeJoinGeometry")
    x.name = "Join Geometry"
    n["Join Geometry"] = x
    x = nodes.new("GeometryNodeSwitch")
    x.name = "Switch.005"
    n["Switch.005"] = x
    _set(x, "input_type", "GEOMETRY")
    x = nodes.new("GeometryNodeSetPosition")
    x.name = "Set Position.001"
    n["Set Position.001"] = x
    x = nodes.new("NodeReroute")
    x.name = "Reroute.002"
    n["Reroute.002"] = x
    _set(x, "socket_idname", "NodeSocketGeometry")
    x = nodes.new("GeometryNodeSwitch")
    x.name = "Switch.003"
    n["Switch.003"] = x
    _set(x, "input_type", "GEOMETRY")
    x = nodes.new("NodeGroupInput")
    x.name = "Group Input.007"
    n["Group Input.007"] = x
    x = nodes.new("NodeGroupInput")
    x.name = "Group Input.008"
    n["Group Input.008"] = x
    x = nodes.new("ShaderNodeMath")
    x.name = "Math.001"
    n["Math.001"] = x
    _set(x, "operation", "MULTIPLY")
    _seti(x, "Value", 0, -1.0)
    x = nodes.new("NodeReroute")
    x.name = "Reroute.016"
    n["Reroute.016"] = x
    _set(x, "socket_idname", "NodeSocketFloat")
    x = nodes.new("NodeReroute")
    x.name = "Reroute.017"
    n["Reroute.017"] = x
    _set(x, "socket_idname", "NodeSocketFloat")
    x = nodes.new("NodeReroute")
    x.name = "Reroute.036"
    n["Reroute.036"] = x
    _set(x, "socket_idname", "NodeSocketFloat")
    x = nodes.new("ShaderNodeVectorMath")
    x.name = "Vector Math"
    n["Vector Math"] = x
    _set(x, "operation", "NORMALIZE")
    x = nodes.new("GeometryNodeSwitch")
    x.name = "Switch.008"
    n["Switch.008"] = x
    x = nodes.new("NodeReroute")
    x.name = "Reroute.018"
    n["Reroute.018"] = x
    _set(x, "socket_idname", "NodeSocketFloat")
    x = nodes.new("FunctionNodeEulerToRotation")
    x.name = "Euler to Rotation"
    n["Euler to Rotation"] = x

    _link(ng.links, n["Switch.002"], "Output", 0, n["Realize Instances"], "Geometry", 0)
    _link(ng.links, n["Realize Instances"], "Geometry", 0, n["Switch"], "True", 0)
    _link(ng.links, n["Switch.002"], "Output", 0, n["Switch"], "False", 0)
    _link(ng.links, n["Switch"], "Output", 0, n["Merge by Distance"], "Geometry", 0)
    _link(ng.links, n["Merge by Distance"], "Geometry", 0, n["Switch.001"], "True", 0)
    _link(ng.links, n["Switch"], "Output", 0, n["Switch.001"], "False", 0)
    _link(
        ng.links,
        n["Instance on Points.001"],
        "Instances",
        0,
        n["Rotate Instances"],
        "Instances",
        0,
    )
    _link(ng.links, n["Reroute.023"], "Output", 0, n["Euler to Rotation"], "Euler", 0)
    _link(ng.links, n["Rotate Instances"], "Instances", 0, n["Switch.002"], "True", 0)
    _link(
        ng.links,
        n["Instance on Points.001"],
        "Instances",
        0,
        n["Switch.002"],
        "False",
        0,
    )
    _link(
        ng.links, n["Reroute.015"], "Output", 0, n["Align Euler to Vector"], "Vector", 0
    )
    _link(ng.links, n["Vector Math"], "Vector", 0, n["Vector Math.001"], "Vector", 0)
    _link(ng.links, n["Mesh Line.003"], "Mesh", 0, n["Switch.003"], "True", 0)
    _link(ng.links, n["Mesh Line.002"], "Mesh", 0, n["Switch.003"], "False", 0)
    _link(ng.links, n["Reroute.032"], "Output", 0, n["Mesh Line.002"], "Offset", 0)
    _link(ng.links, n["Reroute.033"], "Output", 0, n["Mesh Line.003"], "Offset", 0)
    _link(
        ng.links,
        n["Reroute.003"],
        "Output",
        0,
        n["Instance on Points.001"],
        "Points",
        0,
    )
    _link(ng.links, n["Reroute.030"], "Output", 0, n["Mesh Line.002"], "Count", 0)
    _link(ng.links, n["Reroute.029"], "Output", 0, n["Mesh Line.003"], "Count", 0)
    _link(ng.links, n["Switch.001"], "Output", 0, n["Set Position"], "Geometry", 0)
    _link(ng.links, n["Reroute.014"], "Output", 0, n["Set Position"], "Offset", 0)
    _link(ng.links, n["Reroute.019"], "Output", 0, n["Switch.005"], "False", 0)
    _link(ng.links, n["Reroute.019"], "Output", 0, n["Join Geometry"], "Geometry", 0)
    _link(ng.links, n["Join Geometry"], "Geometry", 0, n["Switch.005"], "True", 0)
    _link(ng.links, n["Set Position"], "Geometry", 0, n["Reroute.019"], "Input", 0)
    _link(ng.links, n["Switch.003"], "Output", 0, n["Reroute.003"], "Input", 0)
    _link(ng.links, n["Reroute.003"], "Output", 0, n["Reroute.020"], "Input", 0)
    _link(
        ng.links,
        n["Align Euler to Vector"],
        "Rotation",
        0,
        n["Reroute.022"],
        "Input",
        0,
    )
    _link(ng.links, n["Reroute.022"], "Output", 0, n["Reroute.023"], "Input", 0)
    _link(ng.links, n["Vector Math.002"], "Vector", 0, n["Reroute.024"], "Input", 0)
    _link(ng.links, n["Reroute.028"], "Output", 0, n["Reroute.029"], "Input", 0)
    _link(ng.links, n["Reroute.029"], "Output", 0, n["Reroute.030"], "Input", 0)
    _link(ng.links, n["Vector Math.001"], "Vector", 0, n["Reroute.031"], "Input", 0)
    _link(ng.links, n["Reroute.031"], "Output", 0, n["Reroute.032"], "Input", 0)
    _link(ng.links, n["Reroute.031"], "Output", 0, n["Reroute.033"], "Input", 0)
    _link(ng.links, n["Reroute.027"], "Output", 0, n["Set Position.001"], "Offset", 0)
    _link(ng.links, n["Reroute.034"], "Output", 0, n["Reroute.027"], "Input", 0)
    _link(ng.links, n["Reroute.024"], "Output", 0, n["Reroute.034"], "Input", 0)
    _link(
        ng.links,
        n["Set Position.001"],
        "Geometry",
        0,
        n["Join Geometry"],
        "Geometry",
        0,
    )
    _link(ng.links, n["Reroute.020"], "Output", 0, n["Reroute.002"], "Input", 0)
    _link(ng.links, n["Reroute"], "Output", 0, n["Set Position.001"], "Geometry", 0)
    _link(ng.links, n["Group Input"], "Direction", 0, n["Reroute.035"], "Input", 0)
    _link(ng.links, n["Group Input"], "Direction", 0, n["Vector Math"], "Vector", 0)
    _link(ng.links, n["Group Input"], "Count", 0, n["Reroute.028"], "Input", 0)
    _link(ng.links, n["Reroute.017"], "Output", 0, n["Reroute.036"], "Input", 0)
    _link(
        ng.links,
        n["Group Input.007"],
        "Use Total Distance",
        0,
        n["Switch.003"],
        "Switch",
        0,
    )
    _link(
        ng.links,
        n["Group Input.001"],
        "Align Rotation",
        0,
        n["Switch.002"],
        "Switch",
        0,
    )
    _link(
        ng.links, n["Group Input.002"], "Realize Instances", 0, n["Switch"], "Switch", 0
    )
    _link(
        ng.links,
        n["Group Input.003"],
        "Merge by Distance",
        0,
        n["Switch.001"],
        "Switch",
        0,
    )
    _link(ng.links, n["Group Input.005"], "Show Axies", 0, n["Switch.005"], "Switch", 0)
    _link(ng.links, n["Reroute.011"], "Output", 0, n["Transform"], "Geometry", 0)
    _link(
        ng.links,
        n["Reroute.011"],
        "Output",
        0,
        n["Attribute Statistic.001"],
        "Geometry",
        0,
    )
    _link(
        ng.links, n["Position.001"], "Position", 0, n["Separate XYZ.001"], "Vector", 0
    )
    _link(
        ng.links,
        n["Separate XYZ.001"],
        "X",
        0,
        n["Attribute Statistic.001"],
        "Attribute",
        0,
    )
    _link(ng.links, n["Combine XYZ"], "Vector", 0, n["Transform"], "Translation", 0)
    _link(ng.links, n["Math"], "Value", 0, n["Math.004"], "Value", 0)
    _link(ng.links, n["Math.004"], "Value", 0, n["Math.005"], "Value", 0)
    _link(ng.links, n["Attribute Statistic.001"], "Min", 0, n["Math"], "Value", 1)
    _link(ng.links, n["Attribute Statistic.001"], "Max", 0, n["Math"], "Value", 0)
    _link(ng.links, n["Math.005"], "Value", 0, n["Math.008"], "Value", 0)
    _link(ng.links, n["Reroute.005"], "Output", 0, n["Math.005"], "Value", 1)
    _link(ng.links, n["Reroute.006"], "Output", 0, n["Reroute.005"], "Input", 0)
    _link(
        ng.links, n["Attribute Statistic.001"], "Min", 0, n["Reroute.006"], "Input", 0
    )
    _link(ng.links, n["Math.002"], "Value", 0, n["Math.009"], "Value", 0)
    _link(ng.links, n["Math.009"], "Value", 0, n["Math.010"], "Value", 0)
    _link(ng.links, n["Attribute Statistic.002"], "Min", 0, n["Math.002"], "Value", 1)
    _link(ng.links, n["Attribute Statistic.002"], "Max", 0, n["Math.002"], "Value", 0)
    _link(ng.links, n["Math.010"], "Value", 0, n["Math.012"], "Value", 0)
    _link(ng.links, n["Reroute.007"], "Output", 0, n["Math.010"], "Value", 1)
    _link(ng.links, n["Reroute.008"], "Output", 0, n["Reroute.007"], "Input", 0)
    _link(
        ng.links, n["Attribute Statistic.002"], "Min", 0, n["Reroute.008"], "Input", 0
    )
    _link(ng.links, n["Math.003"], "Value", 0, n["Math.017"], "Value", 0)
    _link(ng.links, n["Math.017"], "Value", 0, n["Math.018"], "Value", 0)
    _link(ng.links, n["Attribute Statistic.003"], "Min", 0, n["Math.003"], "Value", 1)
    _link(ng.links, n["Attribute Statistic.003"], "Max", 0, n["Math.003"], "Value", 0)
    _link(ng.links, n["Math.018"], "Value", 0, n["Math.019"], "Value", 0)
    _link(ng.links, n["Reroute.009"], "Output", 0, n["Math.018"], "Value", 1)
    _link(ng.links, n["Reroute.010"], "Output", 0, n["Reroute.009"], "Input", 0)
    _link(
        ng.links, n["Attribute Statistic.003"], "Min", 0, n["Reroute.010"], "Input", 0
    )
    _link(
        ng.links,
        n["Separate XYZ.001"],
        "Y",
        0,
        n["Attribute Statistic.002"],
        "Attribute",
        0,
    )
    _link(
        ng.links,
        n["Separate XYZ.001"],
        "Z",
        0,
        n["Attribute Statistic.003"],
        "Attribute",
        0,
    )
    _link(
        ng.links,
        n["Reroute.011"],
        "Output",
        0,
        n["Attribute Statistic.002"],
        "Geometry",
        0,
    )
    _link(
        ng.links,
        n["Reroute.011"],
        "Output",
        0,
        n["Attribute Statistic.003"],
        "Geometry",
        0,
    )
    _link(ng.links, n["Combine XYZ"], "Vector", 0, n["Reroute.012"], "Input", 0)
    _link(ng.links, n["Math.008"], "Value", 0, n["Switch.004"], "True", 0)
    _link(ng.links, n["Math.012"], "Value", 0, n["Switch.006"], "True", 0)
    _link(ng.links, n["Math.019"], "Value", 0, n["Switch.007"], "True", 0)
    _link(ng.links, n["Switch.007"], "Output", 0, n["Combine XYZ"], "Z", 0)
    _link(ng.links, n["Switch.006"], "Output", 0, n["Combine XYZ"], "Y", 0)
    _link(ng.links, n["Switch.004"], "Output", 0, n["Combine XYZ"], "X", 0)
    _link(ng.links, n["Reroute.012"], "Output", 0, n["Reroute.013"], "Input", 0)
    _link(ng.links, n["Boolean"], "Boolean", 0, n["Switch.004"], "Switch", 0)
    _link(ng.links, n["Boolean.002"], "Boolean", 0, n["Switch.007"], "Switch", 0)
    _link(ng.links, n["Boolean.001"], "Boolean", 0, n["Switch.006"], "Switch", 0)
    _link(
        ng.links,
        n["Transform"],
        "Geometry",
        0,
        n["Instance on Points.001"],
        "Instance",
        0,
    )
    _link(ng.links, n["Reroute.013"], "Output", 0, n["Vector Math.002"], "Vector", 0)
    _link(ng.links, n["Group Input"], "Geometry", 0, n["Reroute.004"], "Input", 0)
    _link(ng.links, n["Reroute.002"], "Output", 0, n["Reroute"], "Input", 0)
    _link(ng.links, n["Reroute.035"], "Output", 0, n["Reroute.001"], "Input", 0)
    _link(ng.links, n["Reroute.001"], "Output", 0, n["Reroute.015"], "Input", 0)
    _link(ng.links, n["Reroute.004"], "Output", 0, n["Reroute.011"], "Input", 0)
    _link(
        ng.links,
        n["Group Input.003"],
        "Merge Distance",
        0,
        n["Merge by Distance"],
        "Distance",
        0,
    )
    _link(ng.links, n["Reroute.034"], "Output", 0, n["Reroute.014"], "Input", 0)
    _link(ng.links, n["Switch.005"], "Output", 0, n["Group Output"], "Geometry", 0)
    _link(
        ng.links,
        n["Group Input.008"],
        "Flip Direciton",
        0,
        n["Switch.008"],
        "Switch",
        0,
    )
    _link(ng.links, n["Reroute.018"], "Output", 0, n["Switch.008"], "False", 0)
    _link(ng.links, n["Reroute.036"], "Output", 0, n["Math.001"], "Value", 1)
    _link(ng.links, n["Math.001"], "Value", 0, n["Switch.008"], "True", 0)
    _link(ng.links, n["Switch.008"], "Output", 0, n["Vector Math.001"], "Scale", 0)
    _link(
        ng.links,
        n["Group Input"],
        "Spacing / Total distance",
        0,
        n["Reroute.016"],
        "Input",
        0,
    )
    _link(ng.links, n["Reroute.016"], "Output", 0, n["Reroute.017"], "Input", 0)
    _link(ng.links, n["Reroute.036"], "Output", 0, n["Reroute.018"], "Input", 0)
    _link(
        ng.links,
        n["Euler to Rotation"],
        "Rotation",
        0,
        n["Rotate Instances"],
        "Rotation",
        0,
    )


def build_array_node_group(name: str = ARRAY_NODE_GROUP):
    """Build the linear-array group in code (idempotent).

    Reuses an existing group of the same name, rebuilding it in place when the
    stored version is stale -- so modifiers already bound to that name (including
    ones bound to the old binary asset) upgrade without rebinding. Returns the
    node group.
    """
    ng = bpy.data.node_groups.get(name)
    if ng is None:
        ng = bpy.data.node_groups.new(name, "GeometryNodeTree")

    # Offer it in the Add Modifier > Geometry Nodes picker (off by default for
    # API-created groups).
    ng.is_modifier = True

    if ng.get("cad_array_version") == ARRAY_VERSION:
        return ng

    saved = _snapshot_modifier_inputs(ng)
    ng.nodes.clear()
    ng.links.clear()
    ng.interface.clear()
    _skips.clear()
    _build_graph(ng)
    if _skips:
        print("CAD Sketcher array build: unresolved sockets:\n  " + "\n  ".join(_skips))
    _restore_modifier_inputs(ng, saved)
    ng["cad_array_version"] = ARRAY_VERSION
    return ng
