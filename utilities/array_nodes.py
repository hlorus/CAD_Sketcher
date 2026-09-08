"""Code-built ``CAD Sketcher Linear Array`` node group (was a binary asset).

``build_array_node_group`` rebuilds the linear-array group in code, replacing the
copy that used to ship in ``resources/assets.blend`` -- mirroring the boolean,
convert, extrude and revolve groups. The graph is a faithful transcription of the
shipped asset (identical nodes, socket defaults and links, reroutes kept, cosmetic
frames dropped), so the evaluated output is unchanged.
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

    nodes, links = ng.nodes, ng.links
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
    x.operation = "SCALE"
    x.inputs[3].default_value = -1.0
    x = nodes.new("NodeReroute")
    x.name = "Reroute.022"
    n["Reroute.022"] = x
    x.socket_idname = "NodeSocketVectorEuler"
    x = nodes.new("NodeReroute")
    x.name = "Reroute.023"
    n["Reroute.023"] = x
    x.socket_idname = "NodeSocketVectorEuler"
    x = nodes.new("NodeReroute")
    x.name = "Reroute.034"
    n["Reroute.034"] = x
    x.socket_idname = "NodeSocketVector"
    x = nodes.new("NodeReroute")
    x.name = "Reroute.024"
    n["Reroute.024"] = x
    x.socket_idname = "NodeSocketVector"
    x = nodes.new("NodeReroute")
    x.name = "Reroute.035"
    n["Reroute.035"] = x
    x.socket_idname = "NodeSocketVector"
    x = nodes.new("NodeReroute")
    x.name = "Reroute"
    n["Reroute"] = x
    x.socket_idname = "NodeSocketGeometry"
    x = nodes.new("NodeReroute")
    x.name = "Reroute.001"
    n["Reroute.001"] = x
    x.socket_idname = "NodeSocketVector"
    x = nodes.new("NodeReroute")
    x.name = "Reroute.015"
    n["Reroute.015"] = x
    x.socket_idname = "NodeSocketVector"
    x = nodes.new("NodeReroute")
    x.name = "Reroute.004"
    n["Reroute.004"] = x
    x.socket_idname = "NodeSocketGeometry"
    x = nodes.new("ShaderNodeSeparateXYZ")
    x.name = "Separate XYZ.001"
    n["Separate XYZ.001"] = x
    x = nodes.new("GeometryNodeInputPosition")
    x.name = "Position.001"
    n["Position.001"] = x
    x = nodes.new("NodeReroute")
    x.name = "Reroute.011"
    n["Reroute.011"] = x
    x.socket_idname = "NodeSocketGeometry"
    x = nodes.new("ShaderNodeMath")
    x.name = "Math"
    n["Math"] = x
    x.operation = "SUBTRACT"
    x = nodes.new("ShaderNodeMath")
    x.name = "Math.004"
    n["Math.004"] = x
    x.operation = "DIVIDE"
    x.inputs[1].default_value = 2.0
    x = nodes.new("ShaderNodeMath")
    x.name = "Math.005"
    n["Math.005"] = x
    x.use_clamp = True
    x = nodes.new("NodeReroute")
    x.name = "Reroute.005"
    n["Reroute.005"] = x
    x.socket_idname = "NodeSocketFloat"
    x = nodes.new("NodeReroute")
    x.name = "Reroute.006"
    n["Reroute.006"] = x
    x.socket_idname = "NodeSocketFloat"
    x = nodes.new("ShaderNodeMath")
    x.name = "Math.008"
    n["Math.008"] = x
    x.operation = "MULTIPLY"
    x.inputs[1].default_value = -1.0
    x = nodes.new("ShaderNodeMath")
    x.name = "Math.002"
    n["Math.002"] = x
    x.operation = "SUBTRACT"
    x = nodes.new("GeometryNodeAttributeStatistic")
    x.name = "Attribute Statistic.002"
    n["Attribute Statistic.002"] = x
    x = nodes.new("ShaderNodeMath")
    x.name = "Math.009"
    n["Math.009"] = x
    x.operation = "DIVIDE"
    x.inputs[1].default_value = 2.0
    x = nodes.new("ShaderNodeMath")
    x.name = "Math.010"
    n["Math.010"] = x
    x = nodes.new("NodeReroute")
    x.name = "Reroute.007"
    n["Reroute.007"] = x
    x.socket_idname = "NodeSocketFloat"
    x = nodes.new("NodeReroute")
    x.name = "Reroute.008"
    n["Reroute.008"] = x
    x.socket_idname = "NodeSocketFloat"
    x = nodes.new("ShaderNodeMath")
    x.name = "Math.003"
    n["Math.003"] = x
    x.operation = "SUBTRACT"
    x = nodes.new("GeometryNodeAttributeStatistic")
    x.name = "Attribute Statistic.003"
    n["Attribute Statistic.003"] = x
    x = nodes.new("ShaderNodeMath")
    x.name = "Math.017"
    n["Math.017"] = x
    x.operation = "DIVIDE"
    x.inputs[1].default_value = 2.0
    x = nodes.new("ShaderNodeMath")
    x.name = "Math.018"
    n["Math.018"] = x
    x = nodes.new("NodeReroute")
    x.name = "Reroute.009"
    n["Reroute.009"] = x
    x.socket_idname = "NodeSocketFloat"
    x = nodes.new("NodeReroute")
    x.name = "Reroute.010"
    n["Reroute.010"] = x
    x.socket_idname = "NodeSocketFloat"
    x = nodes.new("ShaderNodeMath")
    x.name = "Math.019"
    n["Math.019"] = x
    x.operation = "MULTIPLY"
    x.inputs[1].default_value = -1.0
    x = nodes.new("GeometryNodeAttributeStatistic")
    x.name = "Attribute Statistic.001"
    n["Attribute Statistic.001"] = x
    x = nodes.new("ShaderNodeMath")
    x.name = "Math.012"
    n["Math.012"] = x
    x.operation = "MULTIPLY"
    x.inputs[1].default_value = -1.0
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
    x.boolean = True
    x = nodes.new("FunctionNodeInputBool")
    x.name = "Boolean.001"
    n["Boolean.001"] = x
    x = nodes.new("FunctionNodeInputBool")
    x.name = "Boolean.002"
    n["Boolean.002"] = x
    x.boolean = True
    x = nodes.new("NodeReroute")
    x.name = "Reroute.012"
    n["Reroute.012"] = x
    x.socket_idname = "NodeSocketVector"
    x = nodes.new("NodeReroute")
    x.name = "Reroute.013"
    n["Reroute.013"] = x
    x.socket_idname = "NodeSocketVector"
    x = nodes.new("ShaderNodeCombineXYZ")
    x.name = "Combine XYZ"
    n["Combine XYZ"] = x
    x = nodes.new("GeometryNodeTransform")
    x.name = "Transform"
    n["Transform"] = x
    x = nodes.new("NodeReroute")
    x.name = "Reroute.028"
    n["Reroute.028"] = x
    x.socket_idname = "NodeSocketInt"
    x = nodes.new("NodeReroute")
    x.name = "Reroute.003"
    n["Reroute.003"] = x
    x.socket_idname = "NodeSocketGeometry"
    x = nodes.new("ShaderNodeVectorMath")
    x.name = "Vector Math.001"
    n["Vector Math.001"] = x
    x.operation = "SCALE"
    x = nodes.new("NodeReroute")
    x.name = "Reroute.031"
    n["Reroute.031"] = x
    x.socket_idname = "NodeSocketVector"
    x = nodes.new("NodeReroute")
    x.name = "Reroute.029"
    n["Reroute.029"] = x
    x.socket_idname = "NodeSocketInt"
    x = nodes.new("GeometryNodeMeshLine")
    x.name = "Mesh Line.002"
    n["Mesh Line.002"] = x
    x = nodes.new("GeometryNodeMeshLine")
    x.name = "Mesh Line.003"
    n["Mesh Line.003"] = x
    x.mode = "END_POINTS"
    x = nodes.new("NodeReroute")
    x.name = "Reroute.033"
    n["Reroute.033"] = x
    x.socket_idname = "NodeSocketVector"
    x = nodes.new("NodeReroute")
    x.name = "Reroute.032"
    n["Reroute.032"] = x
    x.socket_idname = "NodeSocketVector"
    x = nodes.new("NodeReroute")
    x.name = "Reroute.030"
    n["Reroute.030"] = x
    x.socket_idname = "NodeSocketInt"
    x = nodes.new("NodeReroute")
    x.name = "Reroute.020"
    n["Reroute.020"] = x
    x.socket_idname = "NodeSocketGeometry"
    x = nodes.new("FunctionNodeAlignEulerToVector")
    x.name = "Align Euler to Vector"
    n["Align Euler to Vector"] = x
    x = nodes.new("GeometryNodeInstanceOnPoints")
    x.name = "Instance on Points.001"
    n["Instance on Points.001"] = x
    x = nodes.new("GeometryNodeSwitch")
    x.name = "Switch.002"
    n["Switch.002"] = x
    x.input_type = "GEOMETRY"
    x = nodes.new("GeometryNodeRotateInstances")
    x.name = "Rotate Instances"
    n["Rotate Instances"] = x
    x = nodes.new("NodeGroupInput")
    x.name = "Group Input.001"
    n["Group Input.001"] = x
    x = nodes.new("GeometryNodeSwitch")
    x.name = "Switch"
    n["Switch"] = x
    x.input_type = "GEOMETRY"
    x = nodes.new("GeometryNodeRealizeInstances")
    x.name = "Realize Instances"
    n["Realize Instances"] = x
    x.realize_to_point_domain = True
    x = nodes.new("NodeGroupInput")
    x.name = "Group Input.002"
    n["Group Input.002"] = x
    x = nodes.new("GeometryNodeSwitch")
    x.name = "Switch.001"
    n["Switch.001"] = x
    x.input_type = "GEOMETRY"
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
    x.socket_idname = "NodeSocketVector"
    x = nodes.new("NodeReroute")
    x.name = "Reroute.027"
    n["Reroute.027"] = x
    x.socket_idname = "NodeSocketVector"
    x = nodes.new("NodeReroute")
    x.name = "Reroute.019"
    n["Reroute.019"] = x
    x.socket_idname = "NodeSocketGeometry"
    x = nodes.new("NodeGroupInput")
    x.name = "Group Input.005"
    n["Group Input.005"] = x
    x = nodes.new("GeometryNodeJoinGeometry")
    x.name = "Join Geometry"
    n["Join Geometry"] = x
    x = nodes.new("GeometryNodeSwitch")
    x.name = "Switch.005"
    n["Switch.005"] = x
    x.input_type = "GEOMETRY"
    x = nodes.new("GeometryNodeSetPosition")
    x.name = "Set Position.001"
    n["Set Position.001"] = x
    x = nodes.new("NodeReroute")
    x.name = "Reroute.002"
    n["Reroute.002"] = x
    x.socket_idname = "NodeSocketGeometry"
    x = nodes.new("GeometryNodeSwitch")
    x.name = "Switch.003"
    n["Switch.003"] = x
    x.input_type = "GEOMETRY"
    x = nodes.new("NodeGroupInput")
    x.name = "Group Input.007"
    n["Group Input.007"] = x
    x = nodes.new("NodeGroupInput")
    x.name = "Group Input.008"
    n["Group Input.008"] = x
    x = nodes.new("ShaderNodeMath")
    x.name = "Math.001"
    n["Math.001"] = x
    x.operation = "MULTIPLY"
    x.inputs[0].default_value = -1.0
    x = nodes.new("NodeReroute")
    x.name = "Reroute.016"
    n["Reroute.016"] = x
    x.socket_idname = "NodeSocketFloat"
    x = nodes.new("NodeReroute")
    x.name = "Reroute.017"
    n["Reroute.017"] = x
    x.socket_idname = "NodeSocketFloat"
    x = nodes.new("NodeReroute")
    x.name = "Reroute.036"
    n["Reroute.036"] = x
    x.socket_idname = "NodeSocketFloat"
    x = nodes.new("ShaderNodeVectorMath")
    x.name = "Vector Math"
    n["Vector Math"] = x
    x.operation = "NORMALIZE"
    x = nodes.new("GeometryNodeSwitch")
    x.name = "Switch.008"
    n["Switch.008"] = x
    x = nodes.new("NodeReroute")
    x.name = "Reroute.018"
    n["Reroute.018"] = x
    x.socket_idname = "NodeSocketFloat"
    x = nodes.new("FunctionNodeEulerToRotation")
    x.name = "Euler to Rotation"
    n["Euler to Rotation"] = x

    links.new(n["Switch.002"].outputs[0], n["Realize Instances"].inputs[0])
    links.new(n["Realize Instances"].outputs[0], n["Switch"].inputs[2])
    links.new(n["Switch.002"].outputs[0], n["Switch"].inputs[1])
    links.new(n["Switch"].outputs[0], n["Merge by Distance"].inputs[0])
    links.new(n["Merge by Distance"].outputs[0], n["Switch.001"].inputs[2])
    links.new(n["Switch"].outputs[0], n["Switch.001"].inputs[1])
    links.new(n["Instance on Points.001"].outputs[0], n["Rotate Instances"].inputs[0])
    links.new(n["Reroute.023"].outputs[0], n["Euler to Rotation"].inputs[0])
    links.new(n["Rotate Instances"].outputs[0], n["Switch.002"].inputs[2])
    links.new(n["Instance on Points.001"].outputs[0], n["Switch.002"].inputs[1])
    links.new(n["Reroute.015"].outputs[0], n["Align Euler to Vector"].inputs[2])
    links.new(n["Vector Math"].outputs[0], n["Vector Math.001"].inputs[0])
    links.new(n["Mesh Line.003"].outputs[0], n["Switch.003"].inputs[2])
    links.new(n["Mesh Line.002"].outputs[0], n["Switch.003"].inputs[1])
    links.new(n["Reroute.032"].outputs[0], n["Mesh Line.002"].inputs[3])
    links.new(n["Reroute.033"].outputs[0], n["Mesh Line.003"].inputs[3])
    links.new(n["Reroute.003"].outputs[0], n["Instance on Points.001"].inputs[0])
    links.new(n["Reroute.030"].outputs[0], n["Mesh Line.002"].inputs[0])
    links.new(n["Reroute.029"].outputs[0], n["Mesh Line.003"].inputs[0])
    links.new(n["Switch.001"].outputs[0], n["Set Position"].inputs[0])
    links.new(n["Reroute.014"].outputs[0], n["Set Position"].inputs[3])
    links.new(n["Reroute.019"].outputs[0], n["Switch.005"].inputs[1])
    links.new(n["Reroute.019"].outputs[0], n["Join Geometry"].inputs[0])
    links.new(n["Join Geometry"].outputs[0], n["Switch.005"].inputs[2])
    links.new(n["Set Position"].outputs[0], n["Reroute.019"].inputs[0])
    links.new(n["Switch.003"].outputs[0], n["Reroute.003"].inputs[0])
    links.new(n["Reroute.003"].outputs[0], n["Reroute.020"].inputs[0])
    links.new(n["Align Euler to Vector"].outputs[0], n["Reroute.022"].inputs[0])
    links.new(n["Reroute.022"].outputs[0], n["Reroute.023"].inputs[0])
    links.new(n["Vector Math.002"].outputs[0], n["Reroute.024"].inputs[0])
    links.new(n["Reroute.028"].outputs[0], n["Reroute.029"].inputs[0])
    links.new(n["Reroute.029"].outputs[0], n["Reroute.030"].inputs[0])
    links.new(n["Vector Math.001"].outputs[0], n["Reroute.031"].inputs[0])
    links.new(n["Reroute.031"].outputs[0], n["Reroute.032"].inputs[0])
    links.new(n["Reroute.031"].outputs[0], n["Reroute.033"].inputs[0])
    links.new(n["Reroute.027"].outputs[0], n["Set Position.001"].inputs[3])
    links.new(n["Reroute.034"].outputs[0], n["Reroute.027"].inputs[0])
    links.new(n["Reroute.024"].outputs[0], n["Reroute.034"].inputs[0])
    links.new(n["Set Position.001"].outputs[0], n["Join Geometry"].inputs[0])
    links.new(n["Reroute.020"].outputs[0], n["Reroute.002"].inputs[0])
    links.new(n["Reroute"].outputs[0], n["Set Position.001"].inputs[0])
    links.new(n["Group Input"].outputs[1], n["Reroute.035"].inputs[0])
    links.new(n["Group Input"].outputs[1], n["Vector Math"].inputs[0])
    links.new(n["Group Input"].outputs[2], n["Reroute.028"].inputs[0])
    links.new(n["Reroute.017"].outputs[0], n["Reroute.036"].inputs[0])
    links.new(n["Group Input.007"].outputs[5], n["Switch.003"].inputs[0])
    links.new(n["Group Input.001"].outputs[6], n["Switch.002"].inputs[0])
    links.new(n["Group Input.002"].outputs[9], n["Switch"].inputs[0])
    links.new(n["Group Input.003"].outputs[7], n["Switch.001"].inputs[0])
    links.new(n["Group Input.005"].outputs[10], n["Switch.005"].inputs[0])
    links.new(n["Reroute.011"].outputs[0], n["Transform"].inputs[0])
    links.new(n["Reroute.011"].outputs[0], n["Attribute Statistic.001"].inputs[0])
    links.new(n["Position.001"].outputs[0], n["Separate XYZ.001"].inputs[0])
    links.new(n["Separate XYZ.001"].outputs[0], n["Attribute Statistic.001"].inputs[2])
    links.new(n["Combine XYZ"].outputs[0], n["Transform"].inputs[2])
    links.new(n["Math"].outputs[0], n["Math.004"].inputs[0])
    links.new(n["Math.004"].outputs[0], n["Math.005"].inputs[0])
    links.new(n["Attribute Statistic.001"].outputs[3], n["Math"].inputs[1])
    links.new(n["Attribute Statistic.001"].outputs[4], n["Math"].inputs[0])
    links.new(n["Math.005"].outputs[0], n["Math.008"].inputs[0])
    links.new(n["Reroute.005"].outputs[0], n["Math.005"].inputs[1])
    links.new(n["Reroute.006"].outputs[0], n["Reroute.005"].inputs[0])
    links.new(n["Attribute Statistic.001"].outputs[3], n["Reroute.006"].inputs[0])
    links.new(n["Math.002"].outputs[0], n["Math.009"].inputs[0])
    links.new(n["Math.009"].outputs[0], n["Math.010"].inputs[0])
    links.new(n["Attribute Statistic.002"].outputs[3], n["Math.002"].inputs[1])
    links.new(n["Attribute Statistic.002"].outputs[4], n["Math.002"].inputs[0])
    links.new(n["Math.010"].outputs[0], n["Math.012"].inputs[0])
    links.new(n["Reroute.007"].outputs[0], n["Math.010"].inputs[1])
    links.new(n["Reroute.008"].outputs[0], n["Reroute.007"].inputs[0])
    links.new(n["Attribute Statistic.002"].outputs[3], n["Reroute.008"].inputs[0])
    links.new(n["Math.003"].outputs[0], n["Math.017"].inputs[0])
    links.new(n["Math.017"].outputs[0], n["Math.018"].inputs[0])
    links.new(n["Attribute Statistic.003"].outputs[3], n["Math.003"].inputs[1])
    links.new(n["Attribute Statistic.003"].outputs[4], n["Math.003"].inputs[0])
    links.new(n["Math.018"].outputs[0], n["Math.019"].inputs[0])
    links.new(n["Reroute.009"].outputs[0], n["Math.018"].inputs[1])
    links.new(n["Reroute.010"].outputs[0], n["Reroute.009"].inputs[0])
    links.new(n["Attribute Statistic.003"].outputs[3], n["Reroute.010"].inputs[0])
    links.new(n["Separate XYZ.001"].outputs[1], n["Attribute Statistic.002"].inputs[2])
    links.new(n["Separate XYZ.001"].outputs[2], n["Attribute Statistic.003"].inputs[2])
    links.new(n["Reroute.011"].outputs[0], n["Attribute Statistic.002"].inputs[0])
    links.new(n["Reroute.011"].outputs[0], n["Attribute Statistic.003"].inputs[0])
    links.new(n["Combine XYZ"].outputs[0], n["Reroute.012"].inputs[0])
    links.new(n["Math.008"].outputs[0], n["Switch.004"].inputs[2])
    links.new(n["Math.012"].outputs[0], n["Switch.006"].inputs[2])
    links.new(n["Math.019"].outputs[0], n["Switch.007"].inputs[2])
    links.new(n["Switch.007"].outputs[0], n["Combine XYZ"].inputs[2])
    links.new(n["Switch.006"].outputs[0], n["Combine XYZ"].inputs[1])
    links.new(n["Switch.004"].outputs[0], n["Combine XYZ"].inputs[0])
    links.new(n["Reroute.012"].outputs[0], n["Reroute.013"].inputs[0])
    links.new(n["Boolean"].outputs[0], n["Switch.004"].inputs[0])
    links.new(n["Boolean.002"].outputs[0], n["Switch.007"].inputs[0])
    links.new(n["Boolean.001"].outputs[0], n["Switch.006"].inputs[0])
    links.new(n["Transform"].outputs[0], n["Instance on Points.001"].inputs[2])
    links.new(n["Reroute.013"].outputs[0], n["Vector Math.002"].inputs[0])
    links.new(n["Group Input"].outputs[0], n["Reroute.004"].inputs[0])
    links.new(n["Reroute.002"].outputs[0], n["Reroute"].inputs[0])
    links.new(n["Reroute.035"].outputs[0], n["Reroute.001"].inputs[0])
    links.new(n["Reroute.001"].outputs[0], n["Reroute.015"].inputs[0])
    links.new(n["Reroute.004"].outputs[0], n["Reroute.011"].inputs[0])
    links.new(n["Group Input.003"].outputs[8], n["Merge by Distance"].inputs[3])
    links.new(n["Reroute.034"].outputs[0], n["Reroute.014"].inputs[0])
    links.new(n["Switch.005"].outputs[0], n["Group Output"].inputs[0])
    links.new(n["Group Input.008"].outputs[4], n["Switch.008"].inputs[0])
    links.new(n["Reroute.018"].outputs[0], n["Switch.008"].inputs[1])
    links.new(n["Reroute.036"].outputs[0], n["Math.001"].inputs[1])
    links.new(n["Math.001"].outputs[0], n["Switch.008"].inputs[2])
    links.new(n["Switch.008"].outputs[0], n["Vector Math.001"].inputs[3])
    links.new(n["Group Input"].outputs[3], n["Reroute.016"].inputs[0])
    links.new(n["Reroute.016"].outputs[0], n["Reroute.017"].inputs[0])
    links.new(n["Reroute.036"].outputs[0], n["Reroute.018"].inputs[0])
    links.new(n["Euler to Rotation"].outputs[0], n["Rotate Instances"].inputs[2])


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
    _build_graph(ng)
    _restore_modifier_inputs(ng, saved)
    ng["cad_array_version"] = ARRAY_VERSION
    return ng
