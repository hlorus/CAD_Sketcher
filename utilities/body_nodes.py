"""The Geometry Nodes group that starts a body's stack: read its sketch.

A sketch is a Curves object, and a Curves object cannot be read as a mesh: to_mesh,
exporters and mesh tools all refuse it whatever its modifiers emit, and Blender
refuses to *apply* a modifier that changes the type (issue #723). So the sketch
carries no modifiers at all and its geometry is pulled into a real mesh object
through an ``Object Info`` node. The rest of the body's stack (convert, extrude,
booleans) then operates on mesh, applies normally and exports normally.
"""

import bpy

BODY_NODE_GROUP = "CAD Sketcher Body Source"
BODY_VERSION = 1


def build_body_node_group(name: str = BODY_NODE_GROUP):
    """Build the sketch-to-body group (idempotent, version-gated).

    Reuses an existing group of the same name, rebuilding it in place when the
    stored version is stale so bound modifiers upgrade without rebinding.
    """
    ng = bpy.data.node_groups.get(name)
    if ng is None:
        ng = bpy.data.node_groups.new(name, "GeometryNodeTree")

    # Offer it in the Add Modifier > Geometry Nodes picker (off by default for
    # API-created groups).
    ng.is_modifier = True

    if ng.get("cad_body_version") == BODY_VERSION:
        return ng
    ng.nodes.clear()
    ng.links.clear()
    ng.interface.clear()

    iface = ng.interface
    iface.new_socket("Sketch", in_out="INPUT", socket_type="NodeSocketObject")
    iface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    nodes, links = ng.nodes, ng.links
    gi = nodes.new("NodeGroupInput")
    go = nodes.new("NodeGroupOutput")

    # Pull the sketch's *evaluated* geometry (its convert modifier's mesh output)
    # in this object's local space. Matching the mesh object's transform to the
    # sketch's keeps the geometry planar in local coordinates yet world-correct.
    info = nodes.new("GeometryNodeObjectInfo")
    info.transform_space = "RELATIVE"
    links.new(gi.outputs["Sketch"], info.inputs["Object"])

    # A mesh target yields realized geometry already; realize regardless so an
    # instanced source still resolves to real mesh data downstream.
    realize = nodes.new("GeometryNodeRealizeInstances")
    links.new(info.outputs["Geometry"], realize.inputs["Geometry"])
    links.new(realize.outputs["Geometry"], go.inputs["Geometry"])

    ng["cad_body_version"] = BODY_VERSION
    return ng


def body_input_ids(node_group) -> dict:
    """Map ``{socket name: identifier}`` for the group's inputs."""
    return {
        s.name: s.identifier
        for s in node_group.interface.items_tree
        if getattr(s, "in_out", "") == "INPUT"
    }
