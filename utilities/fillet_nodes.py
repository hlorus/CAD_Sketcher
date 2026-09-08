"""Generic ``CAD Sketcher Fillet`` geometry-nodes modifier.

Rounds the corners/edges of whatever geometry it is given, via the built-in
``Mesh Bevel`` node, so it works on both a flat sketch profile (rounds the
boundary corners) and a 3D solid (rounds the edges). It reads no sketch or
constraint data -- add it after a sketch's convert modifier, on a mesh output, or
on any mesh.

Inputs: ``Amount`` (width), ``Segments`` (roundness), ``Affect`` (Auto / Vertices
/ Edges) and a ``Selection`` field to fillet only chosen elements. ``Auto`` picks
Vertices for a flat/open mesh (it has boundary edges) and Edges for a closed
solid; the same choice via a per-element ``Selection`` gives "fillet specific
edges/corners".

Limitation: a global vertex fillet rounds *every* corner, including the dense
tessellation of an arc/circle in a flat profile, and Mesh Bevel bails when the
amount exceeds the spacing there. Driving ``Selection`` (e.g. only true corners,
or an angle threshold) is the intended way to fillet specific elements.
"""

import bpy

FILLET_NODE_GROUP = "CAD Sketcher Fillet"
FILLET_VERSION = 2  # rebuilt on Mesh Bevel (was the curve-fillet pipeline)

# ``Affect`` values. An int, not a menu socket: menu sockets don't evaluate
# reliably as modifier inputs on Blender 5.0/5.1 (see boolean_nodes).
AFFECT_AUTO, AFFECT_VERTICES, AFFECT_EDGES = 0, 1, 2


def _compare(nodes, links, data_type, operation, a_socket, b_value):
    cmp = nodes.new("FunctionNodeCompare")
    cmp.data_type = data_type
    cmp.operation = operation
    socket_type = "INT" if data_type == "INT" else "VALUE"
    ins = [s for s in cmp.inputs if s.enabled and s.type == socket_type]
    links.new(a_socket, ins[0])
    ins[1].default_value = b_value
    return cmp.outputs["Result"]


def _bool(nodes, links, operation, a, b):
    node = nodes.new("FunctionNodeBooleanMath")
    node.operation = operation
    links.new(a, node.inputs[0])
    links.new(b, node.inputs[1])
    return node.outputs["Boolean"]


def _bevel(nodes, links, geometry, selection, amount, segments, affect_kind):
    """One Mesh Bevel branch with a round profile (a fillet, not a chamfer)."""
    node = nodes.new("GeometryNodeMeshBevel")
    node.inputs["Affect Kind"].default_value = affect_kind  # "Vertices" | "Edges"
    if "Shape" in [s.name for s in node.inputs]:
        node.inputs["Shape"].default_value = 0.5  # round arc
    links.new(geometry, node.inputs["Mesh"])
    links.new(selection, node.inputs["Selection"])
    links.new(amount, node.inputs["Offset"])
    links.new(segments, node.inputs["Segments"])
    return node.outputs["Mesh"]


def build_fillet_node_group(name: str = FILLET_NODE_GROUP):
    """Build the generic fillet group (idempotent, version-gated)."""
    ng = bpy.data.node_groups.get(name)
    if ng is None:
        ng = bpy.data.node_groups.new(name, "GeometryNodeTree")

    ng.is_modifier = True

    if ng.get("cad_fillet_version") == FILLET_VERSION:
        return ng
    ng.nodes.clear()
    ng.links.clear()
    ng.interface.clear()

    iface = ng.interface
    iface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    amount = iface.new_socket("Amount", in_out="INPUT", socket_type="NodeSocketFloat")
    amount.default_value = 0.1
    amount.min_value = 0.0
    try:
        amount.subtype = "DISTANCE"
    except Exception:
        pass
    segments = iface.new_socket("Segments", in_out="INPUT", socket_type="NodeSocketInt")
    segments.default_value = 4
    segments.min_value = 1
    segments.description = "Segments per rounded corner/edge"
    affect = iface.new_socket("Affect", in_out="INPUT", socket_type="NodeSocketInt")
    affect.default_value = AFFECT_AUTO
    affect.min_value = 0
    affect.max_value = 2
    affect.description = (
        "0 = Auto (corners on a flat profile, edges on a solid), "
        "1 = Vertices, 2 = Edges"
    )
    selection = iface.new_socket(
        "Selection", in_out="INPUT", socket_type="NodeSocketBool"
    )
    selection.default_value = True
    selection.description = "Fillet only the selected corners/edges"
    iface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    nodes, links = ng.nodes, ng.links
    gi = nodes.new("NodeGroupInput")
    go = nodes.new("NodeGroupOutput")

    geo = gi.outputs["Geometry"]
    sel = gi.outputs["Selection"]
    amt = gi.outputs["Amount"]
    seg = gi.outputs["Segments"]

    # Two branches; the Switch below evaluates only the one it selects.
    verts = _bevel(nodes, links, geo, sel, amt, seg, "Vertices")
    edges = _bevel(nodes, links, geo, sel, amt, seg, "Edges")

    # Auto-detect flatness: a flat/open mesh has at least one boundary edge (an
    # edge touching fewer than two faces); a closed solid has none.
    neighbors = nodes.new("GeometryNodeInputMeshEdgeNeighbors")
    stat = nodes.new("GeometryNodeAttributeStatistic")
    stat.data_type = "FLOAT"
    stat.domain = "EDGE"
    links.new(geo, stat.inputs["Geometry"])
    links.new(neighbors.outputs["Face Count"], stat.inputs["Attribute"])
    is_flat = _compare(nodes, links, "FLOAT", "LESS_THAN", stat.outputs["Min"], 2.0)

    # use_vertices = (Affect == Vertices) or (Affect == Auto and is_flat)
    eq_vertices = _compare(
        nodes, links, "INT", "EQUAL", gi.outputs["Affect"], AFFECT_VERTICES
    )
    eq_auto = _compare(nodes, links, "INT", "EQUAL", gi.outputs["Affect"], AFFECT_AUTO)
    auto_vertices = _bool(nodes, links, "AND", eq_auto, is_flat)
    use_vertices = _bool(nodes, links, "OR", eq_vertices, auto_vertices)

    switch = nodes.new("GeometryNodeSwitch")
    switch.input_type = "GEOMETRY"
    links.new(use_vertices, switch.inputs["Switch"])
    links.new(edges, switch.inputs["False"])
    links.new(verts, switch.inputs["True"])
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
