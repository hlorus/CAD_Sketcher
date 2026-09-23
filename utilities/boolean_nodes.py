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

The boolean solver is selectable. Exact is the default because it tolerates
imperfect input. Manifold is typically orders of magnitude faster, but it only
accepts clean closed (manifold) meshes and silently drops operands that are not,
so it is an opt-in per modifier rather than a global switch.
"""

import bpy

BOOLEAN_NODE_GROUP = "CAD Sketcher Boolean"

# Bump whenever the built tree changes so groups baked into existing files are
# rebuilt in place on load, keeping modifiers bound to the same name.
BOOLEAN_VERSION = 4

# Menu items, in node/enum order. The interface menu default is the first.
_OPERATIONS = ("Difference", "Union", "Intersect")
_OP_TO_NODE = {
    "Difference": "DIFFERENCE",
    "Union": "UNION",
    "Intersect": "INTERSECT",
}

# Solver menu items, in index order; the first is the node-group default.
SOLVERS = ("Exact", "Manifold")

# EnumProperty items shared by the preference and the Boolean tool, so both read
# the same names and descriptions.
SOLVER_ITEMS = (
    ("Exact", "Exact", "Robust with imperfect geometry, but slow"),
    (
        "Manifold",
        "Manifold",
        "Much faster, but only for clean closed meshes: non-manifold input is "
        "dropped from the result",
    ),
)

# Named "Boolean Solver", not just "Solver": CAD Sketcher also has a constraint
# solver, and a bare "Solver" in the modifier panel reads as that.
SOLVER_SOCKET = "Boolean Solver"
_SOLVER_TO_NODE = {"Exact": "EXACT", "Manifold": "MANIFOLD"}


def repair_solver_choice(scene) -> bool:
    """Move a boolean off the Manifold solver where it would delete its target.

    Manifold drops an operand that is not a closed volume, so a file saved with
    it selected can hold a boolean whose result is simply empty (a flat profile
    cut by a solid). New booleans choose the solver from the geometry; this is
    the same judgement applied to what a file already has.
    """
    import bpy

    from ..operators.modifiers import (
        boolean_input_ids,
        get_boolean_solver,
        get_modifier_input,
        set_boolean_solver,
    )
    from .boolean_targets import is_closed_solid

    depsgraph = bpy.context.evaluated_depsgraph_get()
    changed = False
    for obj in scene.objects:
        for modifier in obj.modifiers:
            group = getattr(modifier, "node_group", None)
            if modifier.type != "NODES" or group is None:
                continue
            if group.name != BOOLEAN_NODE_GROUP:
                continue
            ids = boolean_input_ids(group)
            if SOLVER_SOCKET not in ids or "Cutter" not in ids:
                continue  # a linked group, stuck at the interface it was built with
            if get_boolean_solver(modifier, ids[SOLVER_SOCKET]) != "Manifold":
                continue
            cutter = get_modifier_input(modifier, ids["Cutter"])
            operands = [obj] + ([cutter] if cutter is not None else [])
            if all(is_closed_solid(ob, depsgraph) for ob in operands):
                continue
            set_boolean_solver(modifier, ids[SOLVER_SOCKET], "Exact")
            changed = True
    return changed


def _geometry_sockets(node):
    """Return (single-input, multi-input) geometry sockets of a boolean node.

    The Mesh Boolean node's socket layout depends on its operation (Difference
    exposes ``Mesh 1`` + ``Mesh 2``; Union/Intersect expose ``Mesh 1`` + a
    multi-input ``Mesh``), so wire by socket role rather than by name.
    """
    single = [s for s in node.inputs if s.type == "GEOMETRY" and not s.is_multi_input]
    multi = [s for s in node.inputs if s.type == "GEOMETRY" and s.is_multi_input]
    return single, multi


def _ensure_socket(interface, name, in_out, socket_type):
    """Return the interface socket ``name``/``in_out``, creating it if missing.

    An existing socket is kept (so its identifier, and every modifier value keyed
    by it, survives a rebuild). One with the wrong type is replaced, since its
    stored values could not be reused anyway.
    """
    for item in interface.items_tree:
        if item.item_type == "SOCKET" and item.name == name and item.in_out == in_out:
            if item.socket_type == socket_type:
                return item
            interface.remove(item)
            break
    return interface.new_socket(name, in_out=in_out, socket_type=socket_type)


def build_boolean_node_group(name: str = BOOLEAN_NODE_GROUP):
    """Build the nondestructive boolean group (idempotent).

    Reuses an existing group of the same name, rebuilding it in place when the
    stored version is stale so modifiers already bound to that name upgrade
    without rebinding. Returns the node group.
    """
    ng = bpy.data.node_groups.get(name)
    if ng is None:
        ng = bpy.data.node_groups.new(name, "GeometryNodeTree")

    # Offer it in the Add Modifier > Geometry Nodes picker. A group created via
    # the API has this off by default, so it would otherwise only be selectable
    # from the node editor (assigning it to a modifier from code still works,
    # which is why it can be used without this flag).
    ng.is_modifier = True

    if ng.get("cad_boolean_version") == BOOLEAN_VERSION:
        return ng
    # Rebuild nodes and links only. The interface is updated in place, never
    # cleared: modifier input values are keyed by socket identifier, and a
    # cleared-then-recreated socket gets a fresh identifier (Socket_1 comes back as
    # Socket_8), which would silently wipe the Cutter and Operation of every
    # boolean already in the file on the next rebuild.
    ng.nodes.clear()
    ng.links.clear()

    iface = ng.interface
    _ensure_socket(iface, "Geometry", "INPUT", "NodeSocketGeometry")
    _ensure_socket(iface, "Cutter", "INPUT", "NodeSocketObject")
    # An integer + Index Switch, not a menu socket: menu sockets do not evaluate
    # reliably as modifier inputs on Blender 5.0/5.1 (the switch produces no
    # geometry there), whereas an int index behaves identically across versions.
    operation = _ensure_socket(iface, "Operation", "INPUT", "NodeSocketInt")
    operation.min_value = 0
    operation.max_value = len(_OPERATIONS) - 1
    operation.default_value = 0
    operation.description = "0 = Difference, 1 = Union, 2 = Intersect"
    self_intersection = _ensure_socket(
        iface, "Self Intersection", "INPUT", "NodeSocketBool"
    )
    # Robust default: sketch fills welded by identity can leave shared boundary
    # points, so keep self-intersection handling on.
    self_intersection.default_value = True
    _ensure_socket(iface, "Hole Tolerant", "INPUT", "NodeSocketBool")
    _ensure_socket(iface, "Geometry", "OUTPUT", "NodeSocketGeometry")
    # Int index for the same reason as Operation.
    solver = _ensure_socket(iface, SOLVER_SOCKET, "INPUT", "NodeSocketInt")
    solver.min_value = 0
    solver.max_value = len(SOLVERS) - 1
    solver.default_value = 0
    solver.description = (
        "0 = Exact (robust, slower), 1 = Manifold (much faster, needs clean closed "
        "meshes; non-manifold input is dropped)"
    )

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

    def make_boolean(op_node, solver_node):
        node = nodes.new("GeometryNodeMeshBoolean")
        # The solver is a node property, not a socket, so it cannot be driven by
        # an input directly: one node per solver, picked by the Index Switch.
        node.solver = solver_node
        node.operation = op_node
        single, multi = _geometry_sockets(node)
        if op_node == "DIFFERENCE":
            # Difference subtracts the multi-input (Mesh 2) from Mesh 1 (body).
            links.new(body_geo, single[0])
            links.new(cutter_geo, multi[0])
        else:
            # Union/Intersect operate on the multi-input list ONLY and ignore
            # Mesh 1, so both operands go into it. (Feeding the body to Mesh 1
            # here silently drops it and outputs just the cutter.)
            links.new(body_geo, multi[0])
            links.new(cutter_geo, multi[0])
        # Only the Exact solver has these sockets; the Manifold node skips them.
        for socket in node.inputs:
            if socket.name == "Self Intersection":
                links.new(gi.outputs["Self Intersection"], socket)
            elif socket.name == "Hole Tolerant":
                links.new(gi.outputs["Hole Tolerant"], socket)
        return node

    def index_switch(index_output, items):
        switch = nodes.new("GeometryNodeIndexSwitch")
        switch.data_type = "GEOMETRY"
        while len(switch.index_switch_items) < len(items):
            switch.index_switch_items.new()
        links.new(index_output, switch.inputs["Index"])
        for i, item in enumerate(items):
            links.new(item, switch.inputs[str(i)])
        return switch.outputs["Output"]

    # Solver switch over operation switches. Only the branch the switches select
    # is evaluated, so the five unused boolean nodes cost nothing at runtime.
    per_solver = []
    for solver_label in SOLVERS:
        branches = [
            make_boolean(_OP_TO_NODE[label], _SOLVER_TO_NODE[solver_label]).outputs[
                "Mesh"
            ]
            for label in _OPERATIONS
        ]
        per_solver.append(index_switch(gi.outputs["Operation"], branches))
    links.new(
        index_switch(gi.outputs[SOLVER_SOCKET], per_solver), go.inputs["Geometry"]
    )

    ng["cad_boolean_version"] = BOOLEAN_VERSION
    return ng
