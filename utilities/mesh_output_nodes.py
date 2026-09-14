"""Geometry Nodes group that surfaces a sketch's evaluated mesh on a mesh object.

A sketch lives on a Curves-type object whose ``CAD Sketcher Convert`` modifier
already outputs a mesh (wire, or a filled n-gon surface). But a Curves object
cannot be read as a mesh -- ``to_mesh`` / exporters / mesh edit tools all refuse
it regardless of what its modifier emits. Placed on a companion *mesh* object,
this group pulls the sketch's evaluated geometry through an ``Object Info`` node,
giving a real, non-destructive mesh that follows the sketch live, exports
normally, and can be applied to bake a static editable mesh.
"""

import bpy

MESH_OUTPUT_NODE_GROUP = "CAD Sketcher To Mesh"
MESH_OUTPUT_VERSION = 1


def build_mesh_output_node_group(name: str = MESH_OUTPUT_NODE_GROUP):
    """Build the sketch-to-mesh group (idempotent, version-gated).

    Reuses an existing group of the same name, rebuilding it in place when the
    stored version is stale so bound modifiers upgrade without rebinding.
    """
    ng = bpy.data.node_groups.get(name)
    if ng is None:
        ng = bpy.data.node_groups.new(name, "GeometryNodeTree")

    # Offer it in the Add Modifier > Geometry Nodes picker (off by default for
    # API-created groups).
    ng.is_modifier = True

    if ng.get("cad_mesh_output_version") == MESH_OUTPUT_VERSION:
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

    ng["cad_mesh_output_version"] = MESH_OUTPUT_VERSION
    return ng


def mesh_output_input_ids(node_group) -> dict:
    """Map ``{socket name: identifier}`` for the group's inputs."""
    return {
        s.name: s.identifier
        for s in node_group.interface.items_tree
        if getattr(s, "in_out", "") == "INPUT"
    }
