"""Generic ``CAD Sketcher Fillet`` geometry-nodes modifier.

Rounds the corners/edges of whatever geometry it is given, via the built-in
``Mesh Bevel`` node, so it works on both a flat sketch profile (rounds the
boundary corners) and a 3D solid (rounds the edges). It reads no sketch or
constraint data -- add it after a sketch's convert modifier, on a mesh output, or
on any mesh.

Inputs: ``Amount`` (width), ``Segments`` (roundness), ``Affect`` (Auto / Vertices
/ Edges) and a ``Selection`` field to fillet only chosen elements. ``Auto`` picks
Vertices for a planar profile (a degenerate bounding box) and Edges for a solid;
the same choice via a per-element ``Selection`` gives "fillet specific
edges/corners".

Limitation: a global vertex fillet rounds *every* corner, including the dense
tessellation of an arc/circle in a flat profile, and Mesh Bevel bails when the
amount exceeds the spacing there. Driving ``Selection`` (e.g. only true corners,
or an angle threshold) is the intended way to fillet specific elements.
"""

import bpy

FILLET_NODE_GROUP = "CAD Sketcher Fillet"
FILLET_VERSION = 6  # fillet only the picked elements

# Picked elements live on the node group (modifiers take no custom properties):
# the indices and the domain they index.
PICKS_KEY = "cad_fillet_picks"
DOMAIN_KEY = "cad_fillet_domain"
# Which group a picked set belongs to, so a group is never shared by two
# modifiers with different picks.
OWNER_KEY = "cad_fillet_owner"

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


def _math(nodes, links, operation, a, b):
    node = nodes.new("ShaderNodeMath")
    node.operation = operation
    links.new(a, node.inputs[0])
    if hasattr(b, "bl_idname") or hasattr(b, "node"):
        links.new(b, node.inputs[1])
    else:
        node.inputs[1].default_value = b
    return node.outputs["Value"]


def _is_flat(nodes, links, geometry):
    """Boolean: is the geometry planar (min bounding-box extent ~ 0)?

    Scale-independent (compares the smallest extent to the largest) and safe on
    any geometry -- Bounding Box never errors, so this can run under Auto without
    tripping a node warning that would grey the modifier inputs.
    """
    bbox = nodes.new("GeometryNodeBoundBox")
    links.new(geometry, bbox.inputs["Geometry"])
    size = nodes.new("ShaderNodeVectorMath")
    size.operation = "SUBTRACT"
    links.new(bbox.outputs["Max"], size.inputs[0])
    links.new(bbox.outputs["Min"], size.inputs[1])
    sep = nodes.new("ShaderNodeSeparateXYZ")
    links.new(size.outputs["Vector"], sep.inputs["Vector"])
    max_extent = _math(
        nodes,
        links,
        "MAXIMUM",
        sep.outputs["X"],
        _math(nodes, links, "MAXIMUM", sep.outputs["Y"], sep.outputs["Z"]),
    )
    min_extent = _math(
        nodes,
        links,
        "MINIMUM",
        sep.outputs["X"],
        _math(nodes, links, "MINIMUM", sep.outputs["Y"], sep.outputs["Z"]),
    )
    threshold = _math(nodes, links, "MULTIPLY", max_extent, 1e-3)
    cmp = nodes.new("FunctionNodeCompare")
    cmp.data_type = "FLOAT"
    cmp.operation = "LESS_THAN"
    ins = [s for s in cmp.inputs if s.enabled and s.type == "VALUE"]
    links.new(min_extent, ins[0])
    links.new(threshold, ins[1])
    return cmp.outputs["Result"]


# Mesh Bevel's width comes from the four per-side offsets, not the "Offset"
# input -- "Offset" only mirrors into them when set as a node default, so a
# *linked* Offset is ignored (Amount then had no effect). Drive the per-sides.
_BEVEL_OFFSETS = (
    "Start Left Offset",
    "Start Right Offset",
    "End Left Offset",
    "End Right Offset",
)


def _bevel(nodes, links, geometry, selection, amount, segments, affect_kind):
    """One Mesh Bevel branch with a round profile (a fillet, not a chamfer)."""
    node = nodes.new("GeometryNodeMeshBevel")
    node.inputs["Affect Kind"].default_value = affect_kind  # "Vertices" | "Edges"
    if "Shape" in [s.name for s in node.inputs]:
        node.inputs["Shape"].default_value = 0.5  # round arc
    links.new(geometry, node.inputs["Mesh"])
    links.new(selection, node.inputs["Selection"])
    names = [s.name for s in node.inputs]
    for side in _BEVEL_OFFSETS:
        if side in names:
            links.new(amount, node.inputs[side])
    # Keep Offset driven too for any build/mode that reads it directly.
    if "Offset" in names:
        links.new(amount, node.inputs["Offset"])
    links.new(segments, node.inputs["Segments"])
    return node.outputs["Mesh"]


def _value_sockets(node_group):
    return [
        item
        for item in node_group.interface.items_tree
        if getattr(item, "item_type", "") == "SOCKET"
        and getattr(item, "in_out", "") == "INPUT"
        and item.socket_type != "NodeSocketGeometry"
    ]


def _snapshot_modifier_inputs(node_group):
    """Input values of every modifier using ``node_group``, keyed by socket name.

    A rebuild re-mints the socket identifiers modifier inputs are keyed by, so
    without this the picks would reset Amount/Segments to 0 (see the node-group
    rebuild note in CONTRIBUTING).
    """
    from ..operators.modifiers import get_modifier_input

    saved = []
    for obj in bpy.data.objects:
        for mod in obj.modifiers:
            if getattr(mod, "type", None) != "NODES" or mod.node_group != node_group:
                continue
            values = {}
            for item in _value_sockets(node_group):
                try:
                    values[item.name] = get_modifier_input(mod, item.identifier)
                except Exception:
                    pass
            saved.append((mod, values))
    return saved


def _restore_modifier_inputs(node_group, saved) -> None:
    """Re-apply values from :func:`_snapshot_modifier_inputs` by socket name."""
    from ..operators.modifiers import set_modifier_input

    for mod, values in saved:
        for item in _value_sockets(node_group):
            value = values.get(item.name, item.default_value)
            try:
                set_modifier_input(mod, item.identifier, value)
            except Exception:
                pass


def _picked_selection(nodes, links, picks, base_selection):
    """Boolean: the element is one of ``picks`` (and passes ``base_selection``).

    The picks are element indices, so this is an OR of index comparisons -- the
    tool writes what the user clicked, no rule to author.
    """
    index = nodes.new("GeometryNodeInputIndex")
    matched = None
    for pick in picks:
        eq = _compare(nodes, links, "INT", "EQUAL", index.outputs["Index"], int(pick))
        matched = eq if matched is None else _bool(nodes, links, "OR", matched, eq)
    return _bool(nodes, links, "AND", base_selection, matched)


def build_fillet_node_group(name: str = FILLET_NODE_GROUP, picks=()):
    """Build the generic fillet group (idempotent, version-gated).

    ``picks`` are element indices to fillet; empty fillets everything the
    ``Selection`` input allows.
    """
    ng = bpy.data.node_groups.get(name)
    if ng is None:
        ng = bpy.data.node_groups.new(name, "GeometryNodeTree")

    ng.is_modifier = True

    picks = [int(p) for p in picks]
    if (
        ng.get("cad_fillet_version") == FILLET_VERSION
        and list(ng.get(PICKS_KEY, [])) == picks
    ):
        return ng

    saved = _snapshot_modifier_inputs(ng)
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

    if picks:
        sel = _picked_selection(nodes, links, picks, sel)

    # Two branches; the Switch below evaluates only the one it selects.
    verts = _bevel(nodes, links, geo, sel, amt, seg, "Vertices")
    edges = _bevel(nodes, links, geo, sel, amt, seg, "Edges")

    # Auto-detect flatness from the bounding box: a flat profile is degenerate
    # along one axis (min extent ~ 0), a solid has volume in all three. Bounding
    # Box works on any geometry and never errors -- unlike mesh-only probes
    # (Edge Neighbors / Attribute Statistic), which warn on a curve/non-mesh input;
    # because Auto is the only Affect value that evaluates the detection (the
    # others constant-fold it away), that warning greyed the inputs at Affect=0.
    is_flat = _is_flat(nodes, links, geo)

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
    ng[PICKS_KEY] = picks
    _restore_modifier_inputs(ng, saved)
    return ng


def get_picks(modifier) -> list:
    """Element indices the modifier fillets (empty = all)."""
    group = modifier.node_group
    return [int(i) for i in group.get(PICKS_KEY, [])] if group else []


def get_domain(modifier) -> str:
    """Domain the picks index: ``EDGE`` or ``POINT``."""
    group = modifier.node_group
    return group.get(DOMAIN_KEY, "EDGE") if group else "EDGE"


def set_picks(modifier, picks, domain: str = "EDGE"):
    """Store the picked elements and rebuild the modifier's group around them.

    Each modifier with picks gets its own group: the picks live in the node tree
    (as index comparisons), so a shared group would apply one object's picks to
    another's.
    """
    picks = sorted({int(p) for p in picks})
    owner = f"{modifier.id_data.name}/{modifier.name}" if modifier.id_data else ""

    if not picks:
        # Nothing picked: back to the shared group, which fillets everything.
        modifier.node_group = build_fillet_node_group()
        return modifier.node_group

    group = modifier.node_group
    if group is None or group.get(OWNER_KEY) != owner:
        group = build_fillet_node_group().copy()
        group.name = f"{FILLET_NODE_GROUP} {owner}"
        group[OWNER_KEY] = owner
        # A copy carries the shared group's version; force the rebuild below.
        group["cad_fillet_version"] = -1

    group = build_fillet_node_group(group.name, picks)
    group[DOMAIN_KEY] = domain
    group[OWNER_KEY] = owner
    modifier.node_group = group
    set_affect_for_domain(modifier, domain)
    return group


def set_affect_for_domain(modifier, domain: str):
    """Point ``Affect`` at the domain the picks index."""
    from ..operators.modifiers import set_modifier_input

    group = modifier.node_group
    if group is None:
        return
    affect = AFFECT_VERTICES if domain == "POINT" else AFFECT_EDGES
    ids = fillet_input_ids(group)
    if "Affect" in ids:
        set_modifier_input(modifier, ids["Affect"], affect)


def fillet_input_ids(node_group) -> dict:
    """Map ``{socket name: identifier}`` for the group's inputs."""
    return {
        s.name: s.identifier
        for s in node_group.interface.items_tree
        if getattr(s, "in_out", "") == "INPUT"
    }
