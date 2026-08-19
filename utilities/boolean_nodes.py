"""Nondestructive boolean node group.

Since sketches are native Curves objects (the mesh is produced by the convert
Geometry Nodes modifier), they are not mesh-type objects and Blender's Boolean
*modifier* refuses them as operands. This ships an equivalent operation as a
Geometry Nodes group that reads the cutter through an ``Object Info`` node, so it
consumes the cutter's *evaluated* mesh (including a sketch's generated fill, or a
sketch that has been extruded/revolved into a solid) while both objects stay
fully editable.

The group lives on the *body* being cut. Pick the cutter object and the
operation (Difference / Union / Intersect) in the modifier. Like the other CAD
Sketcher node groups it is built programmatically so it is versioned in code
rather than shipped as a binary asset, and rebuilt in place when
``BOOLEAN_VERSION`` changes.

The cutter must already be a solid: a flat 2D sketch fill has no volume, so
extrude or revolve it into a solid first (matching the composable extrude /
revolve / array node tools).
"""

import bpy

BOOLEAN_NODE_GROUP = "CAD Sketcher Boolean"

# Bump whenever the built tree changes so groups baked into existing files are
# rebuilt in place on load, keeping modifiers bound to the same name.
BOOLEAN_VERSION = 1

# Menu items, in node/enum order. The interface menu default is the first.
_OPERATIONS = ("Difference", "Union", "Intersect")
_OP_TO_NODE = {
    "Difference": "DIFFERENCE",
    "Union": "UNION",
    "Intersect": "INTERSECT",
}


def _geometry_sockets(node):
    """Return (single-input, multi-input) geometry sockets of a boolean node.

    The Mesh Boolean node's socket layout depends on its operation (Difference
    exposes ``Mesh 1`` + ``Mesh 2``; Union/Intersect expose ``Mesh 1`` + a
    multi-input ``Mesh``), so wire by socket role rather than by name.
    """
    single = [s for s in node.inputs if s.type == "GEOMETRY" and not s.is_multi_input]
    multi = [s for s in node.inputs if s.type == "GEOMETRY" and s.is_multi_input]
    return single, multi


def build_boolean_node_group(name: str = BOOLEAN_NODE_GROUP):
    """Build the nondestructive boolean group (idempotent).

    Reuses an existing group of the same name, rebuilding it in place when the
    stored version is stale so modifiers already bound to that name upgrade
    without rebinding. Returns the node group.
    """
    ng = bpy.data.node_groups.get(name)
    if ng is not None:
        if ng.get("cad_boolean_version") == BOOLEAN_VERSION:
            return ng
        ng.nodes.clear()
        ng.links.clear()
        ng.interface.clear()
    else:
        ng = bpy.data.node_groups.new(name, "GeometryNodeTree")

    iface = ng.interface
    iface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    iface.new_socket("Cutter", in_out="INPUT", socket_type="NodeSocketObject")
    operation = iface.new_socket(
        "Operation", in_out="INPUT", socket_type="NodeSocketMenu"
    )
    self_intersection = iface.new_socket(
        "Self Intersection", in_out="INPUT", socket_type="NodeSocketBool"
    )
    iface.new_socket("Hole Tolerant", in_out="INPUT", socket_type="NodeSocketBool")
    # Robust default: sketch fills welded by identity can leave shared boundary
    # points, so keep self-intersection handling on.
    self_intersection.default_value = True
    iface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    nodes, links = ng.nodes, ng.links
    gi = nodes.new("NodeGroupInput")
    go = nodes.new("NodeGroupOutput")

    # Pull the cutter's *evaluated* geometry in the body's local space, so the
    # boolean is correct regardless of either object's transform, and follows the
    # cutter's own modifiers (a sketch's fill, or its extrude/revolve).
    cutter = nodes.new("GeometryNodeObjectInfo")
    cutter.transform_space = "RELATIVE"
    links.new(gi.outputs["Cutter"], cutter.inputs["Object"])
    cutter_geo = cutter.outputs["Geometry"]
    body_geo = gi.outputs["Geometry"]

    def make_boolean(op_node):
        node = nodes.new("GeometryNodeMeshBoolean")
        node.solver = "EXACT"
        node.operation = op_node
        single, multi = _geometry_sockets(node)
        # Body is the primary operand; the cutter is the other. This is uniform
        # across operations (Difference: Mesh 1 / Mesh 2; Union & Intersect:
        # Mesh 1 / Mesh), so a fully-contained cutter unions/intersects correctly.
        links.new(body_geo, single[0])
        links.new(cutter_geo, multi[0])
        for socket in node.inputs:
            if socket.name == "Self Intersection":
                links.new(gi.outputs["Self Intersection"], socket)
            elif socket.name == "Hole Tolerant":
                links.new(gi.outputs["Hole Tolerant"], socket)
        return node

    # Only the branch the Menu Switch selects is evaluated, so the other two
    # boolean nodes cost nothing at runtime.
    branches = {label: make_boolean(_OP_TO_NODE[label]) for label in _OPERATIONS}

    switch = nodes.new("GeometryNodeMenuSwitch")
    switch.data_type = "GEOMETRY"
    switch.enum_items.clear()
    for label in _OPERATIONS:
        switch.enum_items.new(label)
    links.new(gi.outputs["Operation"], switch.inputs["Menu"])
    for label, node in branches.items():
        links.new(node.outputs["Mesh"], switch.inputs[label])
    links.new(switch.outputs["Output"], go.inputs["Geometry"])

    operation.default_value = _OPERATIONS[0]

    ng["cad_boolean_version"] = BOOLEAN_VERSION
    return ng
