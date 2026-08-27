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
that first *normalizes* whatever profile it is handed down to its boundary
loop(s), so the swept lateral surface is identical whether ``Fill`` was on or off:

    * a mesh (filled or a wire) -> its boundary edges become a curve
      (``Mesh to Curve`` selecting edges with fewer than two adjacent faces),
    * a curve passes straight through,

joined into one boundary curve, which may contain *several* loops (a profile with
a hole has an outer loop and one inner loop per hole). Only those loops are swept,
so interior fill triangulation can never leak into the surface.

The lateral surface is swept by *extrusion* rather than a single grid, so any
number of boundary loops are handled independently -- a profile with a hole
revolves to a proper solid with a void through it, instead of the inner loop being
bridged to the outer one. A ``Fill Curve`` of the profile (which resolves holes by
even-odd containment) seeds a mesh whose rim is repeatedly extruded and rotated by
one angular step; the extruded top ring is recorded (as an edge attribute) and
becomes the next rim. The seed cap is stripped afterwards, leaving the bare
lateral. An *open* profile (a line/arc, not fillable) seeds the sweep from its
wire instead, giving an open tube (a cylinder). Extrusion keeps every face
coherent with its neighbour by construction, so no per-loop winding
canonicalization is needed.

End caps are added only when the profile was *filled* and the sweep is a partial
turn (< 360 deg): the seed cap (already coherent with the lateral it was extruded
from) serves as the start cap, and a copy rotated to the end angle and flipped is
the end cap, so the two wind oppositely and stay coherent -- holes included. A full
turn needs no caps (the surface closes on itself), and an unfilled profile has no
face to cap with -- it stays an open shell.

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
REVOLVE_VERSION = 6

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
    #    steps = max(1, ceil(|Angle| / Resolution)); delta = Angle / steps.
    abs_angle = _math(nodes, links, "ABSOLUTE", a=gi.outputs["Angle"])
    # Guard the divide: clamp resolution away from zero (the operator enforces a
    # positive minimum, but a hand-set 0 would otherwise blow up).
    safe_res = _math(
        nodes, links, "MAXIMUM", a=gi.outputs["Angular Resolution"], b=1e-4
    )
    steps_raw = _math(nodes, links, "DIVIDE", a=abs_angle, b=safe_res)
    steps_ceil = _math(nodes, links, "CEIL", a=steps_raw)
    steps = _math(nodes, links, "MAXIMUM", a=steps_ceil, b=1.0)
    delta = _math(nodes, links, "DIVIDE", a=gi.outputs["Angle"], b=steps)

    # 2. Normalize the profile to its boundary curve(s), independent of whether it
    #    arrived as a filled mesh, a wire mesh, or a curve. This may yield several
    #    loops (a holed profile: an outer loop plus one loop per hole).
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

    # 3. Fill the profile: a Fill Curve resolves holes by even-odd containment,
    #    so a holed profile becomes a region mesh with the correct boundary loops.
    #    Its rim seeds the sweep and (for a partial filled turn) supplies the caps.
    cap_fill = nodes.new("GeometryNodeFillCurve")
    links.new(raw_profile, cap_fill.inputs["Curve"])
    cap_mesh = cap_fill.outputs["Mesh"]

    # An open profile (a line/arc) can't be filled -> Fill Curve yields no faces.
    # Fall back to the profile's wire so it sweeps to an open tube (a cylinder).
    wire = nodes.new("GeometryNodeCurveToMesh")
    links.new(raw_profile, wire.inputs["Curve"])
    cap_faces = nodes.new("GeometryNodeAttributeDomainSize")
    cap_faces.component = "MESH"
    links.new(cap_mesh, cap_faces.inputs["Geometry"])
    fillable = nodes.new("FunctionNodeCompare")
    fillable.data_type = "INT"
    fillable.operation = "GREATER_THAN"
    fla, flb = (s for s in fillable.inputs if s.enabled and s.type == "INT")
    flb.default_value = 0
    links.new(cap_faces.outputs["Face Count"], fla)
    seed_pick = nodes.new("GeometryNodeSwitch")
    seed_pick.input_type = "GEOMETRY"
    links.new(fillable.outputs["Result"], seed_pick.inputs["Switch"])
    links.new(wire.outputs["Mesh"], seed_pick.inputs["False"])
    links.new(cap_mesh, seed_pick.inputs["True"])

    # Mark the initial rim: edges with fewer than two adjacent faces (a wire's
    # edges have 0, a cap's boundary 1, a cap's interior 2). This "rim" edge
    # attribute is carried through the sweep and refreshed each step from the
    # Extrude node's Top output, so rim tracking is identical for cap and wire.
    rim_neighbors = nodes.new("GeometryNodeInputMeshEdgeNeighbors")
    rim_cmp = nodes.new("FunctionNodeCompare")
    rim_cmp.data_type = "INT"
    rim_cmp.operation = "LESS_THAN"
    rca, rcb = (s for s in rim_cmp.inputs if s.enabled and s.type == "INT")
    rcb.default_value = 2
    links.new(rim_neighbors.outputs["Face Count"], rca)
    seed = nodes.new("GeometryNodeStoreNamedAttribute")
    seed.data_type = "BOOLEAN"
    seed.domain = "EDGE"
    seed.inputs["Name"].default_value = "rim"
    links.new(seed_pick.outputs["Output"], seed.inputs["Geometry"])
    links.new(rim_cmp.outputs["Result"], seed.inputs["Value"])
    seed_geo = seed.outputs["Geometry"]

    # The seed cap occupies the lowest face indices (extrusion only appends), so
    # it can be stripped by index afterwards to leave the bare lateral.
    seed_faces = nodes.new("GeometryNodeAttributeDomainSize")
    seed_faces.component = "MESH"
    links.new(seed_geo, seed_faces.inputs["Geometry"])
    seed_face_count = seed_faces.outputs["Face Count"]

    # 4. Sweep the lateral by extrusion: each step extrudes the current rim (offset
    #    zero, so the new ring starts coincident) and rotates that new ring by one
    #    angular step about the axis. Recording the extruded Top edges as the next
    #    rim makes every boundary loop advance independently -- a holed profile
    #    keeps its void instead of being bridged shut. Extrusion also keeps each
    #    new face coherent with its neighbour, so no winding fix-up is needed.
    repeat_in = nodes.new("GeometryNodeRepeatInput")
    repeat_out = nodes.new("GeometryNodeRepeatOutput")
    repeat_in.pair_with_output(repeat_out)
    links.new(steps, repeat_in.inputs["Iterations"])
    links.new(seed_geo, repeat_in.inputs["Geometry"])

    rim_read = nodes.new("GeometryNodeInputNamedAttribute")
    rim_read.data_type = "BOOLEAN"
    rim_read.inputs["Name"].default_value = "rim"
    extrude = nodes.new("GeometryNodeExtrudeMesh")
    extrude.mode = "EDGES"
    links.new(repeat_in.outputs["Geometry"], extrude.inputs["Mesh"])
    links.new(rim_read.outputs["Attribute"], extrude.inputs["Selection"])
    extrude.inputs["Offset Scale"].default_value = 0.0
    step_pos = nodes.new("GeometryNodeInputPosition")
    step_rot = _rotate_about_axis(
        nodes, links, gi, step_pos.outputs["Position"], delta
    )
    move_top = nodes.new("GeometryNodeSetPosition")
    links.new(extrude.outputs["Mesh"], move_top.inputs["Geometry"])
    links.new(extrude.outputs["Top"], move_top.inputs["Selection"])
    links.new(step_rot, move_top.inputs["Position"])
    next_rim = nodes.new("GeometryNodeStoreNamedAttribute")
    next_rim.data_type = "BOOLEAN"
    next_rim.domain = "EDGE"
    next_rim.inputs["Name"].default_value = "rim"
    links.new(move_top.outputs["Geometry"], next_rim.inputs["Geometry"])
    links.new(extrude.outputs["Top"], next_rim.inputs["Value"])
    links.new(next_rim.outputs["Geometry"], repeat_out.inputs["Geometry"])
    swept = repeat_out.outputs["Geometry"]

    # Strip the seed cap (faces below the seed face count) -> the bare lateral, an
    # open tube at both ends. Delete with EDGE_FACE, not ONLY_FACE: the seed cap's
    # *interior* fill edges (a fan's diagonals, or the bridge cuts that let a holed
    # region be filled) are used only by the deleted cap faces, so they must go too
    # -- otherwise a full turn (which adds no caps to cover them) would keep loose
    # interior edges inside the tube. The rim edges survive: they are still used by
    # the swept lateral faces. Vertices are kept (the rim shares them).
    face_index = nodes.new("GeometryNodeInputIndex")
    is_seed = nodes.new("FunctionNodeCompare")
    is_seed.data_type = "INT"
    is_seed.operation = "LESS_THAN"
    sia, sib = (s for s in is_seed.inputs if s.enabled and s.type == "INT")
    links.new(face_index.outputs["Index"], sia)
    links.new(seed_face_count, sib)
    strip = nodes.new("GeometryNodeDeleteGeometry")
    strip.domain = "FACE"
    strip.mode = "EDGE_FACE"
    links.new(swept, strip.inputs["Geometry"])
    links.new(is_seed.outputs["Result"], strip.inputs["Selection"])
    lateral = strip.outputs["Geometry"]

    # 5. End caps. The lateral was extruded FROM the seed cap, so the seed cap's
    #    winding is already coherent with it: reuse it, unflipped, as the start cap
    #    (angle 0). The end cap is the same cap rotated to the end angle and
    #    flipped, so the two wind oppositely and stay coherent with the tube (like
    #    the top and bottom of a prism) -- holes included.
    end_position = nodes.new("GeometryNodeInputPosition")
    end_rot = _rotate_about_axis(
        nodes, links, gi, end_position.outputs["Position"], gi.outputs["Angle"]
    )
    end_moved = nodes.new("GeometryNodeSetPosition")
    links.new(cap_mesh, end_moved.inputs["Geometry"])
    links.new(end_rot, end_moved.inputs["Position"])
    end_flip = nodes.new("GeometryNodeFlipFaces")
    links.new(end_moved.outputs["Geometry"], end_flip.inputs["Mesh"])
    caps = nodes.new("GeometryNodeJoinGeometry")
    links.new(cap_mesh, caps.inputs["Geometry"])
    links.new(end_flip.outputs["Mesh"], caps.inputs["Geometry"])

    # Caps are added only for a *filled* profile swept a *partial* turn: a full
    # turn closes on itself, and an unfilled profile stays an open shell.
    face_count = nodes.new("GeometryNodeAttributeDomainSize")
    face_count.component = "MESH"
    links.new(gi.outputs["Geometry"], face_count.inputs["Geometry"])
    filled = nodes.new("FunctionNodeCompare")
    filled.data_type = "INT"
    filled.operation = "GREATER_THAN"
    fa, fb = (s for s in filled.inputs if s.enabled and s.type == "INT")
    fb.default_value = 0
    links.new(face_count.outputs["Face Count"], fa)
    partial = nodes.new("FunctionNodeCompare")
    partial.data_type = "FLOAT"
    partial.operation = "LESS_THAN"
    pa, pb = (s for s in partial.inputs if s.enabled and s.type == "VALUE")
    pb.default_value = math.tau - 1e-4
    links.new(abs_angle, pa)
    cap_needed = nodes.new("FunctionNodeBooleanMath")
    cap_needed.operation = "AND"
    links.new(filled.outputs["Result"], cap_needed.inputs[0])
    links.new(partial.outputs["Result"], cap_needed.inputs[1])
    caps_switch = nodes.new("GeometryNodeSwitch")
    caps_switch.input_type = "GEOMETRY"
    links.new(cap_needed.outputs["Boolean"], caps_switch.inputs["Switch"])
    links.new(caps.outputs["Geometry"], caps_switch.inputs["True"])

    # The output geometry: lateral plus whatever caps apply, welded. The seed cap
    # was stripped, so the lateral's start ring welds onto the start cap, and a
    # full turn welds its start/end seam closed.
    out_join = nodes.new("GeometryNodeJoinGeometry")
    links.new(lateral, out_join.inputs["Geometry"])
    links.new(caps_switch.outputs["Output"], out_join.inputs["Geometry"])
    out_weld = nodes.new("GeometryNodeMergeByDistance")
    links.new(out_join.outputs["Geometry"], out_weld.inputs["Geometry"])
    out_weld.inputs["Distance"].default_value = _WELD_DISTANCE
    result = out_weld.outputs["Geometry"]

    # 6. Consistent outward normals for BOTH fill states and BOTH angle signs.
    #    Extrusion makes the surface coherent, but whether it faces out or in still
    #    depends on the profile and the sign of the sweep angle. Decide from an
    #    always-closed reference (lateral + both caps) via its signed volume
    #    (divergence theorem: sum over faces of dot(centroid, normal) * area) and
    #    flip the actual result when it is inside-out. The same decision drives the
    #    open shell, so an unfilled revolve stays consistent regardless of sign.
    ref_join = nodes.new("GeometryNodeJoinGeometry")
    links.new(lateral, ref_join.inputs["Geometry"])
    links.new(caps.outputs["Geometry"], ref_join.inputs["Geometry"])
    ref_weld = nodes.new("GeometryNodeMergeByDistance")
    links.new(ref_join.outputs["Geometry"], ref_weld.inputs["Geometry"])
    ref_weld.inputs["Distance"].default_value = _WELD_DISTANCE

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
    links.new(ref_weld.outputs["Geometry"], volume.inputs["Geometry"])
    links.new(term, volume.inputs["Attribute"])
    inside_out = nodes.new("FunctionNodeCompare")
    inside_out.data_type = "FLOAT"
    inside_out.operation = "LESS_THAN"
    va, vb = (s for s in inside_out.inputs if s.enabled and s.type == "VALUE")
    vb.default_value = 0.0
    links.new(volume.outputs["Sum"], va)

    flipped = nodes.new("GeometryNodeFlipFaces")
    links.new(result, flipped.inputs["Mesh"])
    orient = nodes.new("GeometryNodeSwitch")
    orient.input_type = "GEOMETRY"
    links.new(inside_out.outputs["Result"], orient.inputs["Switch"])
    links.new(result, orient.inputs["False"])
    links.new(flipped.outputs["Mesh"], orient.inputs["True"])
    links.new(orient.outputs["Output"], go.inputs["Geometry"])

    _restore_modifier_inputs(ng, saved)
    ng["cad_revolve_version"] = REVOLVE_VERSION
    return ng
