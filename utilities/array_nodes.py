"""Code-built ``CAD Sketcher Linear Array`` node group.

Copies the input geometry along a direction (``Count`` copies, ``Spacing`` apart
or spread over a total distance), optionally along a second direction too, which
turns the line into a grid. ``Count 2`` defaults to 1, so a group without a
second direction behaves exactly like the original one-directional array.

Nodes, properties and socket defaults are set defensively: anything that only
exists on newer Blender is skipped (and reported), so the same graph builds on
every supported version. Every node property and unlinked socket default is set
explicitly, because fresh-node defaults drift between Blender versions.
"""

import bpy

ARRAY_NODE_GROUP = "CAD Sketcher Linear Array"
# Bump when the built graph changes so groups baked into saved files rebuild.
ARRAY_VERSION = 2

# Record of properties/sockets a build couldn't resolve on this Blender.
_skips = []


def _input_ids(node_group):
    """Map input socket name -> identifier (values are written by name)."""
    return {
        s.name: s.identifier
        for s in node_group.interface.items_tree
        if getattr(s, "in_out", "") == "INPUT"
    }


def _value_sockets(node_group):
    return [
        s
        for s in node_group.interface.items_tree
        if getattr(s, "item_type", "") == "SOCKET"
        and getattr(s, "in_out", "") == "INPUT"
        and s.socket_type != "NodeSocketGeometry"
    ]


def _snapshot_modifier_inputs(node_group):
    """Capture every modifier bound to ``node_group`` as (modifier, {name: value}).

    Rebuilding in place reassigns socket identifiers, and modifier inputs are keyed
    by identifier, so values are re-applied by the stable socket *name* afterwards.
    """
    from ..operators.modifiers import get_modifier_input

    sockets = _value_sockets(node_group)
    saved = []
    for obj in bpy.data.objects:
        for mod in obj.modifiers:
            if getattr(mod, "type", None) != "NODES" or mod.node_group != node_group:
                continue
            values = {}
            for socket in sockets:
                try:
                    value = get_modifier_input(mod, socket.identifier)
                except Exception:
                    continue
                values[socket.name] = (
                    tuple(value) if hasattr(value, "__len__") else value
                )
            saved.append((mod, values))
    return saved


def _restore_modifier_inputs(node_group, saved):
    """Re-apply snapshot values by name; new inputs get their default.

    An input the old group didn't have is missing from the snapshot, and the
    modifier would otherwise read it as 0 (a ``Count 2`` of 0 empties the array).
    """
    from ..operators.modifiers import set_modifier_input

    sockets = _value_sockets(node_group)
    for mod, values in saved:
        for socket in sockets:
            default = socket.default_value
            if hasattr(default, "__len__"):
                default = tuple(default)
            try:
                set_modifier_input(
                    mod, socket.identifier, values.get(socket.name, default)
                )
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Defensive node helpers
# ---------------------------------------------------------------------------


def _socket(sockets, name, occurrence=0):
    """The ``occurrence``-th socket named ``name`` (or None if absent)."""
    k = 0
    for s in sockets:
        if s.name == name:
            if k == occurrence:
                return s
            k += 1
    return None


def _node(nodes, idname, **props):
    node = nodes.new(idname)
    for attr, value in props.items():
        try:
            setattr(node, attr, value)
        except Exception as e:
            _skips.append(f"prop {idname}.{attr}={value!r} ({type(e).__name__})")
    return node


def _default(node, name, value, occurrence=0):
    socket = _socket(node.inputs, name, occurrence)
    if socket is None:
        _skips.append(f"default {node.bl_idname}.in[{name!r}#{occurrence}]")
        return
    try:
        socket.default_value = value
    except Exception:
        pass


def _out(node, name, occurrence=0):
    return _socket(node.outputs, name, occurrence)


def _link(links, from_socket, node, name, occurrence=0):
    to_socket = _socket(node.inputs, name, occurrence)
    if from_socket is None or to_socket is None:
        _skips.append(f"link -> {node.bl_idname}.in[{name!r}#{occurrence}]")
        return
    links.new(from_socket, to_socket)


def _math(nodes, links, operation, a, b=None, b_value=None, clamp=False):
    node = _node(nodes, "ShaderNodeMath", operation=operation, use_clamp=clamp)
    _default(node, "Value", 0.5, 2)
    if isinstance(a, (int, float)):
        _default(node, "Value", a, 0)
    else:
        _link(links, a, node, "Value", 0)
    if b is not None:
        _link(links, b, node, "Value", 1)
    elif b_value is not None:
        _default(node, "Value", b_value, 1)
    return _out(node, "Value")


def _switch(nodes, links, input_type, condition, false, true):
    node = _node(nodes, "GeometryNodeSwitch", input_type=input_type)
    _link(links, condition, node, "Switch")
    _link(links, false, node, "False")
    _link(links, true, node, "True")
    return _out(node, "Output")


def _set_position(nodes, links, geometry, offset):
    node = _node(nodes, "GeometryNodeSetPosition")
    _default(node, "Selection", True)
    _default(node, "Position", (0.0, 0.0, 0.0))
    _link(links, geometry, node, "Geometry")
    _link(links, offset, node, "Offset")
    return _out(node, "Geometry")


def _line_points(nodes, links, count, step, use_total):
    """Points along ``step``: ``count`` of them ``step`` apart, or spread over it."""
    lines = []
    for mode in ("OFFSET", "END_POINTS"):
        line = _node(nodes, "GeometryNodeMeshLine", mode=mode, count_mode="TOTAL")
        _default(line, "Resolution", 1.0)
        _default(line, "Start Location", (0.0, 0.0, 0.0))
        _link(links, count, line, "Count")
        # In end-point mode this same socket is the end location.
        _link(links, step, line, "Offset")
        lines.append(_out(line, "Mesh"))
    return _switch(nodes, links, "GEOMETRY", use_total, lines[0], lines[1])


def _step(nodes, links, direction, spacing, flip=None):
    """``normalize(direction) * spacing``, negated when ``flip`` is on."""
    normalize = _node(nodes, "ShaderNodeVectorMath", operation="NORMALIZE")
    _default(normalize, "Vector", (0.0, 0.0, 0.0), 1)
    _default(normalize, "Vector", (0.0, 0.0, 0.0), 2)
    _default(normalize, "Scale", 1.0)
    _link(links, direction, normalize, "Vector")
    if flip is not None:
        negated = _math(nodes, links, "MULTIPLY", -1.0, b=spacing)
        spacing = _switch(nodes, links, "FLOAT", flip, spacing, negated)
    scale = _node(nodes, "ShaderNodeVectorMath", operation="SCALE")
    _default(scale, "Vector", (0.0, 0.0, 0.0), 1)
    _default(scale, "Vector", (0.0, 0.0, 0.0), 2)
    _link(links, _out(normalize, "Vector"), scale, "Vector")
    _link(links, spacing, scale, "Scale")
    return _out(scale, "Vector")


def _bounds_center(nodes, links, geometry, component, clamp=False):
    """Center of the geometry's bounds along one position component."""
    stat = _node(
        nodes, "GeometryNodeAttributeStatistic", data_type="FLOAT", domain="POINT"
    )
    _default(stat, "Selection", True)
    _link(links, geometry, stat, "Geometry")
    _link(links, component, stat, "Attribute")
    extent = _math(nodes, links, "SUBTRACT", _out(stat, "Max"), b=_out(stat, "Min"))
    half = _math(nodes, links, "DIVIDE", extent, b_value=2.0)
    return _math(nodes, links, "ADD", half, b=_out(stat, "Min"), clamp=clamp)


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


def _build_interface(ng):
    iface = ng.interface

    def socket(name, socket_type, default=None, **attrs):
        s = iface.new_socket(name, in_out="INPUT", socket_type=socket_type)
        if default is not None:
            s.default_value = default
        for attr, value in attrs.items():
            setattr(s, attr, value)
        return s

    iface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    iface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    big = 3.4028234663852886e38
    # Names (including the "Direciton"/"Axies" typos) and order are kept from the
    # original asset: modifier values are restored by name.
    socket(
        "Direction", "NodeSocketVector", (0.0, 0.0, 1.0), min_value=0.0, max_value=1.0
    )
    socket("Count", "NodeSocketInt", 5, min_value=1, max_value=10000)
    socket(
        "Spacing / Total distance", "NodeSocketFloat", 3.0, min_value=0.0, max_value=big
    )
    socket("Flip Direciton", "NodeSocketBool", False)
    socket("Use Total Distance", "NodeSocketBool", False)
    socket("Align Rotation", "NodeSocketBool", False)
    socket("Merge by Distance", "NodeSocketBool", False)
    socket(
        "Merge Distance",
        "NodeSocketFloat",
        0.001,
        subtype="DISTANCE",
        min_value=0.0,
        max_value=big,
    )
    socket("Realize Instances", "NodeSocketBool", True)
    socket("Show Axies", "NodeSocketBool", False)
    socket(
        "Direction 2", "NodeSocketVector", (0.0, 1.0, 0.0), min_value=0.0, max_value=1.0
    )
    socket("Count 2", "NodeSocketInt", 1, min_value=1, max_value=10000)
    socket("Spacing 2", "NodeSocketFloat", 3.0, min_value=0.0, max_value=big)


def _build_graph(ng):
    """Populate the freshly cleared group with the array node graph."""
    _build_interface(ng)
    nodes, links = ng.nodes, ng.links
    gi = _node(nodes, "NodeGroupInput")
    go = _node(nodes, "NodeGroupOutput")

    def arg(name):
        return _out(gi, name)

    geometry = arg("Geometry")

    # Copies are placed around a pivot and moved back afterwards, which only
    # matters for Align Rotation: each copy turns around that pivot. The pivot is
    # the bounds center in X (clamped to 0..1) and Z, with Y at 0 -- quirks of the
    # original asset, kept so existing arrays don't move.
    separate = _node(nodes, "ShaderNodeSeparateXYZ")
    _link(
        links,
        _out(_node(nodes, "GeometryNodeInputPosition"), "Position"),
        separate,
        "Vector",
    )
    pivot = _node(nodes, "ShaderNodeCombineXYZ")
    _link(
        links,
        _bounds_center(nodes, links, geometry, _out(separate, "X"), clamp=True),
        pivot,
        "X",
    )
    _default(pivot, "Y", 0.0)
    _link(
        links, _bounds_center(nodes, links, geometry, _out(separate, "Z")), pivot, "Z"
    )
    pivot = _out(pivot, "Vector")

    to_pivot = _node(nodes, "ShaderNodeVectorMath", operation="SCALE")
    _default(to_pivot, "Vector", (0.0, 0.0, 0.0), 1)
    _default(to_pivot, "Vector", (0.0, 0.0, 0.0), 2)
    _default(to_pivot, "Scale", -1.0)
    _link(links, pivot, to_pivot, "Vector")
    centered = _node(nodes, "GeometryNodeTransform")
    _default(centered, "Mode", "Components")
    _default(centered, "Rotation", (0.0, 0.0, 0.0))
    _default(centered, "Scale", (1.0, 1.0, 1.0))
    _link(links, geometry, centered, "Geometry")
    _link(links, _out(to_pivot, "Vector"), centered, "Translation")

    # Copy positions: a line along Direction, optionally repeated along Direction 2.
    use_total = arg("Use Total Distance")
    line = _line_points(
        nodes,
        links,
        arg("Count"),
        _step(
            nodes,
            links,
            arg("Direction"),
            arg("Spacing / Total distance"),
            arg("Flip Direciton"),
        ),
        use_total,
    )
    second = _line_points(
        nodes,
        links,
        arg("Count 2"),
        _step(nodes, links, arg("Direction 2"), arg("Spacing 2")),
        use_total,
    )
    rows = _node(nodes, "GeometryNodeInstanceOnPoints")
    _default(rows, "Selection", True)
    _link(links, line, rows, "Points")
    _link(links, second, rows, "Instance")
    grid = _node(nodes, "GeometryNodeRealizeInstances", realize_to_point_domain=True)
    _default(grid, "Selection", True)
    _default(grid, "Realize All", True)
    _default(grid, "Depth", 0)
    _link(links, _out(rows, "Instances"), grid, "Geometry")
    # A single-row array keeps its line untouched (identical to the 1D array,
    # and robust to a Count 2 of 0).
    is_grid = _node(
        nodes, "FunctionNodeCompare", data_type="INT", operation="GREATER_THAN"
    )
    # A and B repeat once per data type; use the enabled integer pair.
    int_a, int_b = (s for s in is_grid.inputs if s.enabled and s.type == "INT")
    links.new(arg("Count 2"), int_a)
    int_b.default_value = 1
    points = _switch(
        nodes, links, "GEOMETRY", _out(is_grid, "Result"), line, _out(grid, "Geometry")
    )

    copies = _node(nodes, "GeometryNodeInstanceOnPoints")
    _default(copies, "Selection", True)
    _default(copies, "Pick Instance", False)
    _default(copies, "Instance Index", 0)
    _default(copies, "Rotation", (0.0, 0.0, 0.0))
    _default(copies, "Scale", (1.0, 1.0, 1.0))
    _link(links, points, copies, "Points")
    _link(links, _out(centered, "Geometry"), copies, "Instance")
    instances = _out(copies, "Instances")

    align = _node(nodes, "FunctionNodeAlignEulerToVector", axis="X", pivot_axis="AUTO")
    _default(align, "Rotation", (0.0, 0.0, 0.0))
    _default(align, "Factor", 1.0)
    _link(links, arg("Direction"), align, "Vector")
    euler = _node(nodes, "FunctionNodeEulerToRotation")
    _link(links, _out(align, "Rotation"), euler, "Euler")
    rotate = _node(nodes, "GeometryNodeRotateInstances")
    _default(rotate, "Selection", True)
    _default(rotate, "Pivot Point", (0.0, 0.0, 0.0))
    _default(rotate, "Local Space", True)
    _link(links, instances, rotate, "Instances")
    _link(links, _out(euler, "Rotation"), rotate, "Rotation")
    result = _switch(
        nodes,
        links,
        "GEOMETRY",
        arg("Align Rotation"),
        instances,
        _out(rotate, "Instances"),
    )

    realize = _node(nodes, "GeometryNodeRealizeInstances", realize_to_point_domain=True)
    _default(realize, "Selection", True)
    _default(realize, "Realize All", True)
    _default(realize, "Depth", 0)
    _link(links, result, realize, "Geometry")
    result = _switch(
        nodes,
        links,
        "GEOMETRY",
        arg("Realize Instances"),
        result,
        _out(realize, "Geometry"),
    )

    merge = _node(nodes, "GeometryNodeMergeByDistance")
    _default(merge, "Selection", True)
    _default(merge, "Mode", "All")
    _link(links, result, merge, "Geometry")
    _link(links, arg("Merge Distance"), merge, "Distance")
    result = _switch(
        nodes,
        links,
        "GEOMETRY",
        arg("Merge by Distance"),
        result,
        _out(merge, "Geometry"),
    )

    result = _set_position(nodes, links, result, pivot)

    # Show Axies previews the copy positions next to the result.
    join = _node(nodes, "GeometryNodeJoinGeometry")
    _link(links, result, join, "Geometry")
    _link(links, _set_position(nodes, links, points, pivot), join, "Geometry")
    result = _switch(
        nodes, links, "GEOMETRY", arg("Show Axies"), result, _out(join, "Geometry")
    )

    _link(links, result, go, "Geometry")


def build_array_node_group(name: str = ARRAY_NODE_GROUP):
    """Build the linear-array group in code (idempotent).

    Reuses an existing group of the same name, rebuilding it in place when the
    stored version is stale, so modifiers already bound to that name upgrade
    without rebinding. Returns the node group.
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
