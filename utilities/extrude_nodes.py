"""Edge-extrude fallback for the shipped ``CAD Sketcher Extrude`` asset.

The asset extrudes faces (a filled profile becomes a capped solid). A non-filled
sketch converts to a bare wire mesh -- edges, no faces -- so the face extrude has
nothing to act on and the tool silently produces no geometry.

``ensure_extrude_edge_walls`` patches the loaded group in place (idempotent,
version-gated, mirroring ``convert_nodes.ensure_generated_id_nodes``): when the
input carries no faces it extrudes the boundary edges along local +Z by ``Size``
into open walls, honouring the ``Mirror Extrude`` toggle. Filled input is
untouched -- it still flows through the original face-extrude path.
"""

import bpy

EXTRUDE_NODE_GROUP = "CAD Sketcher Extrude"
# Bump when the patched sub-graph changes so groups baked into saved files upgrade.
EXTRUDE_EDGE_WALLS_VERSION = 1


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
