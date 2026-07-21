"""Geometry accessors backed by native curve data.

CurveRef and its typed subclasses (PointRef, LineRef, ArcRef, CircleRef)
wrap a (sketch, curve_id) pair and provide read/write access to geometry
stored in Blender's native Curves attributes.

Use the ``curve_ref()`` factory to get the right subclass for existing curves.
Use ``PointRef.create()``, ``LineRef.create()``, etc. to create new curves.
"""

import math

from mathutils import Matrix, Vector

from ..utilities.math import range_2pi, pol2cart


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
        from ..utilities.curve_data import remove_native_curve_by_id, invalidate_curve_id_cache
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
    """Ensure all standard attributes exist. Optionally init STRING attrs for a curve."""
    from ..utilities.curve_data import ensure_standard_attributes, init_string_attrs
    ensure_standard_attributes(curve_data)
    if curve_idx is not None:
        init_string_attrs(curve_data, curve_idx)


def _invalidate(sketch):
    from ..utilities.curve_data import invalidate_curve_id_cache
    invalidate_curve_id_cache(sketch)


def _build_arc_bezier(curve_data, curve_idx, center, start_co, end_co, is_cyclic=False):
    """Compute and set bezier positions + handles for an arc or circle curve."""
    from ..utilities.constants import FULL_TURN, HALF_TURN

    curve_slice = curve_data.curves[curve_idx]
    n_points = curve_slice.points_length
    first = curve_slice.points[0].index

    center_2d = Vector((center[0], center[1]))
    radius = (Vector((start_co[0], start_co[1])) - center_2d).length
    if radius < 1e-6:
        return

    if is_cyclic:
        angle_per_segment = FULL_TURN / n_points
        segment_count = n_points
        start_angle = 0.0
    else:
        s = Vector((start_co[0], start_co[1])) - center_2d
        e = Vector((end_co[0], end_co[1])) - center_2d
        total_angle = range_2pi(math.atan2(e[1], e[0]) - math.atan2(s[1], s[0]))
        segment_count = n_points - 1
        if segment_count == 0:
            return
        angle_per_segment = total_angle / segment_count
        start_angle = math.atan2(s[1], s[0])

    # Bezier handle offset
    n = FULL_TURN / angle_per_segment if angle_per_segment != 0 else 0
    if n == 0:
        return
    q = (4 / 3) * math.tan(HALF_TURN / (2 * n))
    base_offset = Vector((radius, q * radius))

    # Compute all point positions on the arc
    positions = []
    for i in range(n_points):
        a = start_angle + angle_per_segment * i
        positions.append(center_2d + Vector((radius * math.cos(a), radius * math.sin(a))))

    # Set positions
    for i in range(n_points):
        curve_data.points[first + i].position = positions[i].to_3d()

    locations = list(positions)
    if is_cyclic:
        locations.append(locations[0])

    attrs = curve_data.attributes
    hl = attrs.get("handle_left")
    hr = attrs.get("handle_right")
    if not hl or not hr:
        return

    bezier_indices = list(range(first, first + n_points))
    if is_cyclic:
        bezier_indices.append(first)

    from mathutils import Matrix as _Matrix
    for seg in range(segment_count):
        loc1, loc2 = locations[seg], locations[seg + 1]
        b1_idx, b2_idx = bezier_indices[seg], bezier_indices[seg + 1]

        for i, loc in enumerate((loc1, loc2)):
            pos = loc - center_2d
            angle = math.atan2(pos[1], pos[0])
            offset = base_offset.copy()
            if i == 1:
                offset[1] *= -1
            offset.rotate(_Matrix.Rotation(angle, 2))
            coord = (center_2d + offset).to_3d()
            if i == 0:
                hr.data[b1_idx].vector = coord
            else:
                hl.data[b2_idx].vector = coord

        if not is_cyclic:
            if seg == 0:
                pos = loc1 - center_2d
                angle = math.atan2(pos[1], pos[0])
                offset = base_offset.copy()
                offset[1] *= -1
                offset.rotate(_Matrix.Rotation(angle, 2))
                hl.data[b1_idx].vector = (center_2d + offset).to_3d()
            if seg == segment_count - 1:
                pos = loc2 - center_2d
                angle = math.atan2(pos[1], pos[0])
                offset = base_offset.copy()
                offset.rotate(_Matrix.Rotation(angle, 2))
                hr.data[b2_idx].vector = (center_2d + offset).to_3d()


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
        from ..utilities.curve_data import set_attribute, default_curve_name
        from ..model.constants import SketchCurveType

        curve_data = _ensure_curve_data(sketch)
        if curve_data is None:
            return None

        cid = _allocate(sketch)
        curve_data.add_curves([1])
        _ensure_attrs(curve_data, len(curve_data.curves) - 1)

        curve_idx = len(curve_data.curves) - 1
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
        from ..utilities.curve_data import set_attribute, default_curve_name
        from ..model.constants import SketchCurveType, BezierHandleType

        curve_data = _ensure_curve_data(sketch)
        if curve_data is None:
            return None

        cid = _allocate(sketch)
        curve_data.add_curves([2])
        curve_data.set_types(type="BEZIER")
        _ensure_attrs(curve_data, len(curve_data.curves) - 1)

        curve_idx = len(curve_data.curves) - 1
        curve_slice = curve_data.curves[curve_idx]

        p1_co = p1.co if isinstance(p1, CurveRef) else p1
        p2_co = p2.co if isinstance(p2, CurveRef) else p2
        curve_slice.points[0].position = (float(p1_co[0]), float(p1_co[1]), 0.0)
        curve_slice.points[1].position = (float(p2_co[0]), float(p2_co[1]), 0.0)

        attrs = curve_data.attributes
        for pt in curve_slice.points:
            pos = curve_data.points[pt.index].position
            attrs["handle_left"].data[pt.index].vector = pos
            attrs["handle_right"].data[pt.index].vector = pos
            attrs["handle_type_left"].data[pt.index].value = BezierHandleType.FREE
            attrs["handle_type_right"].data[pt.index].value = BezierHandleType.FREE

        set_attribute(attrs, "curve_id", cid, curve_idx)
        set_attribute(attrs, "sketch_type", SketchCurveType.LINE, curve_idx)
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
        from ..utilities.curve_data import set_attribute, default_curve_name
        from ..model.constants import SketchCurveType, BezierHandleType
        from ..utilities.constants import QUARTER_TURN

        curve_data = _ensure_curve_data(sketch)
        if curve_data is None:
            return None

        # Compute arc angle to determine point count
        center = ct.co
        s = start.co - center
        e = end.co - center
        arc_angle = range_2pi(math.atan2(e[1], e[0]) - math.atan2(s[1], s[0]))
        n_segments = math.ceil(arc_angle / QUARTER_TURN)
        n_points = n_segments + 1

        cid = _allocate(sketch)
        curve_data.add_curves([n_points])
        curve_data.set_types(type="BEZIER")
        _ensure_attrs(curve_data, len(curve_data.curves) - 1)

        curve_idx = len(curve_data.curves) - 1
        curve_slice = curve_data.curves[curve_idx]

        attrs = curve_data.attributes
        for pt in curve_slice.points:
            attrs["handle_type_left"].data[pt.index].value = BezierHandleType.FREE
            attrs["handle_type_right"].data[pt.index].value = BezierHandleType.FREE

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

        # Compute bezier geometry
        _build_arc_bezier(curve_data, curve_idx, center, start.co, end.co)

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
        from ..utilities.curve_data import set_attribute, default_curve_name
        from ..model.constants import SketchCurveType, BezierHandleType

        curve_data = _ensure_curve_data(sketch)
        if curve_data is None:
            return None

        n_points = 4  # 4-segment bezier circle

        cid = _allocate(sketch)
        curve_data.add_curves([n_points])
        curve_data.set_types(type="BEZIER")
        _ensure_attrs(curve_data, len(curve_data.curves) - 1)

        curve_idx = len(curve_data.curves) - 1
        curve_slice = curve_data.curves[curve_idx]

        attrs = curve_data.attributes
        for pt in curve_slice.points:
            attrs["handle_type_left"].data[pt.index].value = BezierHandleType.FREE
            attrs["handle_type_right"].data[pt.index].value = BezierHandleType.FREE

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

        # Compute bezier geometry — use start point at (center.x + radius, center.y)
        center = ct.co
        start_co = Vector((center.x + radius, center.y))
        _build_arc_bezier(curve_data, curve_idx, center, start_co, start_co, is_cyclic=True)

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
    from ..utilities.curve_data import get_curve_type
    from ..model.constants import SketchCurveType

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
