import bpy
from bpy.types import PropertyGroup
from bpy.props import (
    CollectionProperty,
    PointerProperty,
    FloatProperty,
    IntProperty,
    BoolProperty,
    FloatVectorProperty,
    EnumProperty,
    StringProperty,
)

from . import functions
import gpu, bgl
from gpu_extras.batch import batch_for_shader
from . import global_data

from bpy_extras.view3d_utils import location_3d_to_region_2d
import math

from .solver import solve_system, Solver

vertex_shader = """
    uniform mat4 ModelViewProjectionMatrix;
    in vec3 pos;

    void main()
    {
      gl_Position = ModelViewProjectionMatrix * vec4(pos, 1.0);
    }
"""


fragment_shader = """
    uniform vec4 color;
    out vec4 fragColor;

    void main()
    {
      fragColor = color;
    }
"""


class SlvsGenericEntity:
    slvs_index: IntProperty(name="Global Index", default=-1)
    fixed: BoolProperty(name="Fixed")
    visible: BoolProperty(name="Visible", default=True)
    origin: BoolProperty(name="Origin")
    construction: BoolProperty(name="Construction")

    _shader = gpu.shader.from_builtin("3D_UNIFORM_COLOR")
    _id_shader = gpu.types.GPUShader(vertex_shader, fragment_shader)

    point_size = 6
    point_size_select = 20

    @property
    def line_width(self):
        if self.construction:
            return 0.5
        return 2

    line_width_select = 20

    def __str__(self):
        return "Slvs Entity"

    @property
    def py_data(self):
        return global_data.entities[self.slvs_index]

    @py_data.setter
    def py_data(self, handle):
        global_data.entities[self.slvs_index] = handle

    # NOTE: It's not possible to store python runtime data on an instance of a PropertyGroup,
    # workaround this by saving python objects in a global list
    @property
    def _batch(self):
        return global_data.batches[self.slvs_index]

    @_batch.setter
    def _batch(self, value):
        global_data.batches[self.slvs_index] = value

    # NOTE: hover and select could be replaced by actual props with getter and setter funcs
    # selected: BoolProperty(name="Selected")

    @property
    def hover(self):
        return global_data.hover == self.slvs_index

    @hover.setter
    def hover(self, value):
        context = bpy.context
        if value:
            global_data.hover = self.slvs_index
        else:
            global_data.hover = None

    @property
    def selected(self):
        return self.slvs_index in global_data.selected

    @selected.setter
    def selected(self, value):
        slvs_index = self.slvs_index
        list = global_data.selected
        if slvs_index in list:
            i = list.index(slvs_index)
            if not value:
                list.pop(i)
        elif value:
            list.append(slvs_index)

    def is_active(self, context):
        active_sketch_i = context.scene.sketcher.active_sketch_i
        if hasattr(self, "sketch_i"):
            if self.sketch_i != active_sketch_i:
                return False
        elif active_sketch_i != -1:
            return False
        return True

    def color(self, context):
        prefs = functions.get_prefs()
        ts = prefs.theme_settings
        if not self.is_active(context):
            return ts.entity.inactive
        if self.selected:
            if self.hover:
                return ts.entity.selected_hovered
            else:
                return ts.entity.selected
        else:
            if self.hover:
                return ts.entity.hovered
            else:
                return ts.entity.default

    @staticmethod
    def restore_opengl_defaults():
        bgl.glLineWidth(1)
        bgl.glPointSize(1)  # ?
        bgl.glDisable(bgl.GL_BLEND)

    def is_visible(self, context):
        if self.origin:
            return context.scene.sketcher.show_origin
        return self.visible

    def draw(self, context):
        if not self.is_visible(context):
            return

        shader = self._shader
        shader.bind()

        bgl.glEnable(bgl.GL_BLEND)

        bgl.glPointSize(self.point_size)
        bgl.glLineWidth(self.line_width)

        col = self.color(context)
        shader.uniform_float("color", col)

        self._batch.draw(shader)

        self.restore_opengl_defaults()

    def draw_id(self, context):

        # Note: Design Question, should it be possible to select elements that are not active?!
        # e.g. to activate a sketch
        # maybe it should be dynamicly defined what is selectable (points only, lines only, ...)
        # if not self.is_visible(context):
        if not self.is_active(context):
            return

        batch = self._batch

        shader = self._id_shader
        shader.bind()

        bgl.glPointSize(self.point_size_select)
        bgl.glLineWidth(self.line_width_select)

        shader.uniform_float("color", (*functions.index_to_rgb(self.slvs_index), 1.0))
        batch.draw(shader)

        self.restore_opengl_defaults()

    def create_slvs_data(self, solvesys):
        """Create a solvespace entity from parameters"""
        raise NotImplementedError

    def update_from_slvs(self, solvesys):
        """Update parameters from the solvespace entity"""
        pass

    def update_pointers(self, index_old, index_new):
        for prop_name in dir(self):
            if not prop_name.endswith("_i"):
                continue
            prop = getattr(self, prop_name)
            if prop == index_old:
                setattr(self, prop_name, index_new)


# Drawing a point might not include points coord itself but rather a series of virtual points around it
# so a Entity might refere another point entity and/or add a set of coords
#
# Diffrent shaders are needed:
# - faces shader
# - outlines shader
# each needs a matching batch


def slvs_entity_pointer(cls, name, **kwargs):
    index_prop = name + "_i"
    annotations = {}
    if hasattr(cls, "__annotations__"):
        annotations = cls.__annotations__.copy()
    annotations[index_prop] = IntProperty(name=name + " index", default=-1, **kwargs)
    setattr(cls, "__annotations__", annotations)

    @property
    def func(self):
        index = getattr(self, index_prop)
        if index == -1:
            return None
        else:
            return bpy.context.scene.sketcher.entities.get(index)

    setattr(cls, name, func)

    @func.setter
    def setter(self, entity):
        setattr(self, index_prop, entity.slvs_index)

    setattr(cls, name, setter)


class SlvsPoint3D(SlvsGenericEntity, PropertyGroup):
    location: FloatVectorProperty(name="Location", subtype="XYZ")

    def __str__(self):
        return "Point3D({})".format(self.slvs_index)

    def update(self):
        coords, indices = functions.draw_cube_3d(*self.location, 0.05)
        self._batch = batch_for_shader(
            self._shader, "POINTS", {"pos": (self.location[:],)}
        )

    def create_slvs_data(self, solvesys, coords=None, group=Solver.group_active):
        if not coords:
            coords = self.location

        self.params = [solvesys.addParamV(v, group) for v in coords]

        handle = solvesys.addPoint3d(*self.params, group=group)
        self.py_data = handle

    def update_from_slvs(self, solvesys):
        coords = [solvesys.getParam(i).val for i in self.params]
        self.location = coords

    def tweak(self, solvesys, pos):
        self.create_slvs_data(solvesys, coords=pos)

    def closest_picking_point(self, origin, view_vector):
        """Returns the point on this entity which is closest to the picking ray"""
        return self.location

    # TODO: maybe rename -> pivot_point, midpoint
    def placement(self):
        return self.location

    def draw_props(self, layout):
        col = layout.column()
        col.prop(self, "location")


class SlvsLine3D(SlvsGenericEntity, PropertyGroup):
    def __str__(self):
        return "Slvs Line3D from {} to {}".format(self.p1, self.p2)

    def dependencies(self):
        return [self.p1, self.p2]

    def update(self):
        p1, p2 = self.p1, self.p2
        self._batch = batch_for_shader(
            self._shader, "LINES", {"pos": (p1.location, p2.location)}
        )

    def create_slvs_data(self, solvesys, group=Solver.group_active):
        handle = solvesys.addLineSegment(self.p1.py_data, self.p2.py_data, group=group)
        self.py_data = handle

    def closest_picking_point(self, origin, view_vector):
        """Returns the point on this entity which is closest to the picking ray"""
        p1 = self.p1.location
        d1 = self.p2.location - p1  # normalize?
        return functions.nearest_point_line_line(p1, d1, origin, view_vector)

    def placement(self):
        return (self.p1.location + self.p2.location) / 2


slvs_entity_pointer(SlvsLine3D, "p1")
slvs_entity_pointer(SlvsLine3D, "p2")


class SlvsNormal3D(PropertyGroup, SlvsGenericEntity):
    orientation: FloatVectorProperty(subtype="QUATERNION", size=4)

    def draw(self, context):
        pass

    def draw_id(self, context):
        pass

    def create_slvs_data(self, solvesys, group=Solver.group_active):
        quat = self.orientation
        handle = solvesys.addNormal3dV(quat.w, quat.x, quat.y, quat.z, group=group)
        self.py_data = handle


from mathutils import Vector, Matrix


class SlvsWorkplane(PropertyGroup, SlvsGenericEntity):
    size = 5

    def __str__(self):
        return "Slvs Workplane({}) @ {}".format(self.slvs_index, self.p1)

    def dependencies(self):
        return [self.p1, self.nm]

    def is_active(self, context):
        return context.scene.sketcher.active_sketch_i == -1

    def update(self):
        p1, nm = self.p1, self.nm
        mat = self.matrix_basis

        coords = functions.draw_rect_2d(0, 0, self.size, self.size)
        coords = [(mat @ Vector(co))[:] for co in coords]

        indices = ((0, 1), (1, 2), (2, 3), (3, 0))
        self._batch = batch_for_shader(
            self._shader, "LINES", {"pos": coords}, indices=indices
        )

    # NOTE: probably better to avoid overwritting draw func..
    def draw(self, context):
        if not self.is_visible(context):
            return

        shader = self._shader
        shader.bind()

        bgl.glEnable(bgl.GL_BLEND)

        bgl.glPointSize(self.point_size)
        bgl.glLineWidth(self.line_width)

        col = self.color(context)
        shader.uniform_float("color", col)

        self._batch.draw(shader)

        col_surface = col[:-1] + (0.2,)

        shader.uniform_float("color", col_surface)
        mat = self.matrix_basis

        coords = functions.draw_rect_2d(0, 0, self.size, self.size)
        coords = [(mat @ Vector(co))[:] for co in coords]
        indices = ((0, 1, 2), (0, 2, 3))
        batch = batch_for_shader(self._shader, "TRIS", {"pos": coords}, indices=indices)
        batch.draw(shader)

        self.restore_opengl_defaults()

    def create_slvs_data(self, solvesys, group=Solver.group_active):
        handle = solvesys.addWorkplane(self.p1.py_data, self.nm.py_data, group=group)
        self.py_data = handle

    @property
    def matrix_basis(self):
        mat_rot = self.nm.orientation.to_matrix().to_4x4()
        return Matrix.Translation(self.p1.location) @ mat_rot

    @property
    def normal(self):
        v = global_data.Z_AXIS.copy()
        quat = self.nm.orientation
        v.rotate(quat)
        return v


slvs_entity_pointer(SlvsWorkplane, "p1")
slvs_entity_pointer(SlvsWorkplane, "nm")

convert_items = [
    ("NONE", "None", "", 1),
    ("BEZIER", "Bezier", "", 2),
    ("MESH", "Mesh", "", 3),
]

# TODO: draw sketches and allow selecting
class SlvsSketch(PropertyGroup, SlvsGenericEntity):
    convert_type: EnumProperty(
        name="Convert Type",
        items=convert_items,
        description="Define how the sketch should be converted in order to be usable in native blender",
    )
    target_curve: PointerProperty(type=bpy.types.Curve)
    target_curve_object: PointerProperty(type=bpy.types.Object)
    target_mesh: PointerProperty(type=bpy.types.Mesh)
    target_object: PointerProperty(type=bpy.types.Object)

    def __str__(self):
        return "Slvs Sketch({})".format(self.slvs_index)

    def dependencies(self):
        return [
            self.wp,
        ]

    def sketch_entities(self, context):
        for e in context.scene.sketcher.entities.all:
            if not hasattr(e, "sketch"):
                continue
            if e.sketch != self:
                continue
            yield e

    def draw(self, context):
        pass

    def draw_id(self, context):
        pass

    def create_slvs_data(self, solvesys, group=Solver.group_active):
        pass


slvs_entity_pointer(SlvsSketch, "wp")


class Entity2D:
    @property
    def wp(self):
        return self.sketch.wp


class SlvsPoint2D(PropertyGroup, SlvsGenericEntity, Entity2D):
    co: FloatVectorProperty(subtype="XYZ", size=2)

    def __str__(self):
        return "Slvs Point2D({})".format(self.slvs_index)

    def dependencies(self):
        return [
            self.sketch,
        ]

    def update(self):
        u, v = self.co
        mat_local = Matrix.Translation(Vector((u, v, 0)))

        mat = self.wp.matrix_basis @ mat_local
        size = 0.1
        coords = functions.draw_rect_2d(0, 0, size, size)
        coords = [(mat @ Vector(co))[:] for co in coords]
        indices = ((0, 1, 2), (0, 2, 3))
        pos = self.location
        self._batch = batch_for_shader(self._shader, "POINTS", {"pos": (pos[:],)})

    @property
    def location(self):
        u, v = self.co
        mat_local = Matrix.Translation(Vector((u, v, 0)))
        mat = self.wp.matrix_basis @ mat_local
        return mat @ Vector((0, 0, 0))

    def create_slvs_data(self, solvesys, coords=None, group=Solver.group_active):
        if not coords:
            coords = self.co

        self.params = [solvesys.addParamV(v, group) for v in coords]

        handle = solvesys.addPoint2d(self.wp.py_data, *self.params, group=group)
        self.py_data = handle

    def update_from_slvs(self, solvesys):
        coords = [solvesys.getParam(i).val for i in self.params]
        self.co = coords

    def closest_picking_point(self, origin, view_vector):
        """Returns the point on this entity which is closest to the picking ray"""
        return self.location

    def tweak(self, solvesys, coords):
        u, v, _ = self.wp.matrix_basis.inverted() @ coords
        self.create_slvs_data(solvesys, coords=Vector((u, v)))

    def placement(self):
        return self.location


slvs_entity_pointer(SlvsPoint2D, "sketch")


def set_handles(point):
    point.handle_left_type = "FREE"
    point.handle_right_type = "FREE"


class SlvsLine2D(PropertyGroup, SlvsGenericEntity, Entity2D):
    def __str__(self):
        return "Slvs Line2D({}) from {} to {}".format(self.slvs_index, self.p1, self.p2)

    def dependencies(self):
        return [self.p1, self.p2, self.sketch]

    def update(self):
        p1, p2 = self.p1, self.p2
        coords = (p1.location, p2.location)
        self._batch = batch_for_shader(self._shader, "LINES", {"pos": coords})

    def create_slvs_data(self, solvesys, group=Solver.group_active):
        handle = solvesys.addLineSegment(self.p1.py_data, self.p2.py_data, group=group)
        self.py_data = handle

    def closest_picking_point(self, origin, view_vector):
        """Returns the point on this entity which is closest to the picking ray"""
        # NOTE: for 2d entities it could be enough precise to simply take the intersection point with the workplane
        p1 = self.p1.location
        d1 = self.p2.location - p1  # normalize?
        return functions.nearest_point_line_line(p1, d1, origin, view_vector)

    def placement(self):
        return (self.p1.location + self.p2.location) / 2

    def connection_points(self):
        return [self.p1, self.p2]

    def direction(self, point, is_endpoint=False):
        """Returns the direction of the line, true if inverted"""
        if is_endpoint:
            return point == self.p1
        else:
            return point == self.p2

    def to_bezier(
        self, spline, startpoint, endpoint, invert_direction, set_startpoint=False
    ):
        locations = [self.p1.co.to_3d(), self.p2.co.to_3d()]
        if invert_direction:
            locations.reverse()

        if set_startpoint:
            startpoint.co = locations[0]
        endpoint.co = locations[1]

        startpoint.handle_right = locations[0]
        endpoint.handle_left = locations[1]

        return endpoint


slvs_entity_pointer(SlvsLine2D, "p1")
slvs_entity_pointer(SlvsLine2D, "p2")
slvs_entity_pointer(SlvsLine2D, "sketch")


class SlvsNormal2D(PropertyGroup, SlvsGenericEntity, Entity2D):
    def draw(self, context):
        pass

    def draw_id(self, context):
        pass

    def create_slvs_data(self, solvesys, group=Solver.group_active):
        handle = solvesys.addNormal2d(self.wp.py_data, group=group)
        self.py_data = handle


slvs_entity_pointer(SlvsNormal2D, "sketch")


def get_bezier_curve_midpoint_positions(
    curve_element, segment_count, midpoints, angle, cyclic=False
):
    positions = []
    if segment_count == 1:
        return []

    if cyclic:
        point_count = segment_count
    else:
        point_count = segment_count - 1

    a = angle / segment_count
    for i in range(point_count):
        pos = curve_element.point_on_curve(a * (i + 1))
        positions.append(pos)
    return positions


def create_bezier_curve(
    segment_count,
    bezier_points,
    locations,
    center,
    base_offset,
    invert=False,
    cyclic=False,
):
    if cyclic:
        bezier_points.append(bezier_points[0])
        locations.append(locations[0])

    for index in range(segment_count):
        loc1, loc2 = locations[index], locations[index + 1]
        b1, b2 = bezier_points[index], bezier_points[index + 1]

        coords = []
        for i, loc in enumerate((loc1, loc2)):
            pos = loc - center
            angle = math.atan2(pos[1], pos[0])
            offset = base_offset.copy()

            if i == 0 and invert or i == 1 and not invert:
                offset[1] *= -1

            offset.rotate(Matrix.Rotation(angle, 2))
            coords.append((center + offset).to_3d())

        b1.handle_right = coords[0]
        b2.handle_left = coords[1]
        b2.co = loc2.to_3d()


class SlvsArc(PropertyGroup, SlvsGenericEntity, Entity2D):
    def __str__(self):
        return "Slvs Arc({}) at {}, from {}, to {}".format(
            self.slvs_index, self.ct, self.start, self.end
        )

    def dependencies(self):
        return [self.nm, self.ct, self.start, self.end, self.sketch]

    def update(self):
        ct = self.ct.co
        p1 = self.start.co - ct
        p2 = self.end.co - ct

        radius = math.hypot(p1.x, p1.y)
        offset = functions.range_2pi(math.atan2(p1.y, p1.x))

        offset_2 = functions.range_2pi(math.atan2(p2.y, p2.x))
        angle = functions.range_2pi(offset_2 - offset)

        # TODO: resolution should depend on segment length?!
        segments = round(8 * (angle / math.pi * 2)) + 1

        coords = functions.coords_arc_2d(
            0, 0, radius, segments, angle=angle, offset=offset
        )

        u, v = self.ct.co

        mat_local = Matrix.Translation(Vector((u, v, 0)))
        mat = self.wp.matrix_basis @ mat_local
        coords = [(mat @ Vector((*co, 0)))[:] for co in coords]

        self._batch = batch_for_shader(self._shader, "LINE_STRIP", {"pos": coords})

    def create_slvs_data(self, solvesys, group=Solver.group_active):
        handle = solvesys.addArcOfCircle(
            self.wp.py_data,
            self.ct.py_data,
            self.start.py_data,
            self.end.py_data,
            group=group,
        )
        self.py_data = handle

    @property
    def radius(self):
        return (self.ct.co - self.start.co).length

    @property
    def angle(self):
        ct = self.ct.co
        start, end = self.start.co - ct, self.end.co - ct
        return functions.range_2pi(
            math.atan2(end[1], end[0]) - math.atan2(start[1], start[0])
        )

    @property
    def start_angle(self):
        center, start = self.ct.co, self.start.co
        return math.atan2((start - center)[1], (start - center)[0])

    def connection_points(self):
        return [self.start, self.end]

    def direction(self, point, is_endpoint=False):
        """Returns the direction of the line, true if inverted"""
        if is_endpoint:
            return point == self.start
        else:
            return point == self.end

    def bezier_segment_count(self):
        max_angle = math.pi / 2
        return math.ceil(self.angle / max_angle)

    def bezier_point_count(self):
        return self.bezier_segment_count() + 1

    def point_on_curve(self, angle):
        return (
            Vector(functions.pol2cart(self.radius, self.start_angle + angle))
            + self.ct.co
        )

    def to_bezier(
        self,
        spline,
        startpoint,
        endpoint,
        invert_direction,
        set_startpoint=False,
        midpoints=[],
    ):
        # Get midpoint positions
        segment_count = len(midpoints) + 1
        curve_angle = self.angle
        radius, center, start = self.radius, self.ct.co, self.start.co

        midpoint_positions = get_bezier_curve_midpoint_positions(
            self, segment_count, midpoints, curve_angle
        )

        angle = curve_angle / segment_count

        locations = [self.start.co, *midpoint_positions, self.end.co]
        bezier_points = [startpoint, *midpoints, endpoint]

        if invert_direction:
            locations.reverse()

        if set_startpoint:
            startpoint.co = locations[0].to_3d()

        n = 2 * math.pi / angle
        q = (4 / 3) * math.tan(math.pi / (2 * n))
        base_offset = Vector((radius, q * radius))

        create_bezier_curve(
            segment_count,
            bezier_points,
            locations,
            center,
            base_offset,
            invert=invert_direction,
        )

        return endpoint


slvs_entity_pointer(SlvsArc, "nm")
slvs_entity_pointer(SlvsArc, "ct")
slvs_entity_pointer(SlvsArc, "start")
slvs_entity_pointer(SlvsArc, "end")
slvs_entity_pointer(SlvsArc, "sketch")


class SlvsCircle(PropertyGroup, SlvsGenericEntity, Entity2D):
    radius: FloatProperty()

    def __str__(self):
        return "Slvs Circle({}) at {}, radius {}".format(
            self.slvs_index, self.ct, self.radius
        )

    def dependencies(self):
        return [self.nm, self.ct, self.sketch]

    def update(self):
        coords = functions.coords_arc_2d(0, 0, self.radius, 32)

        u, v = self.ct.co

        mat_local = Matrix.Translation(Vector((u, v, 0)))
        mat = self.wp.matrix_basis @ mat_local
        coords = [(mat @ Vector((*co, 0)))[:] for co in coords]

        self._batch = batch_for_shader(self._shader, "LINE_STRIP", {"pos": coords})

    def create_slvs_data(self, solvesys, group=Solver.group_active):
        self.param = solvesys.addParamV(self.radius, group)

        nm = None
        if self.nm != -1:
            nm = self.nm
        else:
            nm = self.wp.nm

        handle = solvesys.addCircle(
            self.ct.py_data,
            self.nm.py_data,
            solvesys.addDistance(self.param),
            group=group,
        )
        self.py_data = handle

    def update_from_slvs(self, solvesys):
        self.radius = solvesys.getParam(self.param).val

    def point_on_curve(self, angle):
        return Vector(functions.pol2cart(self.radius, angle)) + self.ct.co

    def connection_points(self):
        # NOTE: it should probably be possible to lookup coincident points on circle
        return ()

    def direction(self, point, is_endpoint=False):
        return False

    def bezier_segment_count(self):
        return 4

    def bezier_point_count(self):
        return self.bezier_segment_count()

    def to_bezier(
        self,
        spline,
        startpoint,
        endpoint,
        invert_direction,
        set_startpoint=False,
        midpoints=[],
    ):
        # Get midpoint positions
        segment_count = len(midpoints) + 1
        radius, center = self.radius, self.ct.co

        bezier_points = [startpoint, *midpoints]

        locations = get_bezier_curve_midpoint_positions(
            self, segment_count, bezier_points, 2 * math.pi, cyclic=True
        )
        angle = 2 * math.pi / segment_count

        n = 2 * math.pi / angle
        q = (4 / 3) * math.tan(math.pi / (2 * n))
        base_offset = Vector((radius, q * radius))

        create_bezier_curve(
            segment_count,
            bezier_points,
            locations,
            center,
            base_offset,
            invert=invert_direction,
            cyclic=True,
        )
        return endpoint


slvs_entity_pointer(SlvsCircle, "nm")
slvs_entity_pointer(SlvsCircle, "ct")
slvs_entity_pointer(SlvsCircle, "sketch")


def update_pointers(index_old, index_new):
    context = bpy.context

    # NOTE: this should go through all entity pointers and update them if neccesary.
    # It might be possible to use the msgbus to notify and update the IntProperty pointers

    # TODO: also respect context.scene.sketcher.active_sketch

    for o in context.scene.sketcher.all:
        if not hasattr(o, "update_pointers"):
            continue
        o.update_pointers(index_old, index_new)


# NOTE: currently limited to 16 items!
entities = (
    SlvsPoint3D,
    SlvsLine3D,
    SlvsNormal3D,
    SlvsWorkplane,
    SlvsSketch,
    SlvsPoint2D,
    SlvsLine2D,
    SlvsNormal2D,
    SlvsArc,
    SlvsCircle,
)

entity_collections = (
    "points3D",
    "lines3D",
    "normals3D",
    "workplanes",
    "sketches",
    "points2D",
    "lines2D",
    "normals2D",
    "arcs",
    "circles",
)


class SlvsEntities(PropertyGroup):
    """Holds all Solvespace Entities"""

    def _type_index(self, entity):
        return entities.index(type(entity))

    def _set_index(self, entity):
        type_index = self._type_index(entity)
        sub_list = getattr(self, entity_collections[type_index])

        local_index = len(sub_list) - 1
        # TODO: handle this case better
        assert local_index < math.pow(2, 20)
        entity.slvs_index = type_index << 20 | local_index

    def _breakdown_index(self, index):
        type_index = index >> 20
        local_index = index & 0xFFFFF
        return type_index, local_index

    def _get_list_and_index(self, index):
        type_index, local_index = self._breakdown_index(index)
        return getattr(self, entity_collections[type_index]), local_index

    def get(self, index):
        sub_list, i = self._get_list_and_index(index)
        return sub_list[i]

    def remove(self, index):
        assert isinstance(index, int)
        entity_list, i = self._get_list_and_index(index)
        entity_list.remove(i)

        # Put last item to removed index and update all pointers to it
        last_index = len(entity_list) - 1

        if last_index < 0:
            return
        if i > last_index:
            return

        if not i == last_index:  # second last item was deleted
            entity_list.move(last_index, i)

        new_item = entity_list[i]
        update_pointers(new_item.slvs_index, index)
        new_item.slvs_index = index

    def add_point_3d(self, co):
        p = self.points3D.add()
        p.location = co
        self._set_index(p)
        return p

    def add_line_3d(self, p1, p2):
        l = self.lines3D.add()
        l.p1 = p1
        l.p2 = p2
        self._set_index(l)
        return l

    def add_normal_3d(self, quat):
        nm = self.normals3D.add()
        nm.orientation = quat
        self._set_index(nm)
        return nm

    def add_workplane(self, p1, nm):
        wp = self.workplanes.add()
        wp.p1 = p1
        wp.nm = nm
        self._set_index(wp)
        return wp

    def add_sketch(self, wp):
        sketch = self.sketches.add()
        sketch.wp = wp
        self._set_index(sketch)
        _, i = self._breakdown_index(sketch.slvs_index)
        sketch.name = "Sketch." + str(i)
        return sketch

    def add_point_2d(self, co, sketch):
        p = self.points2D.add()
        p.co = co
        p.sketch = sketch
        self._set_index(p)
        return p

    def add_line_2d(self, p1, p2, sketch):
        l = self.lines2D.add()
        l.p1 = p1
        l.p2 = p2
        l.sketch = sketch
        self._set_index(l)
        return l

    def add_normal_2d(self, sketch):
        nm = self.normals2D.add()
        nm.sketch = sketch
        self._set_index(nm)
        return nm

    def add_arc(self, nm, ct, start, end, sketch):
        arc = self.arcs.add()
        arc.nm = nm
        arc.ct = ct
        arc.start = start
        arc.end = end
        arc.sketch = sketch
        self._set_index(arc)
        return arc

    def add_circle(self, nm, ct, radius, sketch):  # TODO: is only 2d.. change name
        c = self.circles.add()
        c.nm = nm
        c.ct = ct
        c.radius = radius
        c.sketch = sketch
        self._set_index(c)
        return c

    @property
    def all(self):
        for coll_name in entity_collections:
            entity_coll = getattr(self, coll_name)
            for entity in entity_coll:
                yield entity

    @property
    def selected_entities(self):
        items = []
        for item in self.all:
            if item.selected:
                items.append(item)
        return items

    def ensure_origin_elements(self, context):
        from mathutils import Euler

        def set_origin_props(e):
            e.fixed = True
            e.origin = True

        sse = context.scene.sketcher.entities
        # origin
        if not self.origin:
            p = sse.add_point_3d((0.0, 0.0, 0.0))
            set_origin_props(p)
            self.origin = p

        # axis
        for name, angles in zip(
            ("origin_axis_X", "origin_axis_Y", "origin_axis_Z"),
            (Euler((0.0, math.pi / 2, 0.0)), Euler((math.pi / 2, 0.0, 0.0)), Euler()),
        ):
            if getattr(self, name):
                continue
            nm = sse.add_normal_3d(Euler(angles).to_quaternion())
            set_origin_props(nm)
            setattr(self, name, nm)

        # workplanes
        for nm_name, wp_name in (
            ("origin_axis_X", "origin_plane_YZ"),
            ("origin_axis_Y", "origin_plane_XZ"),
            ("origin_axis_Z", "origin_plane_XY"),
        ):
            if getattr(self, wp_name):
                continue
            wp = sse.add_workplane(self.origin, getattr(self, nm_name))
            set_origin_props(wp)
            setattr(self, wp_name, wp)


if not hasattr(SlvsEntities, "__annotations__"):
    SlvsEntities.__annotations__ = {}
for entity_cls, list_name in zip(entities, entity_collections):
    SlvsEntities.__annotations__[list_name] = CollectionProperty(type=entity_cls)


slvs_entity_pointer(SlvsEntities, "origin")
slvs_entity_pointer(SlvsEntities, "origin_axis_X")
slvs_entity_pointer(SlvsEntities, "origin_axis_Y")
slvs_entity_pointer(SlvsEntities, "origin_axis_Z")
slvs_entity_pointer(SlvsEntities, "origin_plane_XY")
slvs_entity_pointer(SlvsEntities, "origin_plane_XZ")
slvs_entity_pointer(SlvsEntities, "origin_plane_YZ")


### Constraints
from .global_data import WpReq

point = (SlvsPoint3D, SlvsPoint2D)
line = (SlvsLine3D, SlvsLine2D)
curve = (SlvsCircle, SlvsArc)


class GenericConstraint:
    signature = ()

    def needs_wp(args):
        return WpReq.OPTIONAL

    def __str__(self):
        return "Slvs Constraint"

    def get_workplane(self):
        # NOTE: this could also check through the constraints entity workplanes
        needs_wp = self.needs_wp()

        workplane = None
        if self.sketch_i != -1:
            workplane = self.sketch.wp

        if workplane and needs_wp != WpReq.FREE:
            return workplane.py_data
        if needs_wp == WpReq.NOT_FREE:
            return None
        from py_slvs import slvs

        return slvs.SLVS_FREE_IN_3D

    def entities(self):
        props = []
        for prop_name in dir(self):
            if prop_name.endswith("_i") or not prop_name.startswith("entity"):
                continue
            props.append(getattr(self, prop_name))
        return props

    # TODO: avoid duplicating code
    def update_pointers(self, index_old, index_new):
        for prop_name in dir(self):
            if not prop_name.startswith("entity") or not prop_name.endswith("_i"):
                continue
            prop = getattr(self, prop_name)
            if prop == index_old:
                setattr(self, prop_name, index_new)

    def is_active(self, context):
        if not hasattr(self, "sketch"):
            pass
        active_sketch_i = context.scene.sketcher.active_sketch_i
        if self.sketch:
            return self.sketch.slvs_index == active_sketch_i
        else:
            return active_sketch_i == -1

    def draw_plane(self):
        if self.sketch_i != -1:
            wp = self.sketch.wp
            return wp.p1.location, wp.normal
        # TODO: return drawing plane for constraints in 3d
        return None, None


# NOTE: When tweaking it's neccesary to constrain a point that is only temporary available
# and has no SlvsPoint representation
def make_coincident(solvesys, point_handle, e2, wp, group):
    func = None
    set_wp = False

    if type(e2) in line:
        func = solvesys.addPointOnLine
        set_wp = True
    elif type(e2) in curve:
        func = solvesys.addPointOnCircle
    elif isinstance(e2, SlvsWorkplane):
        func = solvesys.addPointInPlane
    elif type(e2) in point:
        func = solvesys.addPointsCoincident
        set_wp = True

    kwargs = {
        "group": group,
    }

    if set_wp:
        kwargs["wrkpln"] = wp

    func(point_handle, e2.py_data, **kwargs)


class SlvsCoincident(PropertyGroup, GenericConstraint):
    type = "COINCIDENT"
    label = "Coincident"
    signature = (point, (*point, *line, SlvsWorkplane, SlvsCircle, SlvsArc))
    # NOTE: Coincident between 3dPoint and Workplane currently doesn't seem to work

    def __str__(self):
        return "{} between {} and {}".format(
            self.type.lower(), self.entity1, self.entity2
        )

    def needs_wp(self):
        if isinstance(self.entity2, SlvsWorkplane):
            return WpReq.FREE
        return WpReq.OPTIONAL

    def create_slvs_data(self, solvesys, group=Solver.group_active):
        make_coincident(
            solvesys, self.entity1.py_data, self.entity2, self.get_workplane(), group
        )

    def placement(self, context):
        """location to display the constraint"""
        region = context.region
        rv3d = context.space_data.region_3d
        coords = self.entity1.location
        return location_3d_to_region_2d(region, rv3d, coords)


slvs_entity_pointer(SlvsCoincident, "entity1")
slvs_entity_pointer(SlvsCoincident, "entity2")
slvs_entity_pointer(SlvsCoincident, "sketch")


line_arc_circle = (*line, SlvsArc, SlvsCircle)


class SlvsEqual(PropertyGroup, GenericConstraint):
    type = "EQUAL"
    label = "Equal"
    signature = (line_arc_circle, line_arc_circle)

    def __str__(self):
        return "{} between {} and {}".format(
            self.type.lower(), self.entity1, self.entity2
        )

    def create_slvs_data(self, solvesys, group=Solver.group_active):
        # TODO: Don't allow to add Equal between Line and Circle
        e1, e2 = self.entity1, self.entity2

        func = None
        set_wp = False

        if all([type(e) in line for e in (e1, e2)]):
            func = solvesys.addEqualLength
            set_wp = True
        elif all([type(e) in curve for e in (e1, e2)]):
            func = solvesys.addEqualRadius
        else:
            # TODO: Do a proper check to see if there's really one Arc and one Line
            func = solvesys.addEqualLineArcLength
            set_wp = True

        kwargs = {
            "group": group,
        }

        if set_wp:
            kwargs["wrkpln"] = self.get_workplane()

        if func:
            func(e1.py_data, e2.py_data, **kwargs)

    def placement(self, context):
        """location to display the constraint"""
        region = context.region
        rv3d = context.space_data.region_3d
        line = self.entity1
        p1, p2 = line.p1.location, line.p2.location
        coords = (p1 + p2) / 2
        return location_3d_to_region_2d(region, rv3d, coords)


slvs_entity_pointer(SlvsEqual, "entity1")
slvs_entity_pointer(SlvsEqual, "entity2")
slvs_entity_pointer(SlvsEqual, "sketch")


def update_system_cb(self, context):
    solve_system(context)


from mathutils import Euler
from mathutils.geometry import distance_point_to_plane


def get_side_of_line(line_start, line_end, point):
    line_end = line_end - line_start
    point = point - line_start
    return -(
        (line_end.x - line_start.x) * (point.y - line_start.y)
        - (line_end.y - line_start.y) * (point.x - line_start.x)
    )


class SlvsDistance(PropertyGroup, GenericConstraint):
    label = "Distance"
    value: FloatProperty(name=label, update=update_system_cb)
    draw_offset: FloatProperty(default=0.3)
    type = "DISTANCE"
    signature = (point, (*point, *line, SlvsWorkplane))

    def __str__(self):
        return "{} {} between {} and {} on {}".format(
            self.type.lower(), self.value, self.entity1, self.entity2, self.sketch
        )

    def needs_wp(self):
        if isinstance(self.entity2, SlvsWorkplane):
            return WpReq.FREE
        return WpReq.OPTIONAL

    def create_slvs_data(self, solvesys, group=Solver.group_active):
        if self.entity1 == self.entity2:
            raise AttributeError("Cannot create constraint between one entity itself")

        e1, e2 = self.entity1, self.entity2

        func = None
        set_wp = False

        if type(e2) in line:
            func = solvesys.addPointLineDistance
            set_wp = True
        elif type(e2) in point:
            func = solvesys.addPointsDistance
            set_wp = True
        elif isinstance(e2, SlvsWorkplane):
            func = solvesys.addPointPlaneDistance

        # TODO: ProjectedDistance ?!

        kwargs = {
            "group": group,
        }

        if set_wp:
            kwargs["wrkpln"] = self.get_workplane()

        if func:
            func(self.value, e1.py_data, e2.py_data, **kwargs)

    def matrix_basis(self):
        if self.sketch_i == -1 or not isinstance(self.entity1, SlvsPoint2D):
            # TODO: Support distance in 3d
            return Matrix()

        sketch = self.sketch
        x_axis = Vector((1, 0, 0))

        if isinstance(self.entity2, SlvsPoint2D):
            p1, p2 = self.entity1.co, self.entity2.co
            v_rotation = p2 - p1
            v_translation = (p2 + p1) / 2
            mat_rot = x_axis.rotation_difference(v_rotation.to_3d()).to_matrix()

        elif isinstance(self.entity2, SlvsLine2D):
            line = self.entity2
            orig = line.p1.co
            end = line.p2.co - orig
            angle = functions.range_2pi(math.atan2(end[1], end[0])) + math.pi / 2

            mat_rot = Matrix.Rotation(angle, 2, "Z")
            p1 = self.entity1.co - orig
            v_translation = (p1 + p1.project(end)) / 2 + orig

        mat_local = Matrix.Translation(v_translation.to_3d()) @ mat_rot.to_4x4()
        return sketch.wp.matrix_basis @ mat_local

    def init_props(self, args):
        # Set initial distance value to the current spacing
        e1, e2 = args
        if isinstance(e2, SlvsWorkplane):
            # Returns the signed distance to the plane
            value = distance_point_to_plane(e1.location, e2.p1.location, e2.normal)
        elif type(e2) in line:
            orig = e2.p1.location
            end = e2.p2.location - orig
            p1 = e1.location - orig
            value = (p1 - (p1).project(end)).length

            # NOTE: Comment from solvespace documentation:
            # When constraining the distance between a point and a plane,
            # or a point and a plane face, or a point and a line in a workplane,
            # the distance is signed. The distance may be positive or negative,
            # depending on whether the point is above or below the plane.
            # The distance is always shown positive on the sketch;
            # to flip to the other side, enter a negative value.
            value = math.copysign(
                value,
                get_side_of_line(e2.p1.location, e2.p2.location, e1.location),
            )
        else:
            value = (e1.location - e2.location).length
        self.value = value
        return value, None

    def update_draw_offset(self, pos, ui_scale):
        self.draw_offset = pos[1] / ui_scale


slvs_entity_pointer(SlvsDistance, "entity1")
slvs_entity_pointer(SlvsDistance, "entity2")
slvs_entity_pointer(SlvsDistance, "sketch")


class SlvsDiameter(PropertyGroup, GenericConstraint):
    label = "Diameter"
    value: FloatProperty(name=label, update=update_system_cb)
    draw_offset: FloatProperty(default=45, subtype="ANGLE")
    type = "DIAMETER"
    signature = (curve,)

    def __str__(self):
        return "{} of {} on {}".format(self.type.lower(), self.entity1, self.sketch)

    def needs_wp(self):
        return WpReq.OPTIONAL

    def create_slvs_data(self, solvesys, group=Solver.group_active):
        solvesys.addDiameter(self.value, self.entity1.py_data, group=group)

    def init_props(self, args):
        return args[0].radius * 2, None

    def matrix_basis(self):
        if self.sketch_i == -1:
            return Matrix()

        sketch = self.sketch

        origin = self.entity1.ct.co
        rotation = functions.range_2pi(math.radians(self.draw_offset))
        mat_local = Matrix.Translation(origin.to_3d())
        return sketch.wp.matrix_basis @ mat_local

    def update_draw_offset(self, pos, ui_scale):
        self.draw_offset = math.degrees(math.atan2(pos[1], pos[0]))  # / ui_scale


slvs_entity_pointer(SlvsDiameter, "entity1")
slvs_entity_pointer(SlvsDiameter, "sketch")


from mathutils.geometry import intersect_line_line_2d


class SlvsAngle(PropertyGroup, GenericConstraint):
    label = "Angle"
    value: FloatProperty(name=label, update=update_system_cb)
    setting: BoolProperty(name="Invert", update=update_system_cb)
    draw_offset: FloatProperty(default=1)
    type = "ANGLE"
    signature = ((SlvsLine2D,), (SlvsLine2D,))

    def __str__(self):
        return "{} between {} and {} on {}".format(
            self.type.lower(), self.entity1, self.entity2, self.sketch
        )

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_active):
        solvesys.addAngle(
            self.value,
            self.setting,
            self.entity1.py_data,
            self.entity2.py_data,
            wrkpln=self.get_workplane(),
            group=group,
        )

    def matrix_basis(self):
        if self.sketch_i == -1:
            return Matrix()

        sketch = self.sketch

        line1 = self.entity1
        line2 = self.entity2

        origin = intersect_line_line_2d(
            line1.p1.co, line1.p2.co, line2.p1.co, line2.p2.co
        )
        rotation = functions.range_2pi(
            (self.orientation(line2) + self.orientation(line1)) / 2
        )

        if self.setting:
            rotation = rotation - math.pi / 2

        mat_rot = Matrix.Rotation(rotation, 2, "Z")
        mat_local = Matrix.Translation(origin.to_3d()) @ mat_rot.to_4x4()
        return sketch.wp.matrix_basis @ mat_local

    @staticmethod
    def orientation(line):
        pos = line.p2.co - line.p1.co
        return math.atan2(pos[1], pos[0])

    def init_props(self, args):
        # Set initial angle value to the current angle
        line1, line2 = args
        angle = self.orientation(line2) - self.orientation(line1)
        angle = abs(math.degrees(angle))
        self.value = angle
        return angle, None

    def update_draw_offset(self, pos, ui_scale):
        self.draw_offset = math.hypot(pos[0], pos[1]) / ui_scale


slvs_entity_pointer(SlvsAngle, "entity1")
slvs_entity_pointer(SlvsAngle, "entity2")
slvs_entity_pointer(SlvsAngle, "sketch")


class SlvsParallel(PropertyGroup, GenericConstraint):
    type = "PARALLEL"
    label = "Parallel"
    signature = ((SlvsLine2D,), (SlvsLine2D,))

    def __str__(self):
        return "{} between {} and {} on {}".format(
            self.type.lower(), self.entity1, self.entity2, self.sketch
        )

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_active):
        solvesys.addParallel(
            self.entity1.py_data,
            self.entity2.py_data,
            wrkpln=self.get_workplane(),
            group=group,
        )


slvs_entity_pointer(SlvsParallel, "entity1")
slvs_entity_pointer(SlvsParallel, "entity2")
slvs_entity_pointer(SlvsParallel, "sketch")


# NOTE: this could also support constraining two points
class SlvsHorizontal(PropertyGroup, GenericConstraint):
    type = "HORIZONTAL"
    label = "Horizontal"
    signature = ((SlvsLine2D,),)

    def __str__(self):
        return "{} for {} on {}".format(self.type.lower(), self.entity1, self.sketch)

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_active):
        solvesys.addLineHorizontal(
            self.entity1.py_data, wrkpln=self.get_workplane(), group=group
        )


slvs_entity_pointer(SlvsHorizontal, "entity1")
slvs_entity_pointer(SlvsHorizontal, "sketch")


class SlvsVertical(PropertyGroup, GenericConstraint):
    type = "VERTICAL"
    label = "Vertical"
    signature = ((SlvsLine2D,),)

    def __str__(self):
        return "{} for {} on {}".format(self.type.lower(), self.entity1, self.sketch)

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_active):
        solvesys.addLineVertical(
            self.entity1.py_data, wrkpln=self.get_workplane(), group=group
        )


slvs_entity_pointer(SlvsVertical, "entity1")
slvs_entity_pointer(SlvsVertical, "sketch")


class SlvsPerpendicular(PropertyGroup, GenericConstraint):
    setting: BoolProperty(name="Invert", update=update_system_cb)
    type = "PERPENDICULAR"
    label = "Perpendicular"
    signature = ((SlvsLine2D,), (SlvsLine2D,))

    def __str__(self):
        return "{} between {} and {} on {}".format(
            self.type.lower(), self.entity1, self.entity2, self.sketch
        )

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_active):
        solvesys.addPerpendicular(
            self.entity1.py_data,
            self.entity2.py_data,
            wrkpln=self.get_workplane(),
            group=group,
        )


slvs_entity_pointer(SlvsPerpendicular, "entity1")
slvs_entity_pointer(SlvsPerpendicular, "entity2")
slvs_entity_pointer(SlvsPerpendicular, "sketch")


def connection_point(seg_1, seg_2):
    points = seg_1.connection_points()
    for p in seg_2.connection_points():
        if p in points:
            return p
    return None


class SlvsTangent(PropertyGroup, GenericConstraint):
    type = "TANGENT"
    label = "Tangent"
    signature = (curve, (SlvsLine2D, *curve))

    def __str__(self):
        return "{} between {} and {} on {}".format(
            self.type.lower(), self.entity1, self.entity2, self.sketch
        )

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_active):
        e1, e2 = self.entity1, self.entity2

        # NOTE: get connection point between entities and set settings implicitly
        point = connection_point(e1, e2)
        if point and not isinstance(e2, SlvsCircle):
            if isinstance(e2, SlvsLine2D):
                solvesys.addArcLineTangent(
                    e1.direction(point),
                    e1.py_data,
                    e2.py_data,
                    group=group,
                )
            elif isinstance(e2, SlvsArc):
                solvesys.addCurvesTangent(
                    e1.direction(point),
                    e2.direction(point),
                    e1.py_data,
                    e2.py_data,
                    wrkpln=self.get_workplane(),
                    group=group,
                )
        else:
            # NOTE: try to allow generic tangent (e.g. when entities aren't connected)
            # by setting the proper distance between them
            if isinstance(e2, SlvsLine2D):
                value = math.copysign(
                    e1.radius,
                    get_side_of_line(e2.p1.location, e2.p2.location, e1.ct.location),
                )

                solvesys.addPointLineDistance(
                    value,
                    e1.ct.py_data,
                    e2.py_data,
                    wrkpln=self.get_workplane(),
                    group=group,
                )
            else:
                value = e1.radius + e2.radius
                solvesys.addPointsDistance(
                    value,
                    e1.ct.py_data,
                    e2.ct.py_data,
                    wrkpln=self.get_workplane(),
                    group=group,
                )


slvs_entity_pointer(SlvsTangent, "entity1")
slvs_entity_pointer(SlvsTangent, "entity2")
slvs_entity_pointer(SlvsTangent, "sketch")


class SlvsMidpoint(PropertyGroup, GenericConstraint):
    type = "MIDPOINT"
    label = "Midpoint"
    signature = (point, line)

    def __str__(self):
        return "{} between {} and {} on {}".format(
            self.type.lower(), self.entity1, self.entity2, self.sketch
        )

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_active):
        solvesys.addMidPoint(
            self.entity1.py_data,
            self.entity2.py_data,
            wrkpln=self.get_workplane(),
            group=group,
        )


slvs_entity_pointer(SlvsMidpoint, "entity1")
slvs_entity_pointer(SlvsMidpoint, "entity2")
slvs_entity_pointer(SlvsMidpoint, "sketch")


class SlvsSymmetric(PropertyGroup, GenericConstraint):
    type = "SYMMETRIC"
    label = "Symmetric"

    # TODO: not all combinations are possible!
    signature = (
        point,
        point,
        (SlvsLine2D, SlvsWorkplane),
    )

    def __str__(self):
        return "{} between {} and {} over {} on {}".format(
            self.type.lower(), self.entity1, self.entity2, self.entity3, self.sketch
        )

    def needs_wp(self):
        if isinstance(self.entity3, SlvsLine2D):
            return WpReq.NOT_FREE
        return WpReq.FREE

    def create_slvs_data(self, solvesys, group=Solver.group_active):
        e1, e2, e3 = self.entity1, self.entity2, self.entity3

        # NOTE: this doesn't seem to work correctly, acts like addSymmetricVertical
        if isinstance(e3, SlvsLine2D):
            solvesys.addSymmetricLine(
                e1.py_data,
                e2.py_data,
                e3.py_data,
                self.get_workplane(),
                group=group,
            )

        elif isinstance(e3, SlvsWorkplane):
            solvesys.addSymmetric(
                e1.py_data,
                e2.py_data,
                e3.py_data,
                wrkpln=self.get_workplane(),
                group=group,
            )


slvs_entity_pointer(SlvsSymmetric, "entity1")
slvs_entity_pointer(SlvsSymmetric, "entity2")
slvs_entity_pointer(SlvsSymmetric, "entity3")
slvs_entity_pointer(SlvsSymmetric, "sketch")

# TODO: Support advanced constraint types
# - symmetric_h
# - symmetric_v
# - ratio
# - same orientation
# - distance projected


# class SlvsDistanceProj(PropertyGroup, GenericConstraint):
#     value: FloatProperty()
#     type = 'DISTANCE_PROJ'
#     name = 'Projected Distance'
#     signature = ((SlvsPoint3D, ), (SlvsPoint3D, ))
#
#     def __str__(self):
#         return "{} of {} on {}".format(self.type.lower(), self.entity1, self.entity2, self.sketch)
#
#     def needs_wp(self):
#         return WpReq.OPTIONAL
#
#     def create_slvs_data(self, solvesys):
#         solvesys.distance_proj(self.entity1.py_data, self.entity2.py_data, self.value)
#
# slvs_entity_pointer(SlvsDistanceProj, "entity1")
# slvs_entity_pointer(SlvsDistanceProj, "entity1")
# slvs_entity_pointer(SlvsDistanceProj, "sketch")


constraints = (
    SlvsCoincident,
    SlvsEqual,
    SlvsDistance,
    SlvsAngle,
    SlvsDiameter,
    SlvsParallel,
    SlvsHorizontal,
    SlvsVertical,
    SlvsTangent,
    SlvsMidpoint,
    SlvsPerpendicular,
    # SlvsSymmetric,
)

constraint_types = []
for i, c in enumerate(constraints):
    constraint_types.append((c.type, c.label, "", i))


class SlvsConstraints(PropertyGroup):
    @staticmethod
    def cls_from_type(type):
        for cls in constraints:
            if type == cls.type:
                return cls
        return None

    def new_from_type(self, type):
        name = type.lower()
        constraint_list = getattr(self, name)
        return constraint_list.add()

    def get_lists(self):
        lists = []
        for entity_list in self.rna_type.properties:
            name = entity_list.identifier
            if name in ("name", "rna_type"):
                continue
            lists.append(getattr(self, name))
        return lists

    def get_list(self, type):
        return getattr(self, type.lower())

    def get_from_type_index(self, type, index):
        list = getattr(self, type.lower())
        return list[index]

    def get_index(self, constr):
        list = getattr(self, constr.type.lower())
        for i, item in enumerate(list):
            if item == constr:
                return i
        return -1

    def remove(self, constr):
        # NOTE: This could just get the index instead of the constraint
        i = self.get_index(constr)
        self.get_list(constr.type).remove(i)

    @property
    def all(self):
        for entity_list in self.get_lists():
            for entity in entity_list:
                yield entity


for cls in constraints:
    parent_cls = SlvsConstraints
    name = cls.type.lower()
    if not hasattr(parent_cls, "__annotations__"):
        parent_cls.__annotations__ = {}
    parent_cls.__annotations__[name] = CollectionProperty(type=cls)

    # TODO: # get signature from class and add proper arguments to "add" function
    def func(*args):
        item = getattr(SlvsConstraints, name).add()
        cls.new(*args)

    setattr(parent_cls, "add_" + name, func)


class SketcherProps(PropertyGroup):
    hover: IntProperty(default=-1)
    entities: PointerProperty(type=SlvsEntities)
    constraints: PointerProperty(type=SlvsConstraints)
    show_origin: BoolProperty()

    @property
    def all(self):
        """Iterate over entities and constraints of every type"""
        for e in self.entities.all:
            yield e
        for c in self.constraints.all:
            yield c


def update_cb(self, context):
    # update gizmos!
    context.space_data.show_gizmo = True


slvs_entity_pointer(SketcherProps, "active_sketch", update=update_cb)


classes = (
    *entities,
    SlvsEntities,
    *constraints,
    SlvsConstraints,
    SketcherProps,
)


def register():

    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.sketcher = PointerProperty(type=SketcherProps)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
