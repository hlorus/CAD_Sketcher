"""Programmatic 'CAD Sketcher Convert' node group for Blender 5.2+.

The shipped node group (``resources/assets.blend``) closes sketch loops for
filling with Merge by Distance, which is a distance threshold and therefore
fragile: too tight and loose junctions never weld (fill vanishes), too loose and
distinct points on small models merge. Blender 5.2 adds the ``Merge Points`` node
with a ``Merge ID`` input, letting us weld by *identity* instead.

This builds an equivalent group that welds mesh vertices sharing a ``merge_id``
(see ``utilities.curve_data.compute_merge_ids``), gated to true segment endpoints
via vertex valence so tessellated interior vertices are never merged. Custom
attributes are captured on the native Curves source before topology conversion
and explicitly stored again on the generated geometry, so they survive nodes
which otherwise drop unreferenced named attributes.
"""

import bpy

CONVERT_NODE_GROUP = "CAD Sketcher Convert"

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


def _normalize_attribute_definitions(attribute_definitions):
    """Return stable non-object attribute specs used by the conversion group."""
    specs = []
    for entry in attribute_definitions or ():
        name = str(entry.get("name", "")).strip()
        data_type = str(entry.get("type", "")).upper()
        domain = str(entry.get("domain", "")).upper()
        if not name or domain == "OBJECT":
            continue
        if data_type not in {"BOOLEAN", "INT", "FLOAT"}:
            continue
        if domain not in {"POINT", "CURVE"}:
            continue
        specs.append({"name": name, "type": data_type, "domain": domain})
    specs.sort(key=lambda item: (item["name"], item["domain"], item["type"]))
    return specs


def _attribute_signature(specs):
    return repr(tuple((x["name"], x["type"], x["domain"]) for x in specs))


def _capture_custom_attributes(nodes, links, geometry_socket, specs):
    """Capture named source attributes so anonymous fields survive conversion."""
    captured = []
    current_geometry = geometry_socket
    for entry in specs:
        named = nodes.new("GeometryNodeInputNamedAttribute")
        named.data_type = entry["type"]
        named.inputs["Name"].default_value = entry["name"]

        capture = nodes.new("GeometryNodeCaptureAttribute")
        capture.domain = entry["domain"]
        capture.capture_items.clear()
        capture.capture_items.new(entry["type"], entry["name"])

        links.new(current_geometry, capture.inputs["Geometry"])
        links.new(named.outputs["Attribute"], capture.inputs[entry["name"]])
        current_geometry = capture.outputs["Geometry"]
        captured.append((entry, capture.outputs[entry["name"]]))
    return current_geometry, captured


def _restore_custom_attributes(nodes, links, geometry_socket, captured):
    """Write captured values onto the produced geometry as named attributes.

    Both Curve and Mesh geometry support the POINT domain, so storing there gives
    a stable acceptance boundary regardless of whether Fill outputs a wire curve
    or a filled mesh. CURVE-domain source values are interpolated by the captured
    anonymous field across the generated points while retaining their name/type.
    """
    current_geometry = geometry_socket
    for entry, value_socket in captured:
        store = nodes.new("GeometryNodeStoreNamedAttribute")
        store.data_type = entry["type"]
        store.domain = "POINT"
        store.inputs["Name"].default_value = entry["name"]
        links.new(current_geometry, store.inputs["Geometry"])
        links.new(value_socket, store.inputs["Value"])
        current_geometry = store.outputs["Geometry"]
    return current_geometry


def build_convert_node_group(
    name: str = CONVERT_NODE_GROUP, attribute_definitions=None
):
    """Build the identity-weld convert node group (idempotent).

    ``attribute_definitions`` contains per-sketch user attribute definitions.
    Each non-object attribute is explicitly captured on the native Curves input
    and restored on the generated geometry. Reuses an existing group when both
    the converter version and attribute signature already match.
    """
    specs = _normalize_attribute_definitions(attribute_definitions)
    signature = _attribute_signature(specs)

    ng = bpy.data.node_groups.get(name)
    if ng is not None:
        if (
            ng.get("cad_convert_version") == CONVERT_VERSION
            and ng.get("cad_convert_attribute_signature", "") == signature
        ):
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

    source_geometry, captured = _capture_custom_attributes(
        nodes, links, gi.outputs["Geometry"], specs
    )

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
    links.new(source_geometry, delete.inputs["Geometry"])
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

    output_geometry = _restore_custom_attributes(
        nodes, links, switch.outputs["Output"], captured
    )
    links.new(output_geometry, go.inputs["Geometry"])

    ng["cad_convert_version"] = CONVERT_VERSION
    ng["cad_convert_attribute_signature"] = signature
    return ng
