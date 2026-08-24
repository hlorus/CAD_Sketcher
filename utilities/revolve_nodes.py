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

The lateral surface is a Grid of ``(P+1) x (steps+1)`` vertices -- ``P`` profile
points (plus one wrap column to close the loop) by one column per angular step --
whose every vertex is the matching profile point rotated about the axis by its
step's angle. ``Merge by Distance`` welds the wrap column and, at a full turn,
the start/end seam.

End caps are added only when the profile was *filled* and the sweep is a partial
turn (< 360 deg): the filled face at the start, and a copy rotated to the end.
A full turn needs no caps (the surface closes on itself), and an unfilled profile
has no face to cap with -- it stays an open shell. This matches the spec: a
non-filled sketch revolves to a valid surface, just without end caps.
"""

import math

import bpy

REVOLVE_NODE_GROUP = "CAD Sketcher Revolve"

# Bump whenever the built tree changes so groups baked into existing files -- or a
# stale same-named binary asset -- are rebuilt in place on next use, keeping
# modifiers bound to the same name.
REVOLVE_VERSION = 2

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
    profile_curve = profile.outputs["Geometry"]

    # P = boundary-loop point count.
    domain = nodes.new("GeometryNodeAttributeDomainSize")
    domain.component = "CURVE"
    links.new(profile_curve, domain.inputs["Geometry"])
    point_count = domain.outputs["Point Count"]

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
    lateral = set_pos.outputs["Geometry"]

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

    caps_needed = nodes.new("FunctionNodeBooleanMath")
    caps_needed.operation = "AND"
    links.new(filled.outputs["Result"], caps_needed.inputs[0])
    links.new(partial.outputs["Result"], caps_needed.inputs[1])

    # Start cap: the filled face at angle 0 (flip so its normal faces outward,
    # away from the sweep). End cap: the same face rotated to the sweep's end.
    start_flip = nodes.new("GeometryNodeFlipFaces")
    links.new(sep.outputs["Mesh"], start_flip.inputs["Mesh"])

    end_position = nodes.new("GeometryNodeInputPosition")
    end_rot = _rotate_about_axis(
        nodes, links, gi, end_position.outputs["Position"], gi.outputs["Angle"]
    )
    end_cap = nodes.new("GeometryNodeSetPosition")
    links.new(sep.outputs["Mesh"], end_cap.inputs["Geometry"])
    links.new(end_rot, end_cap.inputs["Position"])

    caps = nodes.new("GeometryNodeJoinGeometry")
    links.new(start_flip.outputs["Mesh"], caps.inputs["Geometry"])
    links.new(end_cap.outputs["Geometry"], caps.inputs["Geometry"])

    caps_switch = nodes.new("GeometryNodeSwitch")
    caps_switch.input_type = "GEOMETRY"
    links.new(caps_needed.outputs["Boolean"], caps_switch.inputs["Switch"])
    links.new(caps.outputs["Geometry"], caps_switch.inputs["True"])

    # 5. Join caps onto the lateral surface and weld all coincident seams (wrap
    #    column, full-turn start/end, and the cap boundaries onto the lateral
    #    ends) in one pass, giving a closed solid where applicable.
    result = nodes.new("GeometryNodeJoinGeometry")
    links.new(lateral, result.inputs["Geometry"])
    links.new(caps_switch.outputs["Output"], result.inputs["Geometry"])

    weld = nodes.new("GeometryNodeMergeByDistance")
    links.new(result.outputs["Geometry"], weld.inputs["Geometry"])
    weld.inputs["Distance"].default_value = _WELD_DISTANCE
    welded = weld.outputs["Geometry"]

    # 6. Consistent outward normals. The boundary loop that Mesh to Curve extracts
    #    from a fill triangulation has no deterministic winding, so the swept solid
    #    can come out inside-out for some profile shapes. For a *filled* profile
    #    (which yields a closed solid) compute the signed volume via the divergence
    #    theorem -- sum over faces of dot(centroid, normal) * area -- and flip the
    #    whole mesh when it is negative, so normals always point outward regardless
    #    of the profile's shape. Unfilled profiles are an open shell (no meaningful
    #    volume) and are left as-is.
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
    links.new(welded, volume.inputs["Geometry"])
    links.new(term, volume.inputs["Attribute"])

    inside_out = nodes.new("FunctionNodeCompare")
    inside_out.data_type = "FLOAT"
    inside_out.operation = "LESS_THAN"
    va, vb = (s for s in inside_out.inputs if s.enabled and s.type == "VALUE")
    vb.default_value = 0.0
    links.new(volume.outputs["Sum"], va)

    flip_needed = nodes.new("FunctionNodeBooleanMath")
    flip_needed.operation = "AND"
    links.new(filled.outputs["Result"], flip_needed.inputs[0])
    links.new(inside_out.outputs["Result"], flip_needed.inputs[1])

    flipped = nodes.new("GeometryNodeFlipFaces")
    links.new(welded, flipped.inputs["Mesh"])

    orient = nodes.new("GeometryNodeSwitch")
    orient.input_type = "GEOMETRY"
    links.new(flip_needed.outputs["Boolean"], orient.inputs["Switch"])
    links.new(welded, orient.inputs["False"])
    links.new(flipped.outputs["Mesh"], orient.inputs["True"])
    links.new(orient.outputs["Output"], go.inputs["Geometry"])

    _restore_modifier_inputs(ng, saved)
    ng["cad_revolve_version"] = REVOLVE_VERSION
    return ng
