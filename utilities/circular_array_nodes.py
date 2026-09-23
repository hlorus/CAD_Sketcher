"""Code-built ``CAD Sketcher Circular Array`` node group.

Repeats the input geometry around an axis: ``Count`` copies turned by one angular
step each, either spread over a total ``Angle`` (a full turn by default) or that
angle apart. The axis is given as a point and a direction in the object's local
space, so the operator can hand over whatever the user picked -- a mesh edge, a
sketch line or one of a part's own axes.

Each copy is an instance rotated about the axis, so the source geometry is
evaluated once however many copies there are. ``Align Rotation`` decides whether a
copy turns with the pattern (a bolt circle) or keeps the original orientation
while only its position travels round (a carousel).

Nodes, properties and socket defaults are set defensively, as in the linear array:
anything that only exists on newer Blender is skipped (and reported), and every
node property and unlinked socket default is set explicitly, because fresh-node
defaults drift between Blender versions.
"""

import math

import bpy

CIRCULAR_ARRAY_NODE_GROUP = "CAD Sketcher Circular Array"
# Bump when the built graph changes so groups baked into saved files rebuild.
CIRCULAR_ARRAY_VERSION = 1

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
        item
        for item in node_group.interface.items_tree
        if getattr(item, "item_type", "") == "SOCKET"
        and getattr(item, "in_out", "") == "INPUT"
        and item.socket_type != "NodeSocketGeometry"
    ]


def _snapshot_modifier_inputs(node_group):
    """Input values of every modifier using ``node_group``, keyed by socket name.

    A rebuild re-mints the socket identifiers modifier inputs are keyed by, so
    without this an upgrade would reset every circular array to the defaults.
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
                # Vectors come back as a live reference into the modifier, which
                # the rebuild invalidates: copy the numbers out now.
                values[socket.name] = (
                    tuple(value) if hasattr(value, "__len__") else value
                )
            saved.append((mod, values))
    return saved


def _restore_modifier_inputs(node_group, saved):
    """Re-apply values from :func:`_snapshot_modifier_inputs` by socket name.

    An input the old group didn't have is missing from the snapshot, and the
    modifier would otherwise read it as 0 (a ``Count`` of 0 empties the array),
    so it falls back to the socket's default.
    """
    from ..operators.modifiers import set_modifier_input

    for mod, values in saved:
        for socket in _value_sockets(node_group):
            default = socket.default_value
            if hasattr(default, "__len__"):
                default = tuple(default)
            try:
                set_modifier_input(
                    mod, socket.identifier, values.get(socket.name, default)
                )
            except Exception:
                pass


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
        except Exception as exc:
            _skips.append(f"prop {idname}.{attr}={value!r} ({type(exc).__name__})")
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


def _math(nodes, links, operation, a, b=None, b_value=None):
    node = _node(nodes, "ShaderNodeMath", operation=operation, use_clamp=False)
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


def _plug(links, value, node, name, occurrence=0):
    """Link ``value`` if it is a socket, else write it as the input's default."""
    if isinstance(value, bpy.types.NodeSocket):
        _link(links, value, node, name, occurrence)
    else:
        _default(node, name, value, occurrence)


def _switch(nodes, links, input_type, condition, false, true):
    node = _node(nodes, "GeometryNodeSwitch", input_type=input_type)
    _link(links, condition, node, "Switch")
    _plug(links, false, node, "False")
    _plug(links, true, node, "True")
    return _out(node, "Output")


def _vector(nodes, links, operation, a, b=None, scale=None):
    node = _node(nodes, "ShaderNodeVectorMath", operation=operation)
    _plug(links, a, node, "Vector")
    if b is not None:
        _plug(links, b, node, "Vector", 1)
    if scale is not None:
        _plug(links, scale, node, "Scale")
    return _out(node, "Vector")


def _step_angle(nodes, links, angle, count, use_total):
    """The turn between two copies.

    Spread over the whole angle, ``count`` copies leave ``count`` gaps on a closed
    ring (the last copy must not land on the first), which is what a full turn
    needs; otherwise the angle is the step itself.
    """
    spread = _math(nodes, links, "DIVIDE", angle, b=count)
    return _switch(nodes, links, "FLOAT", use_total, angle, spread)


def _rotation(nodes, links, axis, angle):
    """An axis-angle rotation value."""
    node = _node(nodes, "FunctionNodeAxisAngleToRotation")
    _default(node, "Axis", (0.0, 0.0, 1.0))
    _default(node, "Angle", 0.0)
    _link(links, axis, node, "Axis")
    _link(links, angle, node, "Angle")
    return _out(node, "Rotation")


def _turned(nodes, links, vector, axis, angle):
    """``vector`` turned about ``axis`` (through the origin) by ``angle``."""
    node = _node(nodes, "ShaderNodeVectorRotate", rotation_type="AXIS_ANGLE")
    _default(node, "Center", (0.0, 0.0, 0.0))
    _plug(links, vector, node, "Vector")
    _plug(links, axis, node, "Axis")
    _plug(links, angle, node, "Angle")
    return _out(node, "Vector")


def _bounds_center(nodes, links, geometry):
    """The centre of the source geometry's bounding box.

    It stands in for "where the copy is": a copy travels on the circle this
    point traces, which is what lets a copy keep its orientation while still
    moving round (see ``Align Rotation``).
    """
    box = _node(nodes, "GeometryNodeBoundBox")
    _default(box, "Use Radius", True)
    _link(links, geometry, box, "Geometry")
    span = _vector(nodes, links, "ADD", _out(box, "Min"), _out(box, "Max"))
    return _vector(nodes, links, "SCALE", span, scale=0.5)


def _build_interface(ng):
    iface = ng.interface

    def socket(name, socket_type, default=None, **attrs):
        s = iface.new_socket(name, in_out="INPUT", socket_type=socket_type)
        if default is not None:
            s.default_value = default
        for attr, value in attrs.items():
            try:
                setattr(s, attr, value)
            except Exception:
                _skips.append(f"socket {name}.{attr}")
        return s

    big = 3.4028234663852886e38
    iface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    iface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    socket("Axis", "NodeSocketVector", (0.0, 0.0, 1.0))
    socket("Center", "NodeSocketVector", (0.0, 0.0, 0.0), subtype="TRANSLATION")
    socket("Count", "NodeSocketInt", 6, min_value=1, max_value=10000)
    socket(
        "Angle / Total angle",
        "NodeSocketFloat",
        math.tau,
        subtype="ANGLE",
        min_value=-math.tau,
        max_value=math.tau,
    )
    socket("Use Total Angle", "NodeSocketBool", True)
    socket("Align Rotation", "NodeSocketBool", True)
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


def _build_graph(ng):
    """Populate the freshly cleared group with the circular-array graph."""
    _build_interface(ng)
    nodes, links = ng.nodes, ng.links
    gi = _node(nodes, "NodeGroupInput")
    go = _node(nodes, "NodeGroupOutput")

    def arg(name):
        return _out(gi, name)

    # Copy i is one step further round the axis than copy i-1.
    index = _out(_node(nodes, "GeometryNodeInputIndex"), "Index")
    step = _step_angle(
        nodes, links, arg("Angle / Total angle"), arg("Count"), arg("Use Total Angle")
    )
    angle = _math(nodes, links, "MULTIPLY", index, b=step)

    # Each copy sits where the source's centre lands after that turn, so the
    # positions carry the travel and the instance rotation only decides how a
    # copy is oriented once there.
    center = _bounds_center(nodes, links, arg("Geometry"))
    radius = _vector(nodes, links, "SUBTRACT", center, arg("Center"))
    position = _vector(
        nodes,
        links,
        "ADD",
        _turned(nodes, links, radius, arg("Axis"), angle),
        arg("Center"),
    )

    points = _node(nodes, "GeometryNodePoints")
    _default(points, "Radius", 0.05)
    _link(links, arg("Count"), points, "Count")
    _link(links, position, points, "Position")

    # The instance is the source moved onto its own centre, so instancing puts
    # it back where it was and a rotation turns it about that centre.
    centered = _node(nodes, "GeometryNodeTransform")
    _default(centered, "Mode", "COMPONENTS")
    _default(centered, "Rotation", (0.0, 0.0, 0.0))
    _default(centered, "Scale", (1.0, 1.0, 1.0))
    _link(links, arg("Geometry"), centered, "Geometry")
    _link(
        links,
        _vector(nodes, links, "SCALE", center, scale=-1.0),
        centered,
        "Translation",
    )

    instances = _node(nodes, "GeometryNodeInstanceOnPoints")
    _default(instances, "Selection", True)
    _default(instances, "Pick Instance", False)
    _default(instances, "Instance Index", 0)
    _default(instances, "Scale", (1.0, 1.0, 1.0))
    _link(links, _out(points, "Points"), instances, "Points")
    _link(links, _out(centered, "Geometry"), instances, "Instance")
    _link(
        links,
        _switch(
            nodes,
            links,
            "ROTATION",
            arg("Align Rotation"),
            (0.0, 0.0, 0.0),
            _rotation(nodes, links, arg("Axis"), angle),
        ),
        instances,
        "Rotation",
    )
    placed = _out(instances, "Instances")

    realize = _node(nodes, "GeometryNodeRealizeInstances")
    _default(realize, "Selection", True)
    _default(realize, "Realize All", True)
    _default(realize, "Depth", 0)
    _link(links, placed, realize, "Geometry")
    geometry = _switch(
        nodes,
        links,
        "GEOMETRY",
        arg("Realize Instances"),
        placed,
        _out(realize, "Geometry"),
    )

    merge = _node(nodes, "GeometryNodeMergeByDistance")
    _default(merge, "Selection", True)
    _default(merge, "Mode", "All")
    _link(links, geometry, merge, "Geometry")
    _link(links, arg("Merge Distance"), merge, "Distance")
    geometry = _switch(
        nodes,
        links,
        "GEOMETRY",
        arg("Merge by Distance"),
        geometry,
        _out(merge, "Geometry"),
    )

    _link(links, geometry, go, "Geometry")


def build_circular_array_node_group(name: str = CIRCULAR_ARRAY_NODE_GROUP):
    """Build the circular-array group in code (idempotent).

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

    if ng.get("cad_circular_array_version") == CIRCULAR_ARRAY_VERSION:
        return ng

    saved = _snapshot_modifier_inputs(ng)
    ng.nodes.clear()
    ng.links.clear()
    ng.interface.clear()
    _skips.clear()
    _build_graph(ng)
    if _skips:
        print(
            "CAD Sketcher circular array build: unresolved sockets:\n  "
            + "\n  ".join(_skips)
        )
    _restore_modifier_inputs(ng, saved)
    ng["cad_circular_array_version"] = CIRCULAR_ARRAY_VERSION
    return ng
