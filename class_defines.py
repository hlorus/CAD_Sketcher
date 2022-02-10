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
from .functions import unique_attribute_setter
from functools import cached_property
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
    visible: BoolProperty(name="Visible", default=True, update=functions.update_cb)
    origin: BoolProperty(name="Origin")
    construction: BoolProperty(name="Construction")

    @cached_property
    def _shader(self):
        return gpu.shader.from_builtin("3D_UNIFORM_COLOR")
    @cached_property
    def _id_shader(self):
        return gpu.types.GPUShader(vertex_shader, fragment_shader)

    point_size = 6
    point_size_select = 20

    @property
    def line_width(self):
        if self.construction:
            return 0.5
        return 2

    line_width_select = 20

    def __str__(self):
        _, local_index = functions.breakdown_index(self.slvs_index)
        return "{}({})".format(self.__class__.__name__, str(local_index))

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
            global_data.hover = -1

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

    def is_active(self, active_sketch):
        if hasattr(self, "sketch"):
            return self.sketch == active_sketch
        else:
            return not active_sketch

    def is_selectable(self, context):
        if not self.is_visible(context):
            return False

        prefs = functions.get_prefs()
        if prefs.all_entities_selectable:
            return True

        active_sketch = context.scene.sketcher.active_sketch
        if active_sketch and hasattr(self, "sketch"):
            # Allow to select entities that share the active sketch's wp
            return active_sketch.wp == self.sketch.wp
        return self.is_active(active_sketch)

    def color(self, context):
        prefs = functions.get_prefs()
        ts = prefs.theme_settings
        active = self.is_active(context.scene.sketcher.active_sketch)

        if not active:
            if self.hover:
                return ts.entity.highlight
            if self.selected:
                return ts.entity.inactive_selected
            return ts.entity.inactive

        elif self.selected:
            if self.hover:
                return ts.entity.selected_highlight
            return ts.entity.selected
        elif self.hover:
            return ts.entity.highlight

        return ts.entity.default

    @staticmethod
    def restore_opengl_defaults():
        bgl.glLineWidth(1)
        bgl.glPointSize(1)  # ?
        bgl.glDisable(bgl.GL_BLEND)

    def is_visible(self, context):
        if self.origin:
            return context.scene.sketcher.show_origin

        if hasattr(self, "sketch"):
            return self.sketch.is_visible(context) and self.visible
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
        if not self.is_selectable(context):
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
        index = entity.slvs_index if entity else -1
        setattr(self, index_prop, index)

    setattr(cls, name, setter)


class SlvsPoint3D(SlvsGenericEntity, PropertyGroup):
    """Representation of a point in 3D Space.

    Arguments:
        location (FloatVectorProperty): Point's location in the form (x, y, z)
    """
    location: FloatVectorProperty(name="Location", subtype="XYZ", unit="LENGTH")

    def update(self):
        if bpy.app.background:
            return

        coords, indices = functions.draw_cube_3d(*self.location, 0.05)
        self._batch = batch_for_shader(
            self._shader, "POINTS", {"pos": (self.location[:],)}
        )

    def create_slvs_data(self, solvesys, coords=None, group=Solver.group_fixed):
        if not coords:
            coords = self.location

        self.params = [solvesys.addParamV(v, group) for v in coords]

        handle = solvesys.addPoint3d(*self.params, group=group)
        self.py_data = handle

    def update_from_slvs(self, solvesys):
        coords = [solvesys.getParam(i).val for i in self.params]
        self.location = coords

    def closest_picking_point(self, origin, view_vector):
        """Returns the point on this entity which is closest to the picking ray"""
        return self.location

    # TODO: maybe rename -> pivot_point, midpoint
    def placement(self):
        return self.location

    def draw_props(self, layout):
        layout.prop(self, "location")


class SlvsLine3D(SlvsGenericEntity, PropertyGroup):
    """Representation of a line in 3D Space.

    Arguments:
        p1 (SlvsPoint3D): Line's startpoint
        p2 (SlvsPoint3D): Line's endpoint
    """
    def dependencies(self):
        return [self.p1, self.p2]

    def update(self):
        if bpy.app.background:
            return

        p1, p2 = self.p1, self.p2
        self._batch = batch_for_shader(
            self._shader, "LINES", {"pos": (p1.location, p2.location)}
        )

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        handle = solvesys.addLineSegment(self.p1.py_data, self.p2.py_data, group=group)
        self.py_data = handle

    def closest_picking_point(self, origin, view_vector):
        """Returns the point on this entity which is closest to the picking ray"""
        p1 = self.p1.location
        d1 = self.p2.location - p1  # normalize?
        return functions.nearest_point_line_line(p1, d1, origin, view_vector)

    def placement(self):
        return (self.p1.location + self.p2.location) / 2

    @property
    def length(self):
        return (self.p2.location - self.p1.location).length


slvs_entity_pointer(SlvsLine3D, "p1")
slvs_entity_pointer(SlvsLine3D, "p2")


class SlvsNormal3D(SlvsGenericEntity, PropertyGroup):
    """Representation of a normal in 3D Space which is used to
    store a direction.

    This entity isn't currently exposed to the user and gets created
    implicitly when needed.

    Arguments:
        orientation (Quaternion): A quaternion which describes the rotation
    """
    orientation: FloatVectorProperty(subtype="QUATERNION", size=4)

    def update(self):
        pass

    def draw(self, context):
        pass

    def draw_id(self, context):
        pass

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        quat = self.orientation
        handle = solvesys.addNormal3dV(quat.w, quat.x, quat.y, quat.z, group=group)
        self.py_data = handle


from mathutils import Vector, Matrix


class SlvsWorkplane(SlvsGenericEntity, PropertyGroup):
    """Representation of a plane which is defined by an origin point
    and a normal. Workplanes are used to define the position of 2D entities
    which only store the coordinates on the plane.

    Arguments:
        p1 (SlvsPoint3D): Origin Point of the Plane
        nm (SlvsNormal3D): Normal which defines the orientation
    """

    size = 5

    def dependencies(self):
        return [self.p1, self.nm]

    def is_active(self, active_sketch):
        return not active_sketch

    def is_selectable(self, context):
        return self.is_active(context.scene.sketcher.active_sketch)

    def update(self):
        if bpy.app.background:
            return

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

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
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


def hide_sketch(self, context):
    if self.convert_type != "NONE":
        self.visible = False


# TODO: draw sketches and allow selecting
class SlvsSketch(SlvsGenericEntity, PropertyGroup):
    """A sketch groups 2 dimensional entities together and is used to later
    convert geometry to native blender types.

    Entities that belong to a sketch can only be edited as long as the sketch is active.

    Arguments:
        wp (SlvsWorkplane): The base workplane of the sketch
    """
    unique_names = ["name"]

    convert_type: EnumProperty(
        name="Convert Type",
        items=convert_items,
        description="Define how the sketch should be converted in order to be usable in native blender",
        update=hide_sketch,
    )
    fill_shape: BoolProperty(
        name="Fill Shape",
        description="Fill the resulting shape if it's closed",
        default=True,
    )
    solver_state: EnumProperty(
        name="Solver Status", items=global_data.solver_state_items
    )
    target_curve: PointerProperty(type=bpy.types.Curve)
    target_curve_object: PointerProperty(type=bpy.types.Object)
    target_mesh: PointerProperty(type=bpy.types.Mesh)
    target_object: PointerProperty(type=bpy.types.Object)

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

    def update(self):
        pass

    def draw(self, context):
        pass

    def draw_id(self, context):
        pass

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        pass

    def remove_objects(self):
        for ob in (self.target_object, self.target_curve_object):
            if not ob:
                continue
            bpy.data.objects.remove(ob)

    def is_visible(self, context):
        if context.scene.sketcher.active_sketch_i == self.slvs_index:
            return True
        return self.visible

    def get_solver_state(self):
        return functions.bpyEnum(
            global_data.solver_state_items, identifier=self.solver_state
        )

    def solve(self, context):
        return solve_system(context, sketch=self)


slvs_entity_pointer(SlvsSketch, "wp")
SlvsSketch.__setattr__ = unique_attribute_setter


class Entity2D:
    @property
    def wp(self):
        return self.sketch.wp


class SlvsPoint2D(SlvsGenericEntity, PropertyGroup, Entity2D):
    """Representation of a point on a workplane.

    Arguments:
        co (FloatVectorProperty): The coordinates of the point on the worpkplane in the form (U, V)
        sketch (SlvsSketch): The sketch this entity belongs to
    """

    co: FloatVectorProperty(name="Coordinates", subtype="XYZ", size=2, unit="LENGTH")

    def dependencies(self):
        return [
            self.sketch,
        ]

    def update(self):
        if bpy.app.background:
            return

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

    def tweak(self, solvesys, pos, group):
        wrkpln = self.sketch.wp
        u, v, _ = wrkpln.matrix_basis.inverted() @ pos

        self.create_slvs_data(solvesys, group=group)

        # NOTE: When simply initalizing the point on the tweaking positions
        # the solver fails regularly, addWhereDragged fixes a point and might
        # overconstrain a system. When not using addWhereDragged the tweak point
        # might just jump to the tweaked geometry. Bypass this by creating a line
        # perpendicular to move vector and constrain that.

        orig_pos = self.co
        tweak_pos = Vector((u, v))
        tweak_vec = tweak_pos - orig_pos
        perpendicular_vec = Vector((tweak_vec[1], -tweak_vec[0]))

        params = [solvesys.addParamV(val, group) for val in (u, v)]
        startpoint = solvesys.addPoint2d(wrkpln.py_data, *params, group=group)

        p2 = tweak_pos + perpendicular_vec
        params = [solvesys.addParamV(val, group) for val in (p2.x, p2.y)]
        endpoint = solvesys.addPoint2d(wrkpln.py_data, *params, group=group)

        edge = solvesys.addLineSegment(startpoint, endpoint, group=group)
        make_coincident(solvesys, self.py_data, edge, wrkpln.py_data, group, entity_type=SlvsLine2D)

    def create_slvs_data(self, solvesys, coords=None, group=Solver.group_fixed):
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

    def placement(self):
        return self.location

    def draw_props(self, layout):
        col = layout.column()
        col.prop(self, "co")


slvs_entity_pointer(SlvsPoint2D, "sketch")


def set_handles(point):
    point.handle_left_type = "FREE"
    point.handle_right_type = "FREE"


class SlvsLine2D(SlvsGenericEntity, PropertyGroup, Entity2D):
    """Representation of a line in 2D space. Connects p1 and p2 and lies on the
    sketche's workplane.

    Arguments:
        p1 (SlvsPoint2D): Line's startpoint
        p2 (SlvsPoint2D): Line's endpoint
        sketch (SlvsSketch): The sketch this entity belongs to
    """

    def dependencies(self):
        return [self.p1, self.p2, self.sketch]

    def update(self):
        if bpy.app.background:
            return

        p1, p2 = self.p1, self.p2
        coords = (p1.location, p2.location)
        self._batch = batch_for_shader(self._shader, "LINES", {"pos": coords})

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
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

    def midpoint(self):
        return (self.p1.co + self.p2.co) / 2

    def direction_vec(self):
        return self.p2.co - self.p1.co

    @property
    def length(self):
        return (self.p2.co - self.p1.co).length


slvs_entity_pointer(SlvsLine2D, "p1")
slvs_entity_pointer(SlvsLine2D, "p2")
slvs_entity_pointer(SlvsLine2D, "sketch")


class SlvsNormal2D(SlvsGenericEntity, PropertyGroup, Entity2D):
    """Representation of a normal in 2D Space.

    This entity isn't currently exposed to the user and gets created
    implicitly when needed.

    Arguments:
        sketch (SlvsSketch): The sketch to get the orientation from
    """

    def update(self):
        pass

    def draw(self, context):
        pass

    def draw_id(self, context):
        pass

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
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


CURVE_RESOLUTION = 64


class SlvsArc(SlvsGenericEntity, PropertyGroup, Entity2D):
    """Representation of an arc in 2D space around the centerpoint ct. Connects
    p2 to p3 or (viceversa if the option invert_direction is true) with a
    circle segment that is resolution independent. The arc lies on the sketche's workplane.

    Arguments:
        p1 (SlvsPoint2D): Arc's centerpoint
        p2 (SlvsPoint2D): Arc's startpoint
        p2 (SlvsPoint2D): Arc's endpoint
        nm (SlvsNormal3D): Orientation
        sketch (SlvsSketch): The sketch this entity belongs to
    """

    invert_direction: BoolProperty(name="Invert direction")

    @property
    def start(self):
        return self.p2 if self.invert_direction else self.p1

    @property
    def end(self):
        return self.p1 if self.invert_direction else self.p2

    def dependencies(self):
        return [self.nm, self.ct, self.start, self.end, self.sketch]

    def update(self):
        if bpy.app.background:
            return

        ct = self.ct.co
        p1 = self.start.co - ct
        p2 = self.end.co - ct

        radius = p1.length

        coords = []
        if radius and p2.length:
            offset = p1.angle_signed(Vector((1, 0)))
            angle = functions.range_2pi(p2.angle_signed(p1))

            # TODO: resolution should depend on segment length?!
            segments = round(CURVE_RESOLUTION * (angle / (math.pi * 2)))

            coords = functions.coords_arc_2d(
                0, 0, radius, segments, angle=angle, offset=offset
            )

            mat_local = Matrix.Translation(self.ct.co.to_3d())
            mat = self.wp.matrix_basis @ mat_local
            coords = [(mat @ Vector((*co, 0)))[:] for co in coords]

        self._batch = batch_for_shader(self._shader, "LINE_STRIP", {"pos": coords})

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
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

    def placement(self):
        coords = self.ct.co + functions.pol2cart(
            self.radius, self.start_angle + self.angle / 2
        )

        return self.wp.matrix_basis @ coords.to_3d()

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
        return functions.pol2cart(self.radius, self.start_angle + angle) + self.ct.co

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

    def draw_props(self, layout):
        layout.prop(self, "invert_direction")


slvs_entity_pointer(SlvsArc, "nm")
slvs_entity_pointer(SlvsArc, "ct")
slvs_entity_pointer(SlvsArc, "p1")
slvs_entity_pointer(SlvsArc, "p2")
slvs_entity_pointer(SlvsArc, "sketch")


class SlvsCircle(SlvsGenericEntity, PropertyGroup, Entity2D):
    """Representation of a circle in 2D space. The circle is centered at ct whith
    it's size defined by the radius and is resoulution independent.

    Arguments:
        ct (SlvsPoint2D): Circle's centerpoint
        radius (FloatProperty): The radius of the circle
        nm (SlvsNormal2D):
        sketch (SlvsSketch): The sketch this entity belongs to
    """

    radius: FloatProperty(name="Radius", subtype="DISTANCE", min=0.0, unit="LENGTH")

    def dependencies(self):
        return [self.nm, self.ct, self.sketch]

    def update(self):
        if bpy.app.background:
            return

        coords = functions.coords_arc_2d(0, 0, self.radius, CURVE_RESOLUTION)

        u, v = self.ct.co

        mat_local = Matrix.Translation(Vector((u, v, 0)))
        mat = self.wp.matrix_basis @ mat_local
        coords = [(mat @ Vector((*co, 0)))[:] for co in coords]

        self._batch = batch_for_shader(self._shader, "LINE_STRIP", {"pos": coords})

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
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
        return functions.pol2cart(self.radius, angle) + self.ct.co

    def placement(self):
        return self.wp.matrix_basis @ self.point_on_curve(45).to_3d()

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

from typing import Union, Tuple, Type

class SlvsEntities(PropertyGroup):
    """Holds all Solvespace Entities"""

    def _type_index(self, entity: SlvsGenericEntity) -> int:
        return entities.index(type(entity))

    def _set_index(self, entity: SlvsGenericEntity):
        type_index = self._type_index(entity)
        sub_list = getattr(self, entity_collections[type_index])

        local_index = len(sub_list) - 1
        # TODO: handle this case better
        assert local_index < math.pow(2, 20)
        entity.slvs_index = type_index << 20 | local_index

    @staticmethod
    def _breakdown_index(index: int):
        return functions.breakdown_index(index)

    def type_from_index(self, index: int) -> Type[SlvsGenericEntity]:
        if index < 0:
            return None

        type_index, _ = self._breakdown_index(index)

        if type_index >= len(entities):
            return None
        return entities[type_index]

    def _get_list_and_index(self, index: int):
        type_index, local_index = self._breakdown_index(index)
        if type_index < 0 or type_index >= len(entity_collections):
            return None, local_index
        return getattr(self, entity_collections[type_index]), local_index

    def check(self, index: int) -> bool:
        sub_list, i = self._get_list_and_index(index)
        return i < len(sub_list)

    def get(self, index: int) -> SlvsGenericEntity:
        """Get entity by index

        Arguments:
            index: The global index of the entity.

        Returns:
            SlvsGenericEntity: Entity with the given global index or None if not found.
        """
        if index == -1:
            return None
        sub_list, i = self._get_list_and_index(index)
        if not sub_list or i >= len(sub_list):
            return None
        return sub_list[i]

    def remove(self, index: int):
        """Remove entity by index

        Arguments:
            index: The global index of the entity.
        """
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

    def add_point_3d(self, co: Union[Tuple[float, float, float], Vector]) -> SlvsPoint3D:
        """Add a point in 3d space.

        Arguments:
            co: Location of the point in 3d space.

        Returns:
            SlvsPoint3D: The created point.
        """
        if not hasattr(co, "__len__") or len(co) != 3:
            raise TypeError("Argument co must be of length 3")

        p = self.points3D.add()
        p.location = co
        self._set_index(p)
        p.update()
        return p

    def add_line_3d(self, p1: SlvsPoint3D, p2: SlvsPoint3D) -> SlvsLine3D:
        """Add a line in 3d space.

        Arguments:
            p1: Line's startpoint.
            p2: Line's endpoint.

        Returns:
            SlvsLine3D: The created line.
        """
        l = self.lines3D.add()
        l.p1 = p1
        l.p2 = p2
        self._set_index(l)
        l.update()
        return l

    def add_normal_3d(self, quat: Tuple[float, float, float, float]) -> SlvsNormal3D:
        """Add a normal in 3d space.

        Arguments:
            quat: Quaternion which describes the orientation.

        Returns:
            SlvsNormal3D: The created normal.
        """
        nm = self.normals3D.add()
        nm.orientation = quat
        self._set_index(nm)
        nm.update()
        return nm

    def add_workplane(self, p1: SlvsPoint3D, nm: SlvsNormal3D) -> SlvsWorkplane:
        """Add a workplane.

        Arguments:
            p1: Workplane's originpoint.
            nm: Workplane's normal.

        Returns:
            SlvsWorkplane: The created workplane.
        """
        wp = self.workplanes.add()
        wp.p1 = p1
        wp.nm = nm
        self._set_index(wp)
        wp.update()
        return wp

    def add_sketch(self, wp: SlvsWorkplane) -> SlvsSketch:
        """Add a Sketch.

        Arguments:
            wp: Sketch's workplane.

        Returns:
            SlvsSketch: The created sketch.
        """
        sketch = self.sketches.add()
        sketch.wp = wp
        self._set_index(sketch)
        _, i = self._breakdown_index(sketch.slvs_index)
        sketch.name = "Sketch"
        sketch.update()
        return sketch

    def add_point_2d(self, co: Tuple[float, float], sketch: SlvsSketch) -> SlvsPoint2D:
        """Add a point in 2d space.

        Arguments:
            co: Coordinates of the point on the workplane.
            sketch: The sketch this point belongs to.

        Returns:
            SlvsPoint2D: The created point.
        """
        p = self.points2D.add()
        p.co = co
        p.sketch = sketch
        self._set_index(p)
        p.update()
        return p

    def add_line_2d(self, p1: SlvsPoint2D, p2: SlvsPoint2D, sketch: SlvsSketch) -> SlvsLine2D:
        """Add a line in 2d space.

        Arguments:
            p1: Line's startpoint.
            p2: Line's endpoint.
            sketch: The sketch this line belongs to.

        Returns:
            SlvsLine2D: The created line.
        """
        l = self.lines2D.add()
        l.p1 = p1
        l.p2 = p2
        l.sketch = sketch
        self._set_index(l)
        l.update()
        return l

    def add_normal_2d(self, sketch: SlvsSketch) -> SlvsNormal2D:
        """Add a normal in 2d space.

        Arguments:
            sketch: The sketch this normal belongs to.

        Returns:
            SlvsNormal2D: The created normal.
        """
        nm = self.normals2D.add()
        nm.sketch = sketch
        self._set_index(nm)
        nm.update()
        return nm

    def add_arc(self, nm: SlvsNormal2D, ct: SlvsPoint2D, p1: SlvsPoint2D, p2: SlvsPoint2D, sketch: SlvsSketch) -> SlvsArc:
        """Add an arc in 2d space.

        Arguments:
            ct: Arc's centerpoint.
            p1: Arc's startpoint.
            p2: Arc's endpoint.
            sketch: The sketch this arc belongs to.
            nm: Arc's normal.

        Returns:
            SlvsArc: The created arc.
        """
        arc = self.arcs.add()
        arc.nm = nm
        arc.ct = ct
        arc.p1 = p1
        arc.p2 = p2
        arc.sketch = sketch
        self._set_index(arc)
        arc.update()
        return arc

    def add_circle(self, nm: SlvsNormal2D, ct: SlvsPoint2D, radius: float, sketch: SlvsSketch) -> SlvsCircle:
        """Add a circle in 2d space.

        Arguments:
            ct: Circle's centerpoint.
            radius: Circle's radius.
            sketch: The sketch this circle belongs to.
            nm: Circle's normal.

        Returns:
            SlvsCircle: The created circle.
        """
        c = self.circles.add()
        c.nm = nm
        c.ct = ct
        c.radius = radius
        c.sketch = sketch
        self._set_index(c)
        c.update()
        return c

    @property
    def all(self):
        for coll_name in entity_collections:
            entity_coll = getattr(self, coll_name)
            for entity in entity_coll:
                yield entity

    @property
    def selected_entities(self):
        """Return all selected visible entities"""
        items = []
        for index in global_data.selected:
            entity = self.get(index)
            items.append(entity)
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
    failed: BoolProperty(name="Failed")
    signature = ()

    def needs_wp(args):
        return WpReq.OPTIONAL

    def __str__(self):
        return self.label

    def get_workplane(self):
        # NOTE: this could also check through the constraints entity workplanes
        needs_wp = self.needs_wp()

        workplane = None
        if self.sketch_i != -1:
            workplane = self.sketch.wp

        if workplane and needs_wp != WpReq.FREE:
            return workplane.py_data
        elif needs_wp == WpReq.NOT_FREE:
            return None
        else:
            from py_slvs import slvs

            return slvs.SLVS_FREE_IN_3D

    def entities(self):
        props = []
        for prop_name in dir(self):
            if prop_name.endswith("_i") or not prop_name.startswith("entity"):
                continue
            props.append(getattr(self, prop_name))
        return props

    def dependencies(self):
        deps = self.entities()
        if hasattr(self, "sketch"):
            s = self.sketch
            if s:
                deps.append(s)
        return deps

    # TODO: avoid duplicating code
    def update_pointers(self, index_old, index_new):
        for prop_name in dir(self):
            if not prop_name.startswith("entity") or not prop_name.endswith("_i"):
                continue
            prop = getattr(self, prop_name)
            if prop == index_old:
                setattr(self, prop_name, index_new)

    def is_active(self, active_sketch):
        if not hasattr(self, "sketch"):
            return not active_sketch

        show_inactive = not functions.get_prefs().hide_inactive_constraints
        if show_inactive and self.sketch.visible:
            return True

        return self.sketch == active_sketch

    def draw_plane(self):
        if self.sketch_i != -1:
            wp = self.sketch.wp
            return wp.p1.location, wp.normal
        # TODO: return drawing plane for constraints in 3d
        return None, None


# NOTE: When tweaking it's neccesary to constrain a point that is only temporary available
# and has no SlvsPoint representation
def make_coincident(solvesys, point_handle, e2, wp, group, entity_type=None):
    func = None
    set_wp = False

    if entity_type:
        handle = e2
    else:
        entity_type = type(e2)
        handle = e2.py_data

    if entity_type in line:
        func = solvesys.addPointOnLine
        set_wp = True
    elif entity_type in curve:
        func = solvesys.addPointOnCircle
    elif entity_type == SlvsWorkplane:
        func = solvesys.addPointInPlane
    elif entity_type in point:
        func = solvesys.addPointsCoincident
        set_wp = True

    kwargs = {
        "group": group,
    }

    if set_wp:
        kwargs["wrkpln"] = wp

    return func(point_handle, handle, **kwargs)


class SlvsCoincident(GenericConstraint, PropertyGroup):
    """Forces two points to be coincident,
    or a point to lie on a curve, or a point to lie on a plane.

    The point-coincident constraint is available in both 3d and projected versions.
    The 3d point-coincident constraint restricts three degrees of freedom;
    the projected version restricts only two. If two points are drawn in a workplane,
    and then constrained coincident in 3d, then an error will result–they are already
    coincident in one dimension (the dimension normal to the plane),
    so the third constraint equation is redundant.
    """

    type = "COINCIDENT"
    label = "Coincident"
    signature = (point, (*point, *line, SlvsWorkplane, SlvsCircle, SlvsArc))
    # NOTE: Coincident between 3dPoint and Workplane currently doesn't seem to work

    def needs_wp(self):
        if isinstance(self.entity2, SlvsWorkplane):
            return WpReq.FREE
        return WpReq.OPTIONAL

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        return make_coincident(
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


class SlvsEqual(GenericConstraint, PropertyGroup):
    """Forces two lengths, or radiuses to be equal.

    If a line and an arc of a circle are selected, then the length of the line is
    forced equal to the length (not the radius) of the arc.
    """

    # TODO: Restrict or handle constraint between two arcs
    # TODO: Also supports equal angle

    type = "EQUAL"
    label = "Equal"
    signature = (line_arc_circle, line_arc_circle)

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
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

        return func(e1.py_data, e2.py_data, **kwargs)

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
    sketch = context.scene.sketcher.active_sketch
    solve_system(context, sketch=sketch)


from mathutils import Euler
from mathutils.geometry import distance_point_to_plane


def get_side_of_line(line_start, line_end, point):
    line_end = line_end - line_start
    point = point - line_start
    return -(
        (line_end.x - line_start.x) * (point.y - line_start.y)
        - (line_end.y - line_start.y) * (point.x - line_start.x)
    )


class SlvsDistance(GenericConstraint, PropertyGroup):
    """Sets the distance between a point and some other entity (point/line/Workplane).
    """

    label = "Distance"
    value: FloatProperty(
        name=label, subtype="DISTANCE", unit="LENGTH", update=update_system_cb
    )
    draw_offset: FloatProperty(name="Draw Offset", default=0.3)
    type = "DISTANCE"
    signature = (point, (*point, *line, SlvsWorkplane))

    def needs_wp(self):
        if isinstance(self.entity2, SlvsWorkplane):
            return WpReq.FREE
        return WpReq.OPTIONAL

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
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

        return func(self.value, e1.py_data, e2.py_data, **kwargs)

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

    def init_props(self):
        # Set initial distance value to the current spacing
        e1, e2 = self.entity1, self.entity2
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

    def draw_props(self, layout):
        layout.prop(self, "value")

    def value_placement(self, context):
        """location to display the constraint value"""
        region = context.region
        rv3d = context.space_data.region_3d
        coords = self.matrix_basis() @ Vector((0, self.draw_offset, 0))
        return location_3d_to_region_2d(region, rv3d, coords)

slvs_entity_pointer(SlvsDistance, "entity1")
slvs_entity_pointer(SlvsDistance, "entity2")
slvs_entity_pointer(SlvsDistance, "sketch")


class SlvsDiameter(GenericConstraint, PropertyGroup):
    """Sets the diameter of an arc or a circle.
    """

    label = "Diameter"
    value: FloatProperty(
        name=label, subtype="DISTANCE", unit="LENGTH", update=update_system_cb
    )
    draw_offset: FloatProperty(name="Draw Offset", default=45, subtype="ANGLE")
    type = "DIAMETER"
    signature = (curve,)

    def needs_wp(self):
        return WpReq.OPTIONAL

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        return solvesys.addDiameter(self.value, self.entity1.py_data, group=group)

    def init_props(self):
        return self.entity1.radius * 2, None

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

    def draw_props(self, layout):
        layout.prop(self, "value")

    def value_placement(self, context):
        """location to display the constraint value"""
        region = context.region
        rv3d = context.space_data.region_3d
        coords = self.matrix_basis() @ Vector()
        return location_3d_to_region_2d(region, rv3d, coords)


slvs_entity_pointer(SlvsDiameter, "entity1")
slvs_entity_pointer(SlvsDiameter, "sketch")


from mathutils.geometry import intersect_line_line_2d


class SlvsAngle(GenericConstraint, PropertyGroup):
    """Sets the angle between two lines, applies in 2D only.

    The constraint's setting can be used to to constrain the supplementary angle.
    """

    label = "Angle"
    value: FloatProperty(
        name=label, subtype="ANGLE", unit="ROTATION", update=update_system_cb
    )
    setting: BoolProperty(name="Invert", update=update_system_cb)
    draw_offset: FloatProperty(name="Draw Offset", default=1)
    type = "ANGLE"
    signature = ((SlvsLine2D,), (SlvsLine2D,))

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        kwargs = {
            "group": group,
        }

        wp = self.get_workplane()
        if wp:
            kwargs["wrkpln"] = wp

        return solvesys.addAngle(
            math.degrees(self.value),
            self.setting,
            self.entity1.py_data,
            self.entity2.py_data,
            **kwargs,
        )

    def matrix_basis(self):
        if self.sketch_i == -1:
            return Matrix()

        sketch = self.sketch

        line1 = self.entity1
        line2 = self.entity2

        origin = functions.get_line_intersection(
            *functions.line_abc_form(line1.p1.co, line1.p2.co),
            *functions.line_abc_form(line2.p1.co, line2.p2.co),
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

    @staticmethod
    def _get_angle(A, B):
        # (A dot B)/(|A||B|) = cos(valA)
        divisor = A.length * B.length
        if not divisor:
            return 0.0

        x = A.dot(B) / divisor
        x = max(-1, min(x, 1))

        return math.degrees(math.acos(x))

    @staticmethod
    def _get_angle_inv(A, B):
        # (A dot B)/(|A||B|) = -cos(valA)
        divisor = A.length * B.length
        if not divisor:
            return 0.0

        x = -A.dot(B) / divisor
        x = max(-1, min(x, 1))

        return math.degrees(math.acos(x))

    def init_props(self):
        # Set initial angle value to the current angle
        line1, line2 = self.entity1, self.entity2

        vec1, vec2 = line1.direction_vec(), line2.direction_vec()
        angle_std = self._get_angle(vec1, vec2)
        angle_inv = self._get_angle_inv(vec1, vec2)

        setting = angle_inv < angle_std
        angle = angle_inv if setting else angle_std

        self.value = angle
        self.setting = setting

        # Get the radius
        origin = functions.get_line_intersection(
            *functions.line_abc_form(line1.p1.co, line1.p2.co),
            *functions.line_abc_form(line2.p1.co, line2.p2.co),
        )

        dist = max(
            (line1.midpoint() - origin).length, (line2.midpoint() - origin).length, 0.5
        )
        self.draw_offset = dist if not setting else -dist

        return math.radians(angle), setting

    def update_draw_offset(self, pos, ui_scale):
        self.draw_offset = math.copysign(pos.length / ui_scale, pos.x)

    def draw_props(self, layout):
        layout.prop(self, "value")
        layout.prop(self, "setting")

    def value_placement(self, context):
        """location to display the constraint value"""
        region = context.region
        rv3d = context.space_data.region_3d
        coords = self.matrix_basis() @ Vector((self.draw_offset, 0, 0))
        return location_3d_to_region_2d(region, rv3d, coords)


slvs_entity_pointer(SlvsAngle, "entity1")
slvs_entity_pointer(SlvsAngle, "entity2")
slvs_entity_pointer(SlvsAngle, "sketch")


class SlvsParallel(GenericConstraint, PropertyGroup):
    """Forces two lines to be parallel. Applies only in 2D.
    """

    type = "PARALLEL"
    label = "Parallel"
    signature = ((SlvsLine2D,), (SlvsLine2D,))

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        return solvesys.addParallel(
            self.entity1.py_data,
            self.entity2.py_data,
            wrkpln=self.get_workplane(),
            group=group,
        )


slvs_entity_pointer(SlvsParallel, "entity1")
slvs_entity_pointer(SlvsParallel, "entity2")
slvs_entity_pointer(SlvsParallel, "sketch")


# NOTE: this could also support constraining two points
class SlvsHorizontal(GenericConstraint, PropertyGroup):
    """Forces a line segment to be horizontal. It applies in 2D Space only because
    the meaning of horizontal or vertical is defined by the workplane.
    """

    type = "HORIZONTAL"
    label = "Horizontal"
    signature = ((SlvsLine2D,),)

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        return solvesys.addLineHorizontal(
            self.entity1.py_data, wrkpln=self.get_workplane(), group=group
        )


slvs_entity_pointer(SlvsHorizontal, "entity1")
slvs_entity_pointer(SlvsHorizontal, "sketch")


class SlvsVertical(GenericConstraint, PropertyGroup):
    """Forces a line segment to be vertical. It applies in 2D Space only because
    the meaning of horizontal or vertical is defined by the workplane.
    """

    type = "VERTICAL"
    label = "Vertical"
    signature = ((SlvsLine2D,),)

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        return solvesys.addLineVertical(
            self.entity1.py_data, wrkpln=self.get_workplane(), group=group
        )


slvs_entity_pointer(SlvsVertical, "entity1")
slvs_entity_pointer(SlvsVertical, "sketch")


class SlvsPerpendicular(GenericConstraint, PropertyGroup):
    """Forces two lines to be perpendicular, applies only in 2D. This constraint
    is equivalent to an angle constraint for ninety degrees.
    """
    type = "PERPENDICULAR"
    label = "Perpendicular"
    signature = ((SlvsLine2D,), (SlvsLine2D,))

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        return solvesys.addPerpendicular(
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


class SlvsTangent(GenericConstraint, PropertyGroup):
    """Forces two curves (arc/circle) or a curve and a line to be tangent.
    """
    type = "TANGENT"
    label = "Tangent"
    signature = (curve, (SlvsLine2D, *curve))

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        e1, e2 = self.entity1, self.entity2
        wp = self.get_workplane()

        # check if entities share a point
        point = connection_point(e1, e2)
        if point and not isinstance(e2, SlvsCircle):
            if isinstance(e2, SlvsLine2D):
                return solvesys.addArcLineTangent(
                    e1.direction(point),
                    e1.py_data,
                    e2.py_data,
                    group=group,
                )
            elif isinstance(e2, SlvsArc):
                return solvesys.addCurvesTangent(
                    e1.direction(point),
                    e2.direction(point),
                    e1.py_data,
                    e2.py_data,
                    wrkpln=wp,
                    group=group,
                )

        elif isinstance(e2, SlvsLine2D):
            orig = e2.p1.co
            coords = (e1.ct.co - orig).project(e2.p2.co - orig) + orig
            params = [solvesys.addParamV(v, group) for v in coords]
            p = solvesys.addPoint2d(wp, *params, group=group)
            l = solvesys.addLineSegment(e1.ct.py_data, p, group=group)

            return (
                make_coincident(solvesys, p, e1, wp, group),
                make_coincident(solvesys, p, e2, wp, group),
                solvesys.addPerpendicular(e2.py_data, l, wrkpln=wp, group=group),
            )

        elif type(e2) in curve:
            coords = (e1.ct.co + e2.ct.co) / 2
            params = [solvesys.addParamV(v, group) for v in coords]
            p = solvesys.addPoint2d(wp, *params, group=group)
            l = solvesys.addLineSegment(e1.ct.py_data, e2.ct.py_data, group=group)

            return (
                make_coincident(solvesys, p, e1, wp, group),
                make_coincident(solvesys, p, e2, wp, group),
                solvesys.addPointOnLine(p, l, group=group, wrkpln=wp),
            )


slvs_entity_pointer(SlvsTangent, "entity1")
slvs_entity_pointer(SlvsTangent, "entity2")
slvs_entity_pointer(SlvsTangent, "sketch")


class SlvsMidpoint(GenericConstraint, PropertyGroup):
    """Forces a point to lie on the midpoint of a line.
    """

    type = "MIDPOINT"
    label = "Midpoint"
    signature = (point, line)

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        return solvesys.addMidPoint(
            self.entity1.py_data,
            self.entity2.py_data,
            wrkpln=self.get_workplane(),
            group=group,
        )


slvs_entity_pointer(SlvsMidpoint, "entity1")
slvs_entity_pointer(SlvsMidpoint, "entity2")
slvs_entity_pointer(SlvsMidpoint, "sketch")


class SlvsSymmetric(GenericConstraint, PropertyGroup):
    """Forces two points to be symmetric about a plane.

    The symmetry plane may be a workplane when used in 3D. Or, the symmetry plane
    may be specified as a line in a workplane; the symmetry plane is then through
    that line, and normal to the workplane.

    """

    type = "SYMMETRIC"
    label = "Symmetric"

    # TODO: not all combinations are possible!
    signature = (
        point,
        point,
        (SlvsLine2D, SlvsWorkplane),
    )

    def needs_wp(self):
        if isinstance(self.entity3, SlvsLine2D):
            return WpReq.NOT_FREE
        return WpReq.FREE

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        e1, e2, e3 = self.entity1, self.entity2, self.entity3

        # NOTE: this doesn't seem to work correctly, acts like addSymmetricVertical
        if isinstance(e3, SlvsLine2D):
            return solvesys.addSymmetricLine(
                e1.py_data,
                e2.py_data,
                e3.py_data,
                self.get_workplane(),
                group=group,
            )

        elif isinstance(e3, SlvsWorkplane):
            return solvesys.addSymmetric(
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


class SlvsRatio(GenericConstraint, PropertyGroup):
    """Defines the ratio between the lengths of two line segments.

    The order matters; the ratio is defined as length of entity1 : length of entity2.
    """
    type = "RATIO"
    label = "Ratio"

    value: FloatProperty(
        name=label, subtype="UNSIGNED", update=update_system_cb, min=0.0
    )

    signature = (
        line,
        line,
    )

    def needs_wp(self):
        if isinstance(self.entity1, SlvsLine2D) or isinstance(self.entity2, SlvsLine2D):
            return WpReq.NOT_FREE
        return WpReq.FREE

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        e1, e2 = self.entity1, self.entity2

        return solvesys.addLengthRatio(
            self.value,
            e1.py_data,
            e2.py_data,
            self.get_workplane(),
            group=group,
        )

    def init_props(self):
        line1, line2 = self.entity1, self.entity2

        value = line1.length / line2.length
        return value, None

    def draw_props(self, layout):
        layout.prop(self, "value")


slvs_entity_pointer(SlvsRatio, "entity1")
slvs_entity_pointer(SlvsRatio, "entity2")
slvs_entity_pointer(SlvsRatio, "sketch")

# TODO: Support advanced constraint types
# - symmetric_h
# - symmetric_v
# - ratio
# - same orientation
# - distance projected


# class SlvsDistanceProj(GenericConstraint, PropertyGroup):
#     value: FloatProperty()
#     type = 'DISTANCE_PROJ'
#     name = 'Projected Distance'
#     signature = ((SlvsPoint3D, ), (SlvsPoint3D, ))
##
#     def needs_wp(self):
#         return WpReq.OPTIONAL
#
#     def create_slvs_data(self, solvesys):
#         return solvesys.distance_proj(self.entity1.py_data, self.entity2.py_data, self.value)
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
    SlvsRatio,
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

    def new_from_type(self, type: str) -> GenericConstraint:
        """Create a constraint by type.

        Arguments:
            type: Type of the constraint to be created.
        """
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

    def get_from_type_index(self, type: str, index: int) -> GenericConstraint:
        """Get constraint by type and local index.

        Arguments:
            type: Constraint's type.
            index: Constraint's local index.

        Returns:
            GenericConstraint: Constraint with the given type and index or None if not found.
        """
        list = getattr(self, type.lower())
        if not list or index >= len(list):
            return None
        return list[index]

    def get_index(self, constr: GenericConstraint) -> int:
        """Get the index of a constraint in it's collection.

        Arguments:
            constr: Constraint to get the index for.

        Returns:
            int: Index of the constraint or -1 if not found.
        """
        list = getattr(self, constr.type.lower())
        for i, item in enumerate(list):
            if item == constr:
                return i
        return -1

    def remove(self, constr: GenericConstraint):
        """Remove a constraint.

        Arguments:
            constr: Constraint to be removed.
        """
        i = self.get_index(constr)
        self.get_list(constr.type).remove(i)

    @property
    def all(self):
        for entity_list in self.get_lists():
            for entity in entity_list:
                yield entity

    def add_coincident(self, entity1: SlvsGenericEntity, entity2: SlvsGenericEntity, sketch: SlvsSketch=None) -> SlvsCoincident:
        """Add a coincident constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.

        Returns:
            SlvsCoincident: The created constraint.
        """
        c = self.coincident.add()
        c.entity1 = entity1
        c.entity2 = entity2
        if sketch:
            c.sketch = sketch
        return c

    def add_equal(self, entity1: SlvsGenericEntity, entity2: SlvsGenericEntity, sketch: SlvsSketch=None) -> SlvsEqual:
        """Add an equal constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.

        Returns:
            SlvsEqual: The created constraint.
        """
        c = self.equal.add()
        c.entity1 = entity1
        c.entity2 = entity2
        if sketch:
            c.sketch = sketch
        return c

    def add_distance(self, entity1: SlvsGenericEntity, entity2: SlvsGenericEntity, sketch: SlvsSketch=None, init: bool=False) -> SlvsDistance:
        """Add a distance constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.
            init: Initalize the constraint based on the given entities.

        Returns:
            SlvsDistance: The created constraint.
        """
        c = self.distance.add()
        c.entity1 = entity1
        c.entity2 = entity2
        if sketch:
            c.sketch = sketch
        if init:
            c.init_props()
        return c

    def add_angle(self, entity1: SlvsGenericEntity, entity2: SlvsGenericEntity, sketch: SlvsSketch=None, init: bool=False) -> SlvsAngle:
        """Add an angle constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.
            init: Initalize the constraint based on the given entities.

        Returns:
            SlvsAngle: The created constraint.
        """
        c = self.angle.add()
        c.entity1 = entity1
        c.entity2 = entity2
        if sketch:
            c.sketch = sketch
        if init:
            c.init_props()
        return c

    def add_diameter(self, entity1: SlvsGenericEntity, sketch: SlvsSketch=None, init: bool=False) -> SlvsDiameter:
        """Add a diameter constraint.

        Arguments:
            entity1: -
            sketch: The sketch this constraint belongs to.
            init: Initalize the constraint based on the given entities.

        Returns:
            SlvsDiameter: The created constraint.
        """
        c = self.diameter.add()
        c.entity1 = entity1
        if sketch:
            c.sketch = sketch
        if init:
            c.init_props()
        return c

    def add_parallel(self, entity1: SlvsGenericEntity, entity2: SlvsGenericEntity, sketch: SlvsSketch=None) -> SlvsParallel:
        """Add a parallel constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.

        Returns:
            SlvsParallel: The created constraint.
        """
        c = self.parallel.add()
        c.entity1 = entity1
        c.entity2 = entity2
        if sketch:
            c.sketch = sketch
        return c

    def add_horizontal(self, entity1: SlvsGenericEntity, sketch: SlvsSketch=None) -> SlvsHorizontal:
        """Add a horizontal constraint.

        Arguments:
            entity1: -
            sketch: The sketch this constraint belongs to.

        Returns:
            SlvsHorizontal: The created constraint.
        """
        c = self.horizontal.add()
        c.entity1 = entity1
        if sketch:
            c.sketch = sketch
        return c

    def add_vertical(self, entity1: SlvsGenericEntity, sketch: SlvsSketch=None) -> SlvsVertical:
        """Add a vertical constraint.

        Arguments:
            entity1: -
            sketch: The sketch this constraint belongs to.

        Returns:
            SlvsVertical: The created constraint.
        """
        c = self.vertical.add()
        c.entity1 = entity1
        if sketch:
            c.sketch = sketch
        return c

    def add_tangent(self, entity1: SlvsGenericEntity, entity2: SlvsGenericEntity, sketch: SlvsSketch=None) -> SlvsTangent:
        """Add a tangent constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.

        Returns:
            SlvsTangent: The created constraint.
        """
        c = self.tangent.add()
        c.entity1 = entity1
        c.entity2 = entity2
        if sketch:
            c.sketch = sketch
        return c

    def add_midpoint(self, entity1: SlvsGenericEntity, entity2: SlvsGenericEntity, sketch: SlvsSketch=None) -> SlvsMidpoint:
        """Add a midpoint constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.

        Returns:
            SlvsMidpoint: The created constraint.
        """
        c = self.midpoint.add()
        c.entity1 = entity1
        c.entity2 = entity2
        if sketch:
            c.sketch = sketch
        return c

    def add_perpendicular(self, entity1: SlvsGenericEntity, entity2: SlvsGenericEntity, sketch: SlvsSketch=None) -> SlvsPerpendicular:
        """Add a perpendicular constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.

        Returns:
            SlvsPerpendicular: The created constraint.
        """
        c = self.perpendicular.add()
        c.entity1 = entity1
        c.entity2 = entity2
        if sketch:
            c.sketch = sketch
        return c

    def add_ratio(self, entity1: SlvsGenericEntity, entity2: SlvsGenericEntity, sketch: SlvsSketch=None, init: bool=False) -> SlvsRatio:
        """Add a ratio constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.
            init: Initalize the constraint based on the given entities.

        Returns:
            SlvsRatio: The created constraint.
        """
        c = self.ratio.add()
        c.entity1 = entity1
        c.entity2 = entity2
        if sketch:
            c.sketch = sketch
        if init:
            c.init_props()
        return c


for cls in constraints:
    name = cls.type.lower()
    func_name = "add_" + name

    # Create constraint collections
    annotations = {}
    if hasattr(SlvsConstraints, "__annotations__"):
        annotations = SlvsConstraints.__annotations__.copy()

    annotations[name] = CollectionProperty(type=cls)
    setattr(SlvsConstraints, "__annotations__", annotations)


class SketcherProps(PropertyGroup):
    """The base structure for geometry sketcher"""
    hover: IntProperty(name="Hovered Entity", default=-1)
    entities: PointerProperty(type=SlvsEntities)
    constraints: PointerProperty(type=SlvsConstraints)
    show_origin: BoolProperty(name="Show Origin Entities")

    # this is needed for the sketches ui list
    ui_active_sketch: IntProperty()

    @property
    def all(self):
        """Iterate over entities and constraints of every type"""
        for e in self.entities.all:
            yield e
        for c in self.constraints.all:
            yield c

    def solve(self, context):
        return solve_system(context)



slvs_entity_pointer(SketcherProps, "active_sketch", update=functions.update_cb)


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
