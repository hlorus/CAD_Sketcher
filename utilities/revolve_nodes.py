"""Revolve (lathe) node group, built from source.

The shipped revolve was a ~60-node binary asset in ``resources/assets.blend``
that swept the *profile mesh* directly. That made it depend on how the profile
was tessellated: a filled sketch (the convert modifier's ``Fill`` on) arrives as
a triangulated mesh whose interior edges got swept into the surface, producing
redundant, self-intersecting geometry that broke the result (issue #634). The
same sketch with ``Fill`` off arrives as a clean boundary curve and revolved
fine.

This builds an equivalent group programmatically -- versioned in code and rebuilt
in place when ``REVOLVE_VERSION`` changes, like the boolean and convert groups --
that first *normalizes* whatever profile it is handed down to a single boundary
loop, so the swept lateral surface is identical whether ``Fill`` was on or off:

    * a mesh (filled or a wire) -> its boundary edges become a curve
      (``Mesh to Curve`` selecting edges with fewer than two adjacent faces),
    * a curve passes straight through,

joined into one boundary curve. Only that loop is swept, so interior fill
triangulation can never leak into the surface.

The loop winding is *canonicalized* first (reversed when its area normal points
against an axis-derived reference), because ``Mesh to Curve`` hands back the
boundary with a shape-dependent direction. Without this the swept surface and the
caps end up inconsistently oriented for some shapes.

The lateral surface is a Grid of ``(P+wrap) x (steps+1)`` vertices -- ``P`` profile
points (plus one wrap column for a closed loop) by one column per angular step --
whose every vertex is the matching profile point rotated about the axis by its
step's angle. ``Merge by Distance`` welds the wrap column and, at a full turn,
the start/end seam.

End caps are added only when the profile was *filled* and the sweep is a partial
turn (< 360 deg): the loop filled at the start (flipped) and a copy filled at the
end, wound oppositely so both stay coherent with the lateral. A full turn needs no
caps (the surface closes on itself), and an unfilled profile has no face to cap
with -- it stays an open shell. This matches the spec: a non-filled sketch
revolves to a valid surface, just without end caps.

Finally, orientation is decided from an internally-capped (closed) version of the
solid via its signed volume (divergence theorem) and the whole result is flipped
when it comes out inside-out. The same decision drives both the filled solid and
the unfilled open shell, so normals always point outward regardless of the
profile's shape or the *sign* of the sweep angle.
"""

import math

import bpy

REVOLVE_NODE_GROUP = "CAD Sketcher Revolve"

# Bump whenever the built tree changes so groups baked into existing files -- or a
# stale same-named binary asset -- are rebuilt in place on next use, keeping
# modifiers bound to the same name.
REVOLVE_VERSION = 5

# Weld tolerance for the sweep seams and the cap-to-lateral join. The welded
# points are produced by the *same* profile sample and rotation, so they are
# exactly coincident; any small epsilon collapses them. Kept well below typical
# sketch feature sizes so distinct profile points are never merged.
_WELD_DISTANCE = 1e-4


def _input_ids(node_group):
    """Map input socket name -> identifier (values are written by name)."""
    return {
        s.name: s.identifier
        for s in node_group.interface.items_tree
        if getattr(s, "in_out", "") == "INPUT"
    }


def _snapshot_modifier_inputs(node_group):
    """Capture every modifier bound to ``node_group`` as (modifier, {name: value}).

    Rebuilding the group in place reassigns socket identifiers, and modifier
    inputs are keyed by identifier, so their values must be re-applied by the
    stable socket *name* afterwards -- otherwise upgrading from the old binary
    asset (or a previous version) silently resets every existing revolve.
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
                # Coerce array-likes (vectors) to a plain tuple so the snapshot
                # survives the interface teardown.
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


def _math(nodes, links, operation, a=None, b=None):
    """A ShaderNodeMath node; wire/`set` inputs 0 and 1, return the output socket."""
    node = nodes.new("ShaderNodeMath")
    node.operation = operation
    for index, value in ((0, a), (1, b)):
        if value is None:
            continue
        if isinstance(value, (int, float)):
            node.inputs[index].default_value = float(value)
        else:
            links.new(value, node.inputs[index])
    return node.outputs[0]


def _rotate_about_axis(nodes, links, gi, vector, angle):
    """VectorRotate ``vector`` about the group's axis by ``angle`` (radians)."""
    rot = nodes.new("ShaderNodeVectorRotate")
    rot.rotation_type = "AXIS_ANGLE"
    links.new(vector, rot.inputs["Vector"])
    links.new(gi.outputs["Axis Origin"], rot.inputs["Center"])
    links.new(gi.outputs["Axis Direction"], rot.inputs["Axis"])
    links.new(angle, rot.inputs["Angle"])
    return rot.outputs["Vector"]


def build_revolve_node_group(name: str = REVOLVE_NODE_GROUP):
    """Build the from-source revolve group (idempotent).

    Reuses an existing group of the same name, rebuilding it in place when the
    stored version is stale -- so modifiers already bound to that name (including
    ones bound to the old binary asset) upgrade without rebinding. Returns the
    node group.
    """
    ng = bpy.data.node_groups.get(name)
    if ng is None:
        ng = bpy.data.node_groups.new(name, "GeometryNodeTree")

    # Offer it in the Add Modifier > Geometry Nodes picker (off by default for
    # API-created groups).
    ng.is_modifier = True

    if ng.get("cad_revolve_version") == REVOLVE_VERSION:
        return ng

    # Rebuilding replaces the interface, reassigning socket identifiers; preserve
    # the settings of any modifier already bound to this group (old asset or a
    # prior version) by re-applying them by socket name after the rebuild.
    saved = _snapshot_modifier_inputs(ng)

    ng.nodes.clear()
    ng.links.clear()
    ng.interface.clear()

    iface = ng.interface
    iface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    iface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    iface.new_socket("Axis Origin", in_out="INPUT", socket_type="NodeSocketVector")
    axis = iface.new_socket(
        "Axis Direction", in_out="INPUT", socket_type="NodeSocketVector"
    )
    axis.default_value = (0.0, 0.0, 1.0)
    angle = iface.new_socket("Angle", in_out="INPUT", socket_type="NodeSocketFloat")
    angle.subtype = "ANGLE"
    angle.default_value = math.tau
    resolution = iface.new_socket(
        "Angular Resolution", in_out="INPUT", socket_type="NodeSocketFloat"
    )
    resolution.subtype = "ANGLE"
    resolution.default_value = math.radians(2)
    resolution.min_value = math.radians(0.1)

    nodes, links = ng.nodes, ng.links
    gi = nodes.new("NodeGroupInput")
    go = nodes.new("NodeGroupOutput")

    # 1. Step count from the sweep angle and the max angle per segment:
    #    steps = max(1, ceil(|Angle| / Resolution)).
    abs_angle = _math(nodes, links, "ABSOLUTE", a=gi.outputs["Angle"])
    # Guard the divide: clamp resolution away from zero (the operator enforces a
    # positive minimum, but a hand-set 0 would otherwise blow up).
    safe_res = _math(
        nodes, links, "MAXIMUM", a=gi.outputs["Angular Resolution"], b=1e-4
    )
    steps_raw = _math(nodes, links, "DIVIDE", a=abs_angle, b=safe_res)
    steps_ceil = _math(nodes, links, "CEIL", a=steps_raw)
    steps = _math(nodes, links, "MAXIMUM", a=steps_ceil, b=1.0)

    # 2. Normalize the profile to a single boundary curve, independent of whether
    #    it arrived as a filled mesh, a wire mesh, or a curve.
    sep = nodes.new("GeometryNodeSeparateComponents")
    links.new(gi.outputs["Geometry"], sep.inputs["Geometry"])

    # Boundary edges of the mesh part: those with fewer than two adjacent faces
    # (1 = a fill boundary, 0 = a bare wire). Interior fill edges (2 faces) are
    # dropped, so tessellation never reaches the sweep.
    neighbors = nodes.new("GeometryNodeInputMeshEdgeNeighbors")
    boundary = nodes.new("FunctionNodeCompare")
    boundary.data_type = "INT"
    boundary.operation = "LESS_THAN"
    ba, bb = (s for s in boundary.inputs if s.enabled and s.type == "INT")
    bb.default_value = 2
    links.new(neighbors.outputs["Face Count"], ba)

    mesh_to_curve = nodes.new("GeometryNodeMeshToCurve")
    links.new(sep.outputs["Mesh"], mesh_to_curve.inputs["Mesh"])
    links.new(boundary.outputs["Result"], mesh_to_curve.inputs["Selection"])

    profile = nodes.new("GeometryNodeJoinGeometry")
    links.new(mesh_to_curve.outputs["Curve"], profile.inputs["Geometry"])
    links.new(sep.outputs["Curve"], profile.inputs["Geometry"])
    raw_profile = profile.outputs["Geometry"]

    # P = boundary-loop point count.
    domain = nodes.new("GeometryNodeAttributeDomainSize")
    domain.component = "CURVE"
    links.new(raw_profile, domain.inputs["Geometry"])
    point_count = domain.outputs["Point Count"]

    # Canonicalize the loop winding. Mesh to Curve extracts the boundary loop with
    # a shape-dependent direction, which would leave the swept surface and the
    # caps inconsistently oriented. Reverse the loop when its area normal points
    # against a reference derived from the axis, so every profile winds the same
    # way and a fixed cap orientation is coherent for all shapes.
    #
    # Area normal (Newell-style, translation invariant): N = sum_i (p_i - C) x
    # (p_{i+1} - C), with C the loop centroid.
    centroid = nodes.new("GeometryNodeAttributeStatistic")
    centroid.data_type = "FLOAT_VECTOR"
    centroid.domain = "POINT"
    loop_pos = nodes.new("GeometryNodeInputPosition")
    links.new(raw_profile, centroid.inputs["Geometry"])
    links.new(loop_pos.outputs["Position"], centroid.inputs["Attribute"])
    centroid_co = centroid.outputs["Mean"]

    loop_index = nodes.new("GeometryNodeInputIndex")
    next_index = _math(nodes, links, "ADD", a=loop_index.outputs["Index"], b=1.0)
    next_index = _math(nodes, links, "FLOORED_MODULO", a=next_index, b=point_count)
    next_pos = nodes.new("GeometryNodeSampleIndex")
    next_pos.data_type = "FLOAT_VECTOR"
    next_pos.domain = "POINT"
    links.new(raw_profile, next_pos.inputs["Geometry"])
    links.new(loop_pos.outputs["Position"], next_pos.inputs["Value"])
    links.new(next_index, next_pos.inputs["Index"])

    def _vsub(a, b):
        n = nodes.new("ShaderNodeVectorMath")
        n.operation = "SUBTRACT"
        links.new(a, n.inputs[0])
        links.new(b, n.inputs[1])
        return n.outputs["Vector"]

    def _vcross(a, b):
        n = nodes.new("ShaderNodeVectorMath")
        n.operation = "CROSS_PRODUCT"
        links.new(a, n.inputs[0])
        links.new(b, n.inputs[1])
        return n.outputs["Vector"]

    edge_term = _vcross(
        _vsub(loop_pos.outputs["Position"], centroid_co),
        _vsub(next_pos.outputs["Value"], centroid_co),
    )
    area_normal = nodes.new("GeometryNodeAttributeStatistic")
    area_normal.data_type = "FLOAT_VECTOR"
    area_normal.domain = "POINT"
    links.new(raw_profile, area_normal.inputs["Geometry"])
    links.new(edge_term, area_normal.inputs["Attribute"])

    # Reference: axis x (centroid - axis origin) -- the profile-plane normal for a
    # profile lying in a plane through the axis (the usual revolve setup).
    reference = _vcross(
        gi.outputs["Axis Direction"], _vsub(centroid_co, gi.outputs["Axis Origin"])
    )
    orient_dot = nodes.new("ShaderNodeVectorMath")
    orient_dot.operation = "DOT_PRODUCT"
    links.new(area_normal.outputs["Sum"], orient_dot.inputs[0])
    links.new(reference, orient_dot.inputs[1])
    against = nodes.new("FunctionNodeCompare")
    against.data_type = "FLOAT"
    against.operation = "LESS_THAN"
    ga, gb = (s for s in against.inputs if s.enabled and s.type == "VALUE")
    gb.default_value = 0.0
    links.new(orient_dot.outputs["Value"], ga)

    reverse = nodes.new("GeometryNodeReverseCurve")
    links.new(raw_profile, reverse.inputs["Curve"])
    links.new(against.outputs["Result"], reverse.inputs["Selection"])
    profile_curve = reverse.outputs["Curve"]

    # Whether the profile is a closed loop (cyclic). A closed profile needs one
    # extra "wrap" column so the last point connects back to the first; an open
    # profile (a line/arc -> a tube open along its length) must NOT wrap, or it
    # would sweep a phantom face across the profile ends. Sample spline 0's cyclic
    # flag (profiles are a single loop); Mesh to Curve sets it for closed
    # boundaries, and a raw curve carries its own.
    cyclic = nodes.new("GeometryNodeInputSplineCyclic")
    is_cyclic = nodes.new("GeometryNodeSampleIndex")
    is_cyclic.data_type = "BOOLEAN"
    is_cyclic.domain = "CURVE"
    links.new(profile_curve, is_cyclic.inputs["Geometry"])
    links.new(cyclic.outputs["Cyclic"], is_cyclic.inputs["Value"])
    is_cyclic.inputs["Index"].default_value = 0
    wrap = nodes.new("GeometryNodeSwitch")
    wrap.input_type = "INT"
    links.new(is_cyclic.outputs["Value"], wrap.inputs["Switch"])
    wrap.inputs["False"].default_value = 0
    wrap.inputs["True"].default_value = 1

    # 3. Lateral surface: a grid of (P + wrap) x (steps + 1) vertices. The wrap
    #    column closes a cyclic loop; the extra row carries the final angle.
    grid_x = _math(nodes, links, "ADD", a=point_count, b=wrap.outputs["Output"])
    grid_y = _math(nodes, links, "ADD", a=steps, b=1.0)
    grid = nodes.new("GeometryNodeMeshGrid")
    grid.inputs["Size X"].default_value = 1.0
    grid.inputs["Size Y"].default_value = 1.0
    links.new(grid_x, grid.inputs["Vertices X"])
    links.new(grid_y, grid.inputs["Vertices Y"])

    # Per-vertex column/row from the grid's UV (0..1 across each axis).
    uv = nodes.new("ShaderNodeSeparateXYZ")
    links.new(grid.outputs["UV Map"], uv.inputs["Vector"])
    # column = round(u * (grid_x - 1)); profile index = column mod P, so on a
    # cyclic profile the wrap column (P) folds back to point 0.
    cols_max = _math(nodes, links, "SUBTRACT", a=grid_x, b=1.0)
    col = _math(nodes, links, "MULTIPLY", a=uv.outputs["X"], b=cols_max)
    col = _math(nodes, links, "ROUND", a=col)
    index = _math(nodes, links, "FLOORED_MODULO", a=col, b=point_count)
    step_angle = _math(
        nodes, links, "MULTIPLY", a=gi.outputs["Angle"], b=uv.outputs["Y"]
    )

    # Sample the profile point at that index and rotate it to this step's angle.
    position = nodes.new("GeometryNodeInputPosition")
    sample = nodes.new("GeometryNodeSampleIndex")
    sample.data_type = "FLOAT_VECTOR"
    sample.domain = "POINT"
    links.new(profile_curve, sample.inputs["Geometry"])
    links.new(position.outputs["Position"], sample.inputs["Value"])
    links.new(index, sample.inputs["Index"])

    swept = _rotate_about_axis(nodes, links, gi, sample.outputs["Value"], step_angle)
    set_pos = nodes.new("GeometryNodeSetPosition")
    links.new(grid.outputs["Mesh"], set_pos.inputs["Geometry"])
    links.new(swept, set_pos.inputs["Position"])
    lateral_raw = set_pos.outputs["Geometry"]

    # Weld the swept grid's seams (the wrap column, and the start/end seam at a
    # full turn) so the lateral tube is clean before capping.
    lateral_weld = nodes.new("GeometryNodeMergeByDistance")
    links.new(lateral_raw, lateral_weld.inputs["Geometry"])
    lateral_weld.inputs["Distance"].default_value = _WELD_DISTANCE
    lateral = lateral_weld.outputs["Geometry"]

    # 4. End caps: only for a *filled* profile swept a *partial* turn.
    face_count = nodes.new("GeometryNodeAttributeDomainSize")
    face_count.component = "MESH"
    links.new(gi.outputs["Geometry"], face_count.inputs["Geometry"])
    filled = nodes.new("FunctionNodeCompare")
    filled.data_type = "INT"
    filled.operation = "GREATER_THAN"
    fa, fb = (s for s in filled.inputs if s.enabled and s.type == "INT")
    fb.default_value = 0
    links.new(face_count.outputs["Face Count"], fa)

    # Partial turn: |Angle| < tau (with a small margin so a full turn reads as
    # closed and gets no caps).
    partial = nodes.new("FunctionNodeCompare")
    partial.data_type = "FLOAT"
    partial.operation = "LESS_THAN"
    pa, pb = (s for s in partial.inputs if s.enabled and s.type == "VALUE")
    pb.default_value = math.tau - 1e-4
    links.new(abs_angle, pa)

    # Caps fill the (canonicalized) boundary loop the lateral is swept from, so
    # they weld exactly onto the tube's open ends. With the loop winding
    # deterministic, the end cap keeps the fill winding and the start cap (at
    # angle 0) is flipped, so the two caps wind oppositely and stay coherent with
    # the lateral for every profile shape. They close a *partial* turn (a full
    # turn already closes on itself).
    cap_fill = nodes.new("GeometryNodeFillCurve")
    links.new(profile_curve, cap_fill.inputs["Curve"])
    cap_mesh = cap_fill.outputs["Mesh"]

    start_flip = nodes.new("GeometryNodeFlipFaces")
    links.new(cap_mesh, start_flip.inputs["Mesh"])

    end_position = nodes.new("GeometryNodeInputPosition")
    end_rot = _rotate_about_axis(
        nodes, links, gi, end_position.outputs["Position"], gi.outputs["Angle"]
    )
    end_moved = nodes.new("GeometryNodeSetPosition")
    links.new(cap_mesh, end_moved.inputs["Geometry"])
    links.new(end_rot, end_moved.inputs["Position"])

    caps = nodes.new("GeometryNodeJoinGeometry")
    links.new(start_flip.outputs["Mesh"], caps.inputs["Geometry"])
    links.new(end_moved.outputs["Geometry"], caps.inputs["Geometry"])

    caps_switch = nodes.new("GeometryNodeSwitch")
    caps_switch.input_type = "GEOMETRY"
    links.new(partial.outputs["Result"], caps_switch.inputs["Switch"])
    links.new(caps.outputs["Geometry"], caps_switch.inputs["True"])

    # 5. A closed version (tube + caps) serves as the filled output *and* as the
    #    reference for deciding orientation. The unfilled output is the bare tube.
    closed_join = nodes.new("GeometryNodeJoinGeometry")
    links.new(lateral, closed_join.inputs["Geometry"])
    links.new(caps_switch.outputs["Output"], closed_join.inputs["Geometry"])
    closed_weld = nodes.new("GeometryNodeMergeByDistance")
    links.new(closed_join.outputs["Geometry"], closed_weld.inputs["Geometry"])
    closed_weld.inputs["Distance"].default_value = _WELD_DISTANCE
    closed = closed_weld.outputs["Geometry"]

    # 6. Consistent outward normals for BOTH fill states and BOTH angle signs.
    #    After canonicalization the coherent orientation still faces out or in
    #    depending on the profile and the sign of the sweep angle. Decide from the
    #    *closed* solid's signed volume (divergence theorem: sum over faces of
    #    dot(centroid, normal) * area) and flip when it is inside-out. The same
    #    decision drives the open shell, so an unfilled revolve keeps a consistent
    #    orientation regardless of angle direction too.
    position = nodes.new("GeometryNodeInputPosition")
    normal = nodes.new("GeometryNodeInputNormal")
    face_area = nodes.new("GeometryNodeInputMeshFaceArea")
    flux = nodes.new("ShaderNodeVectorMath")
    flux.operation = "DOT_PRODUCT"
    links.new(position.outputs["Position"], flux.inputs[0])
    links.new(normal.outputs["Normal"], flux.inputs[1])
    term = _math(
        nodes, links, "MULTIPLY", a=flux.outputs["Value"], b=face_area.outputs["Area"]
    )
    volume = nodes.new("GeometryNodeAttributeStatistic")
    volume.data_type = "FLOAT"
    volume.domain = "FACE"
    links.new(closed, volume.inputs["Geometry"])
    links.new(term, volume.inputs["Attribute"])

    inside_out = nodes.new("FunctionNodeCompare")
    inside_out.data_type = "FLOAT"
    inside_out.operation = "LESS_THAN"
    va, vb = (s for s in inside_out.inputs if s.enabled and s.type == "VALUE")
    vb.default_value = 0.0
    links.new(volume.outputs["Sum"], va)

    # Filled -> the closed solid; unfilled -> the open tube. Both take the flip.
    output_geo = nodes.new("GeometryNodeSwitch")
    output_geo.input_type = "GEOMETRY"
    links.new(filled.outputs["Result"], output_geo.inputs["Switch"])
    links.new(lateral, output_geo.inputs["False"])
    links.new(closed, output_geo.inputs["True"])

    flipped = nodes.new("GeometryNodeFlipFaces")
    links.new(output_geo.outputs["Output"], flipped.inputs["Mesh"])

    orient = nodes.new("GeometryNodeSwitch")
    orient.input_type = "GEOMETRY"
    links.new(inside_out.outputs["Result"], orient.inputs["Switch"])
    links.new(output_geo.outputs["Output"], orient.inputs["False"])
    links.new(flipped.outputs["Mesh"], orient.inputs["True"])
    links.new(orient.outputs["Output"], go.inputs["Geometry"])

    _restore_modifier_inputs(ng, saved)
    ng["cad_revolve_version"] = REVOLVE_VERSION
    return ng
