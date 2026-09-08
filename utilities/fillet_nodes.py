"""Generic ``CAD Sketcher Fillet`` geometry-nodes modifier.

A self-contained node group that rounds the corners of whatever geometry it is
given: it recovers a curve (Mesh to Curve), rounds it (Fillet Curve), then either
re-fills it as an n-gon surface or emits it as a wire. It reads no sketch or
constraint data, so it works on any curve/mesh-wire output -- drop it after a
sketch's convert modifier, or on a mesh-output object, to round the result
non-destructively.

``Radius`` and ``Count`` are exposed as modifier inputs; ``Fill`` toggles between
a filled surface and a plain wire. The fill path normalizes spline winding first
because Fill Curve's N-gon mode is winding-sensitive (see ``_normalize_winding``).
"""

import bpy

from .convert_nodes import _normalize_winding

FILLET_NODE_GROUP = "CAD Sketcher Fillet"
FILLET_VERSION = 1


def build_fillet_node_group(name: str = FILLET_NODE_GROUP):
    """Build the generic fillet group (idempotent, version-gated).

    Reuses an existing group of the same name, rebuilding it in place when the
    stored version is stale so bound modifiers upgrade without rebinding.
    """
    ng = bpy.data.node_groups.get(name)
    if ng is None:
        ng = bpy.data.node_groups.new(name, "GeometryNodeTree")

    # Offer it in the Add Modifier > Geometry Nodes picker (off by default for
    # API-created groups).
    ng.is_modifier = True

    if ng.get("cad_fillet_version") == FILLET_VERSION:
        return ng
    ng.nodes.clear()
    ng.links.clear()
    ng.interface.clear()

    iface = ng.interface
    iface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    radius = iface.new_socket("Radius", in_out="INPUT", socket_type="NodeSocketFloat")
    radius.default_value = 0.1
    radius.min_value = 0.0
    try:
        radius.subtype = "DISTANCE"
    except Exception:
        pass
    count = iface.new_socket("Count", in_out="INPUT", socket_type="NodeSocketInt")
    count.default_value = 4
    count.min_value = 1
    count.description = "Segments per rounded corner (Bezier smoothness)"
    fill = iface.new_socket("Fill", in_out="INPUT", socket_type="NodeSocketBool")
    fill.default_value = True
    iface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    nodes, links = ng.nodes, ng.links
    gi = nodes.new("NodeGroupInput")
    go = nodes.new("NodeGroupOutput")

    to_curve = nodes.new("GeometryNodeMeshToCurve")
    links.new(gi.outputs["Geometry"], to_curve.inputs["Mesh"])

    fillet = nodes.new("GeometryNodeFilletCurve")
    # Clamp each fillet to the room between adjacent points, so a large radius on
    # densely tessellated arcs/circles can't collapse them.
    for socket in fillet.inputs:
        if socket.name == "Limit Radius":
            socket.default_value = True
    links.new(to_curve.outputs["Curve"], fillet.inputs["Curve"])
    links.new(gi.outputs["Radius"], fillet.inputs["Radius"])
    links.new(gi.outputs["Count"], fillet.inputs["Count"])

    # Fill path: pin winding (Fill Curve N-gons is winding-sensitive) then fill.
    normalized = _normalize_winding(nodes, links, fillet.outputs["Curve"])
    fill_curve = nodes.new("GeometryNodeFillCurve")
    try:
        fill_curve.inputs["Mode"].default_value = "N-gons"
    except Exception:
        pass
    links.new(normalized, fill_curve.inputs["Curve"])

    # Wire path: the rounded curve as edges (no profile -> edge-only mesh).
    wire = nodes.new("GeometryNodeCurveToMesh")
    links.new(fillet.outputs["Curve"], wire.inputs["Curve"])

    switch = nodes.new("GeometryNodeSwitch")
    switch.input_type = "GEOMETRY"
    links.new(gi.outputs["Fill"], switch.inputs["Switch"])
    links.new(wire.outputs["Mesh"], switch.inputs["False"])
    links.new(fill_curve.outputs["Mesh"], switch.inputs["True"])
    links.new(switch.outputs["Output"], go.inputs["Geometry"])

    ng["cad_fillet_version"] = FILLET_VERSION
    return ng


def fillet_input_ids(node_group) -> dict:
    """Map ``{socket name: identifier}`` for the group's inputs."""
    return {
        s.name: s.identifier
        for s in node_group.interface.items_tree
        if getattr(s, "in_out", "") == "INPUT"
    }
