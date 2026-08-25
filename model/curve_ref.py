"""Geometry accessors backed by native curve data.

CurveRef and its typed subclasses (PointRef, LineRef, ArcRef, CircleRef)
wrap a (sketch, curve_id) pair and provide read/write access to geometry
stored in Blender's native Curves attributes.

Use the ``curve_ref()`` factory to get the right subclass for existing curves.
Use ``PointRef.create()``, ``LineRef.create()``, etc. to create new curves.
"""

import math

from mathutils import Matrix, Vector

from ..utilities.math import pol2cart, range_2pi

# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class CurveRef:
    """Base accessor for a curve element within a sketch.

    Provides identity, validity check, type queries, and shared helpers.
    Use the ``curve_ref()`` factory instead of instantiating directly.
    """

    __slots__ = ("_sketch", "_curve_id", "_curve_data", "_idx", "_curve_slice")

    def __init__(self, sketch, curve_id):
        self._sketch = sketch
        self._curve_id = curve_id
        self._curve_data = None
        self._idx = None
        self._curve_slice = None

    # -- Resolution --

    def _resolve(self):
        from ..utilities.curve_data import get_curve_data
        cd, idx, cs = get_curve_data(self._sketch, self._curve_id)
        if cd is None:
            self._curve_data = None
            self._idx = None
            self._curve_slice = None
            return False
        self._curve_data = cd
        self._idx = idx
        self._curve_slice = cs
        return True

    @property
    def valid(self):
        return self._resolve()

    @property
    def sketch(self):
        return self._sketch

    @property
    def curve_id(self):
        return self._curve_id

    # -- Type checks (overridden by subclasses) --

    def is_point(self):
        return False

    def is_line(self):
        return False

    def is_curve(self):
        return False

    @property
    def location(self):
        """Fallback location for unresolved refs."""
        return Vector((0, 0, 0))

    @property
    def co(self):
        """Fallback 2D position for unresolved refs."""
        return Vector((0, 0))

    def is_arc(self):
        return False

    def is_circle(self):
        return False

    def is_closed(self):
        if not self._resolve():
            return False
        return self._curve_slice.use_cyclic

    def is_2d(self):
        return True

    def is_3d(self):
        return False

    # -- Shared attribute helpers --

    def _get_attr_value(self, attr_name, default=None):
        if not self._resolve():
            return default
        from ..utilities.curve_data import UUID_FIELDS, get_uuid, has_uuid_field
        if attr_name in UUID_FIELDS:
            if not has_uuid_field(self._curve_data, attr_name):
                return default
            return get_uuid(self._curve_data, attr_name, self._idx)
        attr = self._curve_data.attributes.get(attr_name)
        if not attr:
            return default
        v = attr.data[self._idx].value
        return v.decode() if isinstance(v, bytes) else v

    def _set_attr_value(self, attr_name, value):
        if not self._resolve():
            return
        from ..utilities.curve_data import set_attribute
        set_attribute(self._curve_data.attributes, attr_name, value, self._idx)

    def _get_related_ref(self, attr_name):
        cid = self._get_attr_value(attr_name, "")
        if not cid:
            return None
        return PointRef(self._sketch, cid)

    def _first_point_2d(self):
        """Local 2D position of the first curve point."""
        if not self._resolve():
            return Vector((0, 0))
        pt_idx = self._curve_slice.points[0].index
        pos = self._curve_data.points[pt_idx].position
        return Vector((pos[0], pos[1]))

    def _first_point_3d(self):
        """Local 3D position of the first curve point."""
        if not self._resolve():
            return Vector((0, 0, 0))
        pt_idx = self._curve_slice.points[0].index
        return Vector(self._curve_data.points[pt_idx].position)

    # -- Workplane --

    @property
    def wp_matrix(self):
        obj = self._sketch.target_object
        if obj and obj.parent:
            return obj.parent.matrix_world
        if obj:
            return obj.matrix_world
        return Matrix.Identity(4)

    # -- Flags (read/write) --

    @property
    def construction(self):
        return bool(self._get_attr_value("construction", False))

    @construction.setter
    def construction(self, value):
        self._set_attr_value("construction", bool(value))

    @property
    def fixed(self):
        return bool(self._get_attr_value("fixed", False))

    @fixed.setter
    def fixed(self, value):
        self._set_attr_value("fixed", bool(value))

    @property
    def visible(self):
        return bool(self._get_attr_value("visible", True))

    @visible.setter
    def visible(self, value):
        self._set_attr_value("visible", bool(value))

    @property
    def name(self):
        """User-facing name stored on the curve (falls back to the type)."""
        return self._get_attr_value("name", "") or self._type_label

    @name.setter
    def name(self, value):
        self._set_attr_value("name", value)

    # -- UI --

    def draw_props(self, layout):
        from ..declarations import Operators

        layout.label(text=str(self))
        layout.separator()

        col = layout.column()
        for flag in ("construction", "fixed", "visible"):
            val = getattr(self, flag)
            op = col.operator(
                Operators.SetCurveFlag,
                text=flag.capitalize(),
                icon="CHECKBOX_HLT" if val else "CHECKBOX_DEHLT",
            )
            op.curve_id = self._curve_id
            op.flag = flag
            op.value = not val

    # -- Deletion --

    def remove(self):
        """Remove this curve from the sketch."""
        from ..utilities.curve_data import (
            remove_native_curve_by_id,
        )
        remove_native_curve_by_id(self._sketch, self._curve_id)
        self._curve_data = None
        self._idx = None
        self._curve_slice = None

    # -- Identity --

    def __eq__(self, other):
        if isinstance(other, CurveRef):
            return self._sketch == other._sketch and self._curve_id == other._curve_id
        return NotImplemented

    def __hash__(self):
        return hash((id(self._sketch), self._curve_id))

    _type_label = "Curve"

    def __str__(self):
        return self._type_label

    def __repr__(self):
        return f"{type(self).__name__}(sketch={self._sketch.name!r}, id={self._curve_id})"


# ---------------------------------------------------------------------------
# Shared creation helpers
# ---------------------------------------------------------------------------

def _ensure_curve_data(sketch):
    """Ensure sketch has a curve object, return curve_data."""
    from ..utilities.curve_data import ensure_sketch_curve_object
    return ensure_sketch_curve_object(sketch)


def _allocate(sketch):
    """Allocate a new curve_id."""
    from ..utilities.curve_data import _allocate_curve_id
    return _allocate_curve_id(sketch)


def _ensure_attrs(curve_data, curve_idx=None):
    """Ensure standard and user-defined attributes exist for a new curve."""
    from ..utilities.curve_data import ensure_standard_attributes, init_string_attrs
    from ..utilities.custom_attributes import initialize_curve_defaults
    ensure_standard_attributes(curve_data)
    if curve_idx is not None:
        init_string_attrs(curve_data, curve_idx)
        initialize_curve_defaults(curve_data, curve_idx)


def _invalidate(sketch):
    from ..utilities.curve_data import (
        compute_merge_ids,
        invalidate_curve_id_cache,
        is_batching,
    )

    invalidate_curve_id_cache(sketch)
    # A newly created segment changes connectivity, so refresh the derived weld
    # ids (before update_tag, so the live GN fill closes the same frame). Under a
    # batch this is deferred to rebuild_segments on the batch's exit.
    if not is_batching(sketch):
        compute_merge_ids(sketch)


# Rational NURBS conic settings. Order 3 (degree 2) with the ENDPOINT_BEZIER knot
# mode (Blender knots_mode enum value 3) turns each control triple into a rational
# Bezier span, so weighted conics evaluate exactly at any resolution.
_NURBS_CONIC_ORDER = 3
_KNOTS_ENDPOINT_BEZIER = 3

# Periodic 8-point control net for an exact unit circle: on-circle midpoints
# (weight 1) interleaved with off-circle square corners (weight sqrt(2)/2). Scaled
# by radius and offset by the centre at build time. Point 0 is the +X on-circle
# point, matching where the solver writes the radius edge (curve_solver 2nd pass).
_CIRCLE_NURBS_CONTROL = (
    ((1.0, 0.0), 1.0),
    ((1.0, 1.0), math.sqrt(2.0) / 2.0),
    ((0.0, 1.0), 1.0),
    ((-1.0, 1.0), math.sqrt(2.0) / 2.0),
    ((-1.0, 0.0), 1.0),
    ((-1.0, -1.0), math.sqrt(2.0) / 2.0),
    ((0.0, -1.0), 1.0),
    ((1.0, -1.0), math.sqrt(2.0) / 2.0),
)
CIRCLE_NURBS_POINTS = len(_CIRCLE_NURBS_CONTROL)


def _build_circle_nurbs(curve_data, curve_idx, center, radius):
    """Write an exact periodic rational-NURBS circle (positions + weights + order).

    The circle must be cyclic (set by the caller); with the periodic control net
    and ENDPOINT_BEZIER knots this evaluates to a mathematically exact circle.
    """
    attrs = curve_data.attributes
    weight = attrs.get("nurbs_weight")
    order = attrs.get("nurbs_order")
    knots = attrs.get("knots_mode")
    cx, cy = center[0], center[1]
    curve_slice = curve_data.curves[curve_idx]
    for pt, ((ox, oy), wt) in zip(curve_slice.points, _CIRCLE_NURBS_CONTROL):
        curve_data.points[pt.index].position = (cx + ox * radius, cy + oy * radius, 0.0)
        if weight is not None:
            weight.data[pt.index].value = wt
    if order is not None:
        order.data[curve_idx].value = _NURBS_CONIC_ORDER
    if knots is not None:
        knots.data[curve_idx].value = _KNOTS_ENDPOINT_BEZIER


def _build_arc_nurbs(curve_data, curve_idx, center, start_co, end_co):
    """Write an exact rational-NURBS arc: positions + weights (+ order/knots).

    The sweep is split into <=90 deg spans; each span is a rational-quadratic
    Bezier segment -- on-circle endpoints (weight 1) with an off-circle shoulder
    control point at ``radius / cos(span/2)`` on the span bisector (weight
    ``cos(span/2)``). Adjacent spans share their on-circle junction, so the control
    net is ``2*nseg + 1`` points: on0, shoulder0, on1, shoulder1, ..., onN. With
    order 3 and ENDPOINT_BEZIER knots this evaluates to the exact arc at any
    resolution. The caller (create / resegment) sizes the curve to 2*nseg+1.
    """
    curve_slice = curve_data.curves[curve_idx]
    n_points = curve_slice.points_length
    first = curve_slice.points[0].index
    n_seg = (n_points - 1) // 2
    if n_seg < 1:
        return

    center_2d = Vector((center[0], center[1]))
    s = Vector((start_co[0], start_co[1])) - center_2d
    radius = s.length
    if radius < 1e-6:
        return
    e = Vector((end_co[0], end_co[1])) - center_2d
    total_angle = range_2pi(math.atan2(e[1], e[0]) - math.atan2(s[1], s[0]))
    start_angle = math.atan2(s[1], s[0])
    span = total_angle / n_seg
    half = span / 2.0
    cos_half = math.cos(half)
    shoulder_w = cos_half
    shoulder_r = radius / cos_half if abs(cos_half) > 1e-9 else radius

    attrs = curve_data.attributes
    weight = attrs.get("nurbs_weight")

    def _on(angle):
        return (center_2d + Vector((radius * math.cos(angle),
                                    radius * math.sin(angle)))).to_3d()

    def _shoulder(angle):
        return (center_2d + Vector((shoulder_r * math.cos(angle),
                                    shoulder_r * math.sin(angle)))).to_3d()

    idx = first
    curve_data.points[idx].position = _on(start_angle)
    if weight is not None:
        weight.data[idx].value = 1.0
    idx += 1
    for seg in range(n_seg):
        seg_start = start_angle + span * seg
        curve_data.points[idx].position = _shoulder(seg_start + half)
        if weight is not None:
            weight.data[idx].value = shoulder_w
        idx += 1
        curve_data.points[idx].position = _on(seg_start + span)
        if weight is not None:
            weight.data[idx].value = 1.0
        idx += 1

    order = attrs.get("nurbs_order")
    knots = attrs.get("knots_mode")
    if order is not None:
        order.data[curve_idx].value = _NURBS_CONIC_ORDER
    if knots is not None:
        knots.data[curve_idx].value = _KNOTS_ENDPOINT_BEZIER


# ---------------------------------------------------------------------------
# PointRef
# ---------------------------------------------------------------------------

class PointRef(CurveRef):
    """Accessor for a point curve (1-point curve)."""

    __slots__ = ()
    _type_label = "Point"

    def is_point(self):
        return True

    @property
    def co(self):
        """Local 2D position."""
        return self._first_point_2d()

    @co.setter
    def co(self, value):
        """Set local 2D position and rebuild referencing segments."""
        if not self._resolve():
            return
        pt_idx = self._curve_slice.points[0].index
        self._curve_data.points[pt_idx].position = (float(value[0]), float(value[1]), 0.0)
        from ..utilities.curve_data import is_batching, rebuild_segments
        if not is_batching(self._sketch):
            rebuild_segments(self._sketch)

    @property
    def location(self):
        """World-space 3D position."""
        pos = self._first_point_3d()
        mat = self._sketch.target_object.matrix_world
        return mat @ pos

    @staticmethod
    def create(sketch, co, construction=False, fixed=False, name=None):
        """Create a new point curve and return a PointRef.

        Args:
            sketch: The sketch to add the point to.
            co: 2D coordinates (x, y).
            construction: Whether this is a construction point.
            fixed: Whether this point is fixed.
            name: Optional display name; a default is generated when omitted.

        Returns:
            PointRef for the new curve.
        """
        from ..model.constants import SketchCurveType
        from ..utilities.curve_data import default_curve_name, set_attribute

        curve_data = _ensure_curve_data(sketch)
        if curve_data is None:
            return None

        cid = _allocate(sketch)
        curve_data.add_curves([1])
        curve_idx = len(curve_data.curves) - 1
        # A standalone point is a single POLY vertex (scoped, like the others).
        curve_data.set_types(type="POLY", indices=[curve_idx])
        _ensure_attrs(curve_data, curve_idx)

        curve_slice = curve_data.curves[curve_idx]
        curve_slice.points[0].position = (float(co[0]), float(co[1]), 0.0)

        attrs = curve_data.attributes
        set_attribute(attrs, "curve_id", cid, curve_idx)
        set_attribute(attrs, "sketch_type", SketchCurveType.POINT, curve_idx)
        set_attribute(attrs, "construction", construction, curve_idx)
        set_attribute(attrs, "fixed", fixed, curve_idx)
        set_attribute(attrs, "visible", True, curve_idx)
        set_attribute(attrs, "name",
                      name or default_curve_name(curve_data, SketchCurveType.POINT),
                      curve_idx)

        _invalidate(sketch)
        curve_data.update_tag()
        return PointRef(sketch, cid)


# ---------------------------------------------------------------------------
# LineRef
# ---------------------------------------------------------------------------

class LineRef(CurveRef):
    """Accessor for a line curve (2-point curve with start/end relationships)."""

    __slots__ = ()
    _type_label = "Line"

    def is_line(self):
        return True

    @property
    def p1(self):
        """Start point."""
        return self._get_related_ref("start_point_id")

    @property
    def p2(self):
        """End point."""
        return self._get_related_ref("end_point_id")

    def direction_vec(self):
        """Normalized direction from p1 to p2."""
        p1, p2 = self.p1, self.p2
        if p1 is None or p2 is None:
            return Vector((1, 0))
        vec = p2.co - p1.co
        if vec.length == 0:
            return Vector((1, 0))
        return vec.normalized()

    def midpoint(self):
        """Midpoint between p1 and p2."""
        p1, p2 = self.p1, self.p2
        if p1 is None or p2 is None:
            return Vector((0, 0))
        return (p1.co + p2.co) / 2

    @property
    def length(self):
        """Distance from p1 to p2."""
        p1, p2 = self.p1, self.p2
        if p1 is None or p2 is None:
            return 0.0
        return (p2.co - p1.co).length

    def normal(self):
        """Unit vector perpendicular to the line."""
        d = self.direction_vec()
        return Vector((-d.y, d.x))

    @staticmethod
    def create(sketch, p1, p2, construction=False, name=None):
        """Create a new line curve and return a LineRef.

        Args:
            sketch: The sketch to add the line to.
            p1: PointRef for start point.
            p2: PointRef for end point.
            construction: Whether this is a construction line.
            name: Optional display name; a default is generated when omitted.

        Returns:
            LineRef for the new curve.
        """
        from ..model.constants import SketchCurveType
        from ..utilities.curve_data import default_curve_name, set_attribute

        curve_data = _ensure_curve_data(sketch)
        if curve_data is None:
            return None

        cid = _allocate(sketch)
        curve_data.add_curves([2])
        curve_idx = len(curve_data.curves) - 1
        # A line is a straight two-point POLY curve: no handles, a single edge, and
        # its mesh vertices match the sketch endpoints exactly. Scope the type so
        # other NURBS/BEZIER curves in the datablock are untouched.
        curve_data.set_types(type="POLY", indices=[curve_idx])
        _ensure_attrs(curve_data, curve_idx)

        curve_slice = curve_data.curves[curve_idx]
        p1_co = p1.co if isinstance(p1, CurveRef) else p1
        p2_co = p2.co if isinstance(p2, CurveRef) else p2
        curve_slice.points[0].position = (float(p1_co[0]), float(p1_co[1]), 0.0)
        curve_slice.points[1].position = (float(p2_co[0]), float(p2_co[1]), 0.0)

        attrs = curve_data.attributes
        set_attribute(attrs, "curve_id", cid, curve_idx)
        set_attribute(attrs, "sketch_type", SketchCurveType.LINE, curve_idx)
        # POLY isn't tessellated, so resolution is moot; keep 1 for consistency.
        set_attribute(attrs, "resolution", 1, curve_idx)
        set_attribute(attrs, "start_point_id",
                      p1.curve_id if isinstance(p1, CurveRef) else "", curve_idx)
        set_attribute(attrs, "end_point_id",
                      p2.curve_id if isinstance(p2, CurveRef) else "", curve_idx)
        set_attribute(attrs, "construction", construction, curve_idx)
        set_attribute(attrs, "fixed", False, curve_idx)
        set_attribute(attrs, "visible", True, curve_idx)
        set_attribute(attrs, "name",
                      name or default_curve_name(curve_data, SketchCurveType.LINE),
                      curve_idx)

        _invalidate(sketch)
        curve_data.update_tag()
        return LineRef(sketch, cid)


# ---------------------------------------------------------------------------
# ArcRef
# ---------------------------------------------------------------------------

class ArcRef(CurveRef):
    """Accessor for an arc curve (multi-point bezier with center, start, end)."""

    __slots__ = ()
    _type_label = "Arc"

    def is_curve(self):
        return True

    def is_arc(self):
        return True

    @property
    def ct(self):
        """Center point."""
        return self._get_related_ref("center_point_id")

    @property
    def start(self):
        """Start point."""
        return self._get_related_ref("start_point_id")

    @property
    def end(self):
        """End point."""
        return self._get_related_ref("end_point_id")

    # Aliases matching old entity API
    p1 = start
    p2 = end

    @property
    def radius(self):
        """Distance from center to start point."""
        ct = self.ct
        if ct is None or not ct.valid:
            return 0.0
        start = self.start
        if start is None or not start.valid:
            center = ct.co
            edge = self._first_point_2d()
            return (edge - center).length
        return (ct.co - start.co).length

    @property
    def angle(self):
        """Arc angle in radians (0 to 2*pi)."""
        ct, start, end = self.ct, self.start, self.end
        if ct is None or start is None or end is None:
            return 0.0
        center = ct.co
        s = start.co - center
        e = end.co - center
        return range_2pi(math.atan2(e[1], e[0]) - math.atan2(s[1], s[0]))

    @property
    def start_angle(self):
        """Start angle in radians."""
        ct, start = self.ct, self.start
        if ct is None or start is None:
            return 0.0
        d = start.co - ct.co
        return math.atan2(d[1], d[0])

    def point_on_curve(self, angle, relative=True):
        """Position on the arc at the given angle."""
        ct = self.ct
        if ct is None:
            return Vector((0, 0))
        start_angle = self.start_angle if relative else 0
        return pol2cart(self.radius, start_angle + angle) + ct.co

    @staticmethod
    def create(sketch, ct, start, end, construction=False, name=None):
        """Create a new arc curve and return an ArcRef.

        Args:
            sketch: The sketch to add the arc to.
            ct: PointRef for center point.
            start: PointRef for start point.
            end: PointRef for end point.
            construction: Whether this is a construction arc.
            name: Optional display name; a default is generated when omitted.

        Returns:
            ArcRef for the new curve.
        """
        from ..model.constants import SketchCurveType
        from ..utilities.constants import QUARTER_TURN
        from ..utilities.curve_data import default_curve_name, set_attribute

        curve_data = _ensure_curve_data(sketch)
        if curve_data is None:
            return None

        # Split the sweep into <=90 deg spans; a rational NURBS arc needs
        # 2 control points per span plus the shared shoulders -> 2*nseg + 1.
        center = ct.co
        s = start.co - center
        e = end.co - center
        arc_angle = range_2pi(math.atan2(e[1], e[0]) - math.atan2(s[1], s[0]))
        n_segments = max(1, math.ceil(arc_angle / QUARTER_TURN))
        n_points = 2 * n_segments + 1

        cid = _allocate(sketch)
        curve_data.add_curves([n_points])
        curve_idx = len(curve_data.curves) - 1
        # Scope the type so existing POLY lines / other curves keep theirs.
        curve_data.set_types(type="NURBS", indices=[curve_idx])
        _ensure_attrs(curve_data, curve_idx)

        attrs = curve_data.attributes
        set_attribute(attrs, "curve_id", cid, curve_idx)
        set_attribute(attrs, "sketch_type", SketchCurveType.ARC, curve_idx)
        set_attribute(attrs, "center_point_id", ct.curve_id, curve_idx)
        set_attribute(attrs, "start_point_id", start.curve_id, curve_idx)
        set_attribute(attrs, "end_point_id", end.curve_id, curve_idx)
        set_attribute(attrs, "construction", construction, curve_idx)
        set_attribute(attrs, "fixed", False, curve_idx)
        set_attribute(attrs, "visible", True, curve_idx)
        set_attribute(attrs, "name",
                      name or default_curve_name(curve_data, SketchCurveType.ARC),
                      curve_idx)

        _build_arc_nurbs(curve_data, curve_idx, center, start.co, end.co)

        _invalidate(sketch)
        curve_data.update_tag()
        return ArcRef(sketch, cid)


# ---------------------------------------------------------------------------
# CircleRef
# ---------------------------------------------------------------------------

class CircleRef(CurveRef):
    """Accessor for a circle curve (cyclic bezier with center)."""

    __slots__ = ()
    _type_label = "Circle"

    def is_curve(self):
        return True

    def is_circle(self):
        return True

    def is_closed(self):
        return True

    @property
    def ct(self):
        """Center point."""
        return self._get_related_ref("center_point_id")

    @property
    def radius(self):
        """Distance from center to first edge point."""
        ct = self.ct
        if ct is None or not ct.valid:
            return 0.0
        center = ct.co
        edge = self._first_point_2d()
        return (edge - center).length

    def point_on_curve(self, angle):
        """Position on the circle at the given angle."""
        ct = self.ct
        if ct is None:
            return Vector((0, 0))
        return pol2cart(self.radius, angle) + ct.co

    @staticmethod
    def create(sketch, ct, radius, construction=False, name=None):
        """Create a new circle curve and return a CircleRef.

        Args:
            sketch: The sketch to add the circle to.
            ct: PointRef for center point.
            radius: Circle radius.
            construction: Whether this is a construction circle.
            name: Optional display name; a default is generated when omitted.

        Returns:
            CircleRef for the new curve.
        """
        from ..model.constants import SketchCurveType
        from ..utilities.curve_data import default_curve_name, set_attribute

        curve_data = _ensure_curve_data(sketch)
        if curve_data is None:
            return None

        cid = _allocate(sketch)
        curve_data.add_curves([CIRCLE_NURBS_POINTS])
        curve_idx = len(curve_data.curves) - 1
        # Scope the type to just this curve so other POLY/BEZIER curves are untouched.
        curve_data.set_types(type="NURBS", indices=[curve_idx])
        _ensure_attrs(curve_data, curve_idx)

        attrs = curve_data.attributes
        set_attribute(attrs, "curve_id", cid, curve_idx)
        set_attribute(attrs, "sketch_type", SketchCurveType.CIRCLE, curve_idx)
        set_attribute(attrs, "center_point_id", ct.curve_id, curve_idx)
        set_attribute(attrs, "cyclic", True, curve_idx)
        set_attribute(attrs, "construction", construction, curve_idx)
        set_attribute(attrs, "fixed", False, curve_idx)
        set_attribute(attrs, "visible", True, curve_idx)
        set_attribute(attrs, "name",
                      name or default_curve_name(curve_data, SketchCurveType.CIRCLE),
                      curve_idx)

        _build_circle_nurbs(curve_data, curve_idx, ct.co, radius)

        _invalidate(sketch)
        curve_data.update_tag()
        return CircleRef(sketch, cid)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def curve_ref(sketch, curve_id):
    """Create the appropriate typed CurveRef subclass for a curve_id.

    Returns PointRef, LineRef, ArcRef, or CircleRef based on the
    sketch_type attribute, or a base CurveRef if the type is unknown.
    """
    from ..model.constants import SketchCurveType
    from ..utilities.curve_data import get_curve_type

    ctype = get_curve_type(sketch, curve_id)
    if ctype == SketchCurveType.POINT:
        return PointRef(sketch, curve_id)
    if ctype == SketchCurveType.LINE:
        return LineRef(sketch, curve_id)
    if ctype == SketchCurveType.ARC:
        return ArcRef(sketch, curve_id)
    if ctype == SketchCurveType.CIRCLE:
        return CircleRef(sketch, curve_id)
    return CurveRef(sketch, curve_id)
