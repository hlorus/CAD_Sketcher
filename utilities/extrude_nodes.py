"""Code-built ``CAD Sketcher Extrude`` node group (was a binary asset).

``build_extrude_node_group`` builds the face-extrude group in code, replacing the
copy that used to ship in ``resources/assets.blend`` -- mirroring the boolean,
convert and revolve groups. A filled profile becomes a capped solid; the sign of
``Size`` keeps the caps facing outward, and the ``Mirror Extrude`` /
``Asymmetry Override`` toggles select symmetric or two-sided variants.

``ensure_extrude_edge_walls`` then patches that group in place (idempotent,
version-gated): when the input carries no faces it extrudes the boundary edges
along local +Z by ``Size`` into open walls, honouring ``Mirror Extrude``. Filled
input is untouched -- it flows through the original face-extrude path.
"""


EXTRUDE_NODE_GROUP = "CAD Sketcher Extrude"
# Bump when the built graph changes so groups baked into saved files rebuild.
EXTRUDE_VERSION = 1
# Bump when the patched sub-graph changes so groups baked into saved files upgrade.
EXTRUDE_EDGE_WALLS_VERSION = 1

# The seam weld after each Extrude/Join. Kept at the asset's historical 1 mm for a
# behaviour-identical migration; issue #670 (this value eats sub-1mm detail on
# mm-scale models) is addressed in a follow-up, not here.
_SEAM_WELD_DISTANCE = 0.001


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
    -- otherwise upgrading from the old binary asset silently resets every extrude.
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


def build_extrude_node_group(name: str = EXTRUDE_NODE_GROUP):
    """Build the face-extrude group in code (idempotent).

    Reuses an existing group of the same name, rebuilding it in place when the
    stored version is stale -- so modifiers already bound to that name (including
    ones bound to the old binary asset) upgrade without rebinding. The wire-profile
    wall path is layered on separately by ``ensure_extrude_edge_walls``; a rebuild
    drops its marker so the caller re-applies it. Returns the node group.
    """
    ng = bpy.data.node_groups.get(name)
    if ng is None:
        ng = bpy.data.node_groups.new(name, "GeometryNodeTree")

    # Offer it in the Add Modifier > Geometry Nodes picker (off by default for
    # API-created groups).
    ng.is_modifier = True

    if ng.get("cad_extrude_version") == EXTRUDE_VERSION:
        return ng

    saved = _snapshot_modifier_inputs(ng)

    ng.nodes.clear()
    ng.links.clear()
    ng.interface.clear()

    iface = ng.interface
    iface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    iface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    size = iface.new_socket("Size", in_out="INPUT", socket_type="NodeSocketFloat")
    size.default_value = 1.0
    iface.new_socket("Mirror Extrude", in_out="INPUT", socket_type="NodeSocketBool")
    iface.new_socket("Asymmetry Override", in_out="INPUT", socket_type="NodeSocketBool")
    asym = iface.new_socket(
        "Asymmetry Distance", in_out="INPUT", socket_type="NodeSocketFloat"
    )
    asym.default_value = 1.0

    nodes, links = ng.nodes, ng.links
    gi = nodes.new("NodeGroupInput")
    go = nodes.new("NodeGroupOutput")
    geom = gi.outputs["Geometry"]
    size_o = gi.outputs["Size"]
    mirror_o = gi.outputs["Mirror Extrude"]
    asym_on = gi.outputs["Asymmetry Override"]
    asym_d = gi.outputs["Asymmetry Distance"]

    def extrude(geo, scale):
        n = nodes.new("GeometryNodeExtrudeMesh")
        n.mode = "FACES"
        # Extrude the selected faces as one region (matching the asset). Blender
        # defaults this socket to True, which would wall off every internal fill
        # edge and inflate the cap; False keeps a single shared extrusion.
        n.inputs["Individual"].default_value = False
        links.new(geo, n.inputs["Mesh"])
        links.new(scale, n.inputs["Offset Scale"])
        return n.outputs["Mesh"]

    def flip(geo):
        n = nodes.new("GeometryNodeFlipFaces")
        links.new(geo, n.inputs["Mesh"])
        return n.outputs["Mesh"]

    def join(*geos):
        n = nodes.new("GeometryNodeJoinGeometry")
        for g in geos:
            links.new(g, n.inputs["Geometry"])
        return n.outputs["Geometry"]

    def weld(geo):
        n = nodes.new("GeometryNodeMergeByDistance")
        links.new(geo, n.inputs["Geometry"])
        n.inputs["Distance"].default_value = _SEAM_WELD_DISTANCE
        # Weld across disconnected components (the extrude cap joined to the source
        # loop): the seam pieces are separate islands, so "Connected" would miss
        # them. Matches the asset's mode. Guard for older/renamed sockets.
        try:
            n.inputs["Mode"].default_value = "ALL"
        except Exception:
            pass
        return n.outputs["Geometry"]

    def switch(cond, false_geo, true_geo):
        n = nodes.new("GeometryNodeSwitch")
        n.input_type = "GEOMETRY"
        links.new(cond, n.inputs["Switch"])
        links.new(false_geo, n.inputs["False"])
        links.new(true_geo, n.inputs["True"])
        return n.outputs["Output"]

    def is_negative(value):
        n = nodes.new("FunctionNodeCompare")
        n.data_type = "FLOAT"
        n.operation = "LESS_THAN"
        links.new(value, n.inputs["A"])  # B stays 0.0
        return n.outputs["Result"]

    def negate(value):
        n = nodes.new("ShaderNodeMath")
        n.operation = "MULTIPLY"
        links.new(value, n.inputs[0])
        n.inputs[1].default_value = -1.0
        return n.outputs["Value"]

    # Single extrude: cap one end with the flipped source loop. The sign of Size
    # decides which piece gets flipped so the caps always face outward.
    simple = switch(
        is_negative(size_o),
        weld(join(extrude(geom, size_o), flip(geom))),
        weld(join(flip(extrude(geom, size_o)), geom)),
    )

    # Mirror: extrude both +Size and -Size from the source loop, flipping the
    # negative side; the whole result flips again when Size itself is negative.
    mirror_body = weld(join(extrude(geom, size_o), flip(extrude(geom, negate(size_o)))))
    mirror = switch(is_negative(size_o), mirror_body, flip(mirror_body))

    # Asymmetry: extrude Size one way and Asymmetry Distance the other.
    asymmetric = weld(join(extrude(geom, size_o), flip(extrude(geom, asym_d))))

    result = switch(asym_on, switch(mirror_o, simple, mirror), asymmetric)
    links.new(result, go.inputs["Geometry"])

    # A fresh graph has no wall path yet; let ensure_extrude_edge_walls re-add it.
    if "cad_extrude_edge_walls_version" in ng:
        del ng["cad_extrude_edge_walls_version"]

    _restore_modifier_inputs(ng, saved)
    ng["cad_extrude_version"] = EXTRUDE_VERSION
    return ng


def _group_input(nodes):
    return next((n for n in nodes if n.bl_idname == "NodeGroupInput"), None)


def _group_output(nodes):
    return next((n for n in nodes if n.bl_idname == "NodeGroupOutput"), None)


def ensure_extrude_edge_walls(node_group):
    """Add the face-less wall path to the extrude group once, and return it."""
    if node_group is None:
        return node_group
    if node_group.get("cad_extrude_edge_walls_version") == EXTRUDE_EDGE_WALLS_VERSION:
        return node_group

    nodes, links = node_group.nodes, node_group.links
    gi = _group_input(nodes)
    go = _group_output(nodes)
    if gi is None or go is None:
        return node_group
    geo_out = go.inputs.get("Geometry")
    if geo_out is None or not geo_out.links:
        return node_group

    # The face-extrude result currently wired to the output; keep it for filled
    # input (the branch we fall back to when the profile has faces).
    faces_result = geo_out.links[0].from_socket

    geometry = gi.outputs["Geometry"]
    size = gi.outputs["Size"]
    mirror = gi.outputs["Mirror Extrude"]

    # No faces on the input? Then it's a wire profile to turn into walls.
    domain = nodes.new("GeometryNodeAttributeDomainSize")
    domain.component = "MESH"
    links.new(geometry, domain.inputs["Geometry"])
    no_faces = nodes.new("FunctionNodeCompare")
    no_faces.data_type = "INT"
    no_faces.operation = "EQUAL"
    a, b = (s for s in no_faces.inputs if s.enabled and s.type == "INT")
    b.default_value = 0
    links.new(domain.outputs["Face Count"], a)

    def edge_walls(sign):
        # Wire wire edges have no usable normal, so the extrude Offset must be an
        # explicit vector -- a constant socket default is ignored and the edges
        # would extrude flat. Drive local Z from Size so walls rise perpendicular
        # to the sketch plane (matching the face path's normal-up direction).
        combine = nodes.new("ShaderNodeCombineXYZ")
        if sign < 0:
            negate = nodes.new("ShaderNodeMath")
            negate.operation = "MULTIPLY"
            negate.inputs[1].default_value = -1.0
            links.new(size, negate.inputs[0])
            links.new(negate.outputs["Value"], combine.inputs["Z"])
        else:
            links.new(size, combine.inputs["Z"])

        extrude = nodes.new("GeometryNodeExtrudeMesh")
        extrude.mode = "EDGES"
        links.new(geometry, extrude.inputs["Mesh"])
        links.new(combine.outputs["Vector"], extrude.inputs["Offset"])
        return extrude.outputs["Mesh"]

    up = edge_walls(1.0)
    # Mirror: also extrude down and weld the shared source loop, so the walls span
    # -Size..+Size instead of 0..+Size.
    down = edge_walls(-1.0)
    join = nodes.new("GeometryNodeJoinGeometry")
    links.new(up, join.inputs["Geometry"])
    links.new(down, join.inputs["Geometry"])
    weld = nodes.new("GeometryNodeMergeByDistance")
    links.new(join.outputs["Geometry"], weld.inputs["Geometry"])

    mirror_switch = nodes.new("GeometryNodeSwitch")
    mirror_switch.input_type = "GEOMETRY"
    links.new(mirror, mirror_switch.inputs["Switch"])
    links.new(up, mirror_switch.inputs["False"])
    links.new(weld.outputs["Geometry"], mirror_switch.inputs["True"])

    final = nodes.new("GeometryNodeSwitch")
    final.input_type = "GEOMETRY"
    links.new(no_faces.outputs["Result"], final.inputs["Switch"])
    links.new(faces_result, final.inputs["False"])
    links.new(mirror_switch.outputs["Output"], final.inputs["True"])
    links.new(final.outputs["Output"], geo_out)

    node_group["cad_extrude_edge_walls_version"] = EXTRUDE_EDGE_WALLS_VERSION
    return node_group
