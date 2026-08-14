"""Programmatic 'CAD Sketcher Convert' node group for Blender 5.2+.

The shipped node group (``resources/assets.blend``) closes sketch loops for
filling with Merge by Distance, which is a distance threshold and therefore
fragile: too tight and loose junctions never weld (fill vanishes), too loose and
distinct points on small models merge. Blender 5.2 adds the ``Merge Points`` node
with a ``Merge ID`` input, letting us weld by *identity* instead.

This builds an equivalent group that welds mesh vertices sharing a ``merge_id``
(see ``utilities.curve_data.compute_merge_ids``), gated to true segment endpoints
via vertex valence so tessellated interior vertices are never merged. The result
is tolerance-free and independent of sketch scale. The final generated geometry
also carries deterministic vertex/face identifiers so consumers can keep element
references across coordinate-only sketch edits while topology is unchanged.
Older Blender keeps loading the merge-by-distance asset.
"""

import bpy

CONVERT_NODE_GROUP = "CAD Sketcher Convert"
VERTEX_ID_ATTR = "cad_sketcher_vertex_id"
FACE_ID_ATTR = "cad_sketcher_face_id"

# Bump whenever the built node tree changes, so groups baked into existing files
# (or a stale merge-by-distance asset of the same name) are rebuilt on load.
CONVERT_VERSION = 3


def _int_compare(nodes, links, operation, value):
    """A Compare node on integers: returns (node, a_socket) with B set to value."""
    cmp = nodes.new("FunctionNodeCompare")
    cmp.data_type = "INT"
    cmp.operation = operation
    # data_type='INT' exposes just the two integer sockets; pick them by type so
    # this doesn't depend on socket ordering across Blender versions.
    a, b = (s for s in cmp.inputs if s.enabled and s.type == "INT")
    b.default_value = value
    return cmp, a


def _is_identity_group(ng) -> bool:
    return any(n.bl_idname == "GeometryNodeMergePoints" for n in ng.nodes)


def _store_index_attribute(nodes, links, geometry, name, domain):
    """Store the current element index as a named integer attribute.

    Geometry Nodes evaluates ``Index`` in the domain requested by the Store
    Named Attribute node. For an unchanged generated topology this gives a
    deterministic mapping on every depsgraph re-evaluation instead of relying on
    transient evaluated-mesh instances.
    """
    index = nodes.new("GeometryNodeInputIndex")
    store = nodes.new("GeometryNodeStoreNamedAttribute")
    store.data_type = "INT"
    store.domain = domain
    store.inputs["Name"].default_value = name
    links.new(geometry, store.inputs["Geometry"])
    links.new(index.outputs["Index"], store.inputs["Value"])
    return store.outputs["Geometry"]


def build_convert_node_group(name: str = CONVERT_NODE_GROUP):
    """Build the identity-weld convert node group (idempotent).

    Reuses an existing group of the same name, rebuilding it in place if it's a
    stale (merge-by-distance) version — so modifiers already bound to that name
    upgrade without rebinding.
    """
    ng = bpy.data.node_groups.get(name)
    if ng is not None:
        if ng.get("cad_convert_version") == CONVERT_VERSION:
            return ng
        ng.nodes.clear()
        ng.links.clear()
        ng.interface.clear()
    else:
        ng = bpy.data.node_groups.new(name, "GeometryNodeTree")

    iface = ng.interface
    iface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    iface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    fill = iface.new_socket("Fill", in_out="INPUT", socket_type="NodeSocketBool")
    fill.default_value = True

    nodes, links = ng.nodes, ng.links
    gi = nodes.new("NodeGroupInput")
    go = nodes.new("NodeGroupOutput")

    # 1. Drop construction curves and degenerate (< 2 point) splines before the
    #    fill so they never become geometry.
    construction = nodes.new("GeometryNodeInputNamedAttribute")
    construction.data_type = "BOOLEAN"
    construction.inputs["Name"].default_value = "construction"

    spline_len = nodes.new("GeometryNodeSplineLength")
    degenerate, degen_a = _int_compare(nodes, links, "LESS_THAN", 2)
    links.new(spline_len.outputs["Point Count"], degen_a)

    drop = nodes.new("FunctionNodeBooleanMath")
    drop.operation = "OR"
    links.new(construction.outputs["Attribute"], drop.inputs[0])
    links.new(degenerate.outputs["Result"], drop.inputs[1])

    delete = nodes.new("GeometryNodeDeleteGeometry")
    delete.domain = "CURVE"
    links.new(gi.outputs["Geometry"], delete.inputs["Geometry"])
    links.new(drop.outputs["Boolean"], delete.inputs["Selection"])

    # 2. Tessellate to a wire mesh.
    to_mesh = nodes.new("GeometryNodeCurveToMesh")
    links.new(delete.outputs["Geometry"], to_mesh.inputs["Curve"])

    # 3. Weld by identity: merge vertices sharing merge_id, but only true segment
    #    endpoints (valence 1 on the disconnected chains) -- tessellated interior
    #    vertices (valence 2) are excluded, so their interpolated id is harmless.
    merge_id = nodes.new("GeometryNodeInputNamedAttribute")
    merge_id.data_type = "INT"
    merge_id.inputs["Name"].default_value = "merge_id"

    neighbors = nodes.new("GeometryNodeInputMeshVertexNeighbors")
    is_end, end_a = _int_compare(nodes, links, "EQUAL", 1)
    links.new(neighbors.outputs["Vertex Count"], end_a)

    # id 0 means "no weld". Exclude it so a not-yet-computed merge_id (e.g. a
    # transient frame mid-draw) can't collapse every endpoint into one point.
    nonzero, nz_a = _int_compare(nodes, links, "NOT_EQUAL", 0)
    links.new(merge_id.outputs["Attribute"], nz_a)
    weld = nodes.new("FunctionNodeBooleanMath")
    weld.operation = "AND"
    links.new(is_end.outputs["Result"], weld.inputs[0])
    links.new(nonzero.outputs["Result"], weld.inputs[1])

    merge = nodes.new("GeometryNodeMergePoints")
    links.new(to_mesh.outputs["Mesh"], merge.inputs["Geometry"])
    links.new(merge_id.outputs["Attribute"], merge.inputs["Merge ID"])
    links.new(weld.outputs["Boolean"], merge.inputs["Selection"])

    # 4. Back to curves; fill closed loops, or output the wire when Fill is off.
    to_curve = nodes.new("GeometryNodeMeshToCurve")
    links.new(merge.outputs["Geometry"], to_curve.inputs["Mesh"])

    fill_curve = nodes.new("GeometryNodeFillCurve")
    links.new(to_curve.outputs["Curve"], fill_curve.inputs["Curve"])

    switch = nodes.new("GeometryNodeSwitch")
    switch.input_type = "GEOMETRY"
    links.new(gi.outputs["Fill"], switch.inputs["Switch"])
    links.new(to_curve.outputs["Curve"], switch.inputs["False"])
    links.new(fill_curve.outputs["Mesh"], switch.inputs["True"])

    # 5. Materialize generated-element identity. The evaluated mesh itself is
    #    recreated by Blender, so downstream tools must not rely on Python object
    #    identity. Named integer ids reappear deterministically on every
    #    evaluation as long as the generated topology is the same. When topology
    #    changes, only the affected correspondence is intentionally invalidated.
    geometry = _store_index_attribute(
        nodes, links, switch.outputs["Output"], VERTEX_ID_ATTR, "POINT"
    )
    geometry = _store_index_attribute(nodes, links, geometry, FACE_ID_ATTR, "FACE")
    links.new(geometry, go.inputs["Geometry"])

    ng["cad_convert_version"] = CONVERT_VERSION
    return ng
