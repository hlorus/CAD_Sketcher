from typing import Generator, Union, Tuple, Type
import logging
import math
from statistics import mean

import bpy
from bpy.types import PropertyGroup, Context, UILayout
from bpy.props import (
    CollectionProperty,
    PointerProperty,
    FloatProperty,
    IntProperty,
    BoolProperty,
    IntVectorProperty,
    FloatVectorProperty,
    EnumProperty,
    StringProperty,
)
import bgl
from bpy_extras.view3d_utils import location_3d_to_region_2d
import gpu
from gpu_extras.batch import batch_for_shader
import mathutils
from mathutils import Vector, Matrix, Euler
from mathutils.geometry import intersect_line_line_2d, intersect_sphere_sphere_2d, intersect_line_sphere_2d, distance_point_to_plane
from py_slvs import slvs

from . import global_data, functions, preferences
from .shaders import Shaders
from .solver import solve_system, Solver
from .functions import pol2cart, unique_attribute_setter
from .declarations import Operators
from .global_data import WpReq

logger = logging.getLogger(__name__)


class SlvsGenericEntity:

    def entity_name_getter(self):
        return self.get("name", str(self))

    def entity_name_setter(self, new_name):
        self["name"] = new_name

    slvs_index: IntProperty(name="Global Index", default=-1)
    name: StringProperty(
        name="Name",
        get=entity_name_getter,
        set=entity_name_setter,
        options={"SKIP_SAVE"},
    )
    fixed: BoolProperty(name="Fixed")
    visible: BoolProperty(name="Visible", default=True, update=functions.update_cb)
    origin: BoolProperty(name="Origin")
    construction: BoolProperty(name="Construction")

    dirty: BoolProperty(name="Needs Update", default=True, options={"SKIP_SAVE"})

    @classmethod
    @property
    def type(cls) -> str:
        return cls.__name__

    @property
    def is_dirty(self) -> bool:
        if self.dirty:
            return True

        if not hasattr(self, "dependencies"):
            return False
        deps = self.dependencies()
        for e in deps:
            # NOTE: might has to ckech through deps recursively -> e.is_dirty
            if e.dirty:
                return True
        return False

    @is_dirty.setter
    def is_dirty(self, value: bool):
        self.dirty = value

    @property
    def _shader(self):
        if self.is_point():
            return Shaders.uniform_color_3d()
        return Shaders.uniform_color_line_3d()

    @property
    def _id_shader(self):
        if self.is_point():
            return Shaders.id_shader_3d()
        return Shaders.id_line_3d()

    @property
    def point_size(self):
        return 5 * preferences.get_scale()

    @property
    def point_size_select(self):
        return 20 * preferences.get_scale()

    @property
    def line_width(self):
        scale = preferences.get_scale()
        if self.construction:
            return 1.5 * scale
        return 2 * scale

    @property
    def line_width_select(self):
        return 20 * preferences.get_scale()

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

    def is_selectable(self, context: Context):
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

    def is_highlight(self):
        return self.hover or self in global_data.highlight_entities

    def color(self, context: Context):
        prefs = functions.get_prefs()
        ts = prefs.theme_settings
        active = self.is_active(context.scene.sketcher.active_sketch)
        highlight = self.is_highlight()

        if not active:
            if highlight:
                return ts.entity.highlight
            if self.selected:
                return ts.entity.inactive_selected
            return ts.entity.inactive

        elif self.selected:
            if highlight:
                return ts.entity.selected_highlight
            return ts.entity.selected
        elif highlight:
            return ts.entity.highlight

        return ts.entity.default

    @staticmethod
    def restore_opengl_defaults():
        bgl.glLineWidth(1)
        bgl.glPointSize(1)  # ?
        bgl.glDisable(bgl.GL_BLEND)

    def is_visible(self, context: Context) -> bool:
        if self.origin:
            return context.scene.sketcher.show_origin

        if hasattr(self, "sketch"):
            return self.sketch.is_visible(context) and self.visible
        return self.visible

    def is_dashed(self):
        return False

    def draw(self, context):
        if not self.is_visible(context):
            return None

        shader = self._shader
        shader.bind()

        bgl.glEnable(bgl.GL_BLEND)
        bgl.glPointSize(self.point_size)

        col = self.color(context)
        shader.uniform_float("color", col)

        if not self.is_point():
            shader.uniform_bool("dashed", (self.is_dashed(),))

        if not self.is_point():
            viewport = [context.area.width, context.area.height]
            shader.uniform_float("Viewport", viewport)
            shader.uniform_float("thickness", self.line_width)

        self._batch.draw(shader)
        gpu.shader.unbind()
        self.restore_opengl_defaults()

    def draw_id(self, context):
        # Note: Design Question, should it be possible to select elements that are not active?!
        # e.g. to activate a sketch
        # maybe it should be dynamically defined what is selectable (points only, lines only, ...)

        batch = self._batch
        shader = self._id_shader
        shader.bind()

        bgl.glPointSize(self.point_size_select)

        shader.uniform_float("color", (*functions.index_to_rgb(self.slvs_index), 1.0))
        if not self.is_point():
            viewport = [context.area.width, context.area.height]
            shader.uniform_float("Viewport", viewport)
            shader.uniform_float("thickness", self.line_width_select)
            shader.uniform_bool("dashed", (False,))

        batch.draw(shader)
        gpu.shader.unbind()
        self.restore_opengl_defaults()

    def create_slvs_data(self, solvesys):
        """Create a solvespace entity from parameters"""
        raise NotImplementedError

    def update_from_slvs(self, solvesys):
        """Update parameters from the solvespace entity"""
        pass

    def update_pointers(self, index_old, index_new):
        def _update(name):
            prop = getattr(self, name)
            if prop == index_old:
                logger.debug(
                    "Update reference {} of {} to {}: ".format(name, self, index_new)
                )
                setattr(self, name, index_new)

        for prop_name in dir(self):
            if not prop_name.endswith("_i"):
                continue
            _update(prop_name)

        if hasattr(self, "target_object") and self.target_object:
            ob = self.target_object
            if ob.sketch_index == index_old:
                ob.sketch_index = index_new

    def dependencies(self):
        return []

    def draw_props(self, layout):
        is_experimental = preferences.is_experimental()

        # Header
        layout.prop(self, "name", text="")

        # Info block
        layout.separator()
        layout.label(text="Type: " + type(self).__name__)
        layout.label(text="Is Origin: " + str(self.origin))

        if is_experimental:
            sub = layout.column()
            sub.scale_y = 0.8
            sub.label(text="Index: " + str(self.slvs_index))
            sub.label(text="Dependencies:")
            for e in self.dependencies():
                sub.label(text=str(e))

        # General props
        layout.separator()
        layout.prop(self, "visible")
        layout.prop(self, "fixed")
        layout.prop(self, "construction")

        # Specific prop
        layout.separator()
        sub = layout.column()

        # Delete
        layout.separator()
        layout.operator(Operators.DeleteEntity, icon='X').index = self.slvs_index

        return sub

    def tag_update(self, _context=None):
        # context argument ignored
        if not self.is_dirty:
            self.is_dirty = True

    def is_3d(self):
        return not hasattr(self, "sketch")

    def is_2d(self):
        return hasattr(self, "sketch")

    @classmethod
    def is_point(cls):
        return False

    @classmethod
    def is_line(cls):
        return False

    @classmethod
    def is_curve(cls):
        return False

    @classmethod
    def is_closed(cls):
        return False


# Drawing a point might not include points coord itself but rather a series of virtual points around it
# so a Entity might refer another point entity and/or add a set of coords
#
# Different shaders are needed:
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


def tag_update(self, context: Context):
    self.tag_update()


class Point3D(SlvsGenericEntity):
    @classmethod
    def is_point(cls):
        return True

    def update(self):
        if bpy.app.background:
            return

        coords, indices = functions.draw_cube_3d(*self.location, 0.05)
        self._batch = batch_for_shader(
            self._shader, "POINTS", {"pos": (self.location[:],)}
        )
        self.is_dirty = False

    # TODO: maybe rename -> pivot_point, midpoint
    def placement(self):
        return self.location

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


class SlvsPoint3D(Point3D, PropertyGroup):
    """Representation of a point in 3D Space.

    Arguments:
        location (FloatVectorProperty): Point's location in the form (x, y, z)
    """

    location: FloatVectorProperty(
        name="Location",
        description="The location of the point",
        subtype="XYZ",
        unit="LENGTH",
        update=SlvsGenericEntity.tag_update
    )

    def draw_props(self, layout):
        sub = super().draw_props(layout)
        sub.prop(self, "location")
        return sub


class SlvsLine3D(SlvsGenericEntity, PropertyGroup):
    """Representation of a line in 3D Space.

    Arguments:
        p1 (SlvsPoint3D): Line's startpoint
        p2 (SlvsPoint3D): Line's endpoint
    """

    @classmethod
    def is_line(cls):
        return True

    def dependencies(self):
        return [self.p1, self.p2]

    def is_dashed(self):
        return self.construction

    def update(self):
        if bpy.app.background:
            return

        p1, p2 = self.p1.location, self.p2.location
        coords = (p1, p2)

        kwargs = {"pos": coords}
        self._batch = batch_for_shader(self._shader, "LINES", kwargs)

        self.is_dirty = False

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


class Normal3D(SlvsGenericEntity):
    def update(self):
        self.is_dirty = False

    def draw(self, context: Context):
        pass

    def draw_id(self, context: Context):
        pass

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        quat = self.orientation
        handle = solvesys.addNormal3dV(quat.w, quat.x, quat.y, quat.z, group=group)
        self.py_data = handle


class SlvsNormal3D(Normal3D, PropertyGroup):
    """Representation of a normal in 3D Space which is used to
    store a direction.

    This entity isn't currently exposed to the user and gets created
    implicitly when needed.

    Arguments:
        orientation (Quaternion): A quaternion which describes the rotation
    """

    orientation: FloatVectorProperty(
        name="Orientation",
        description="Quaternion which describes the orientation of the normal",
        subtype="QUATERNION",
        size=4,
        update=SlvsGenericEntity.tag_update,
    )
    pass


def get_face_orientation(mesh, face):
    # returns quaternion describing the face orientation in objectspace
    normal = mathutils.geometry.normal([mesh.vertices[i].co for i in face.vertices])
    return normal.to_track_quat("Z", "X")


def get_face_midpoint(quat, ob, face):
    """ Average distance from origin to face vertices. """
    mesh = ob.data
    coords = [mesh.vertices[i].co.copy() for i in face.vertices]
    quat_inv = quat.inverted()
    for v in coords:
        v.rotate(quat_inv)
    dist = mean([co[2] for co in coords])

    # offset origin along normal by average distance
    pos = Vector((0, 0, dist))
    pos.rotate(quat)
    return ob.matrix_world @ pos


class SlvsWorkplane(SlvsGenericEntity, PropertyGroup):
    """Representation of a plane which is defined by an origin point
    and a normal. Workplanes are used to define the position of 2D entities
    which only store the coordinates on the plane.

    Arguments:
        p1 (SlvsPoint3D): Origin Point of the Plane
        nm (SlvsNormal3D): Normal which defines the orientation
    """

    size = 0.4

    def dependencies(self):
        return [self.p1, self.nm]

    # def is_active(self, active_sketch):
    #     return not active_sketch

    # def is_selectable(self, context):
    #     return self.is_active(context.scene.sketcher.active_sketch)

    def update(self):
        if bpy.app.background:
            return

        p1, nm = self.p1, self.nm

        coords = functions.draw_rect_2d(0, 0, self.size, self.size)
        coords = [(Vector(co))[:] for co in coords]

        indices = ((0, 1), (1, 2), (2, 3), (3, 0))
        self._batch = batch_for_shader(
            self._shader, "LINES", {"pos": coords}, indices=indices
        )
        self.is_dirty = False

    # NOTE: probably better to avoid overwriting draw func..
    def draw(self, context):
        if not self.is_visible(context):
            return

        with gpu.matrix.push_pop():
            scale = context.region_data.view_distance
            gpu.matrix.multiply_matrix(self.matrix_basis)
            gpu.matrix.scale(Vector((scale, scale, scale)))

            col = self.color(context)
            # Let parent draw outline
            super().draw(context)

            # Additionally draw a face
            col_surface = col[:-1] + (0.2,)

            shader = Shaders.uniform_color_3d()
            shader.bind()
            bgl.glEnable(bgl.GL_BLEND)

            shader.uniform_float("color", col_surface)

            coords = functions.draw_rect_2d(0, 0, self.size, self.size)
            coords = [Vector(co)[:] for co in coords]
            indices = ((0, 1, 2), (0, 2, 3))
            batch = batch_for_shader(shader, "TRIS", {"pos": coords}, indices=indices)
            batch.draw(shader)

        self.restore_opengl_defaults()

    def draw_id(self, context):
        with gpu.matrix.push_pop():
            scale = context.region_data.view_distance
            gpu.matrix.multiply_matrix(self.matrix_basis)
            gpu.matrix.scale(Vector((scale, scale, scale)))
            super().draw_id(context)

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


# TODO: draw sketches and allow selecting
class SlvsSketch(SlvsGenericEntity, PropertyGroup):
    """A sketch groups 2 dimensional entities together and is used to later
    convert geometry to native blender types.

    Entities that belong to a sketch can only be edited as long as the sketch is active.

    Arguments:
        wp (SlvsWorkplane): The base workplane of the sketch
    """

    unique_names = ["name"]

    def hide_sketch(self, context):
        if self.convert_type != "NONE":
            self.visible = False

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
    dof: IntProperty(name="Degrees of Freedom", max=6)
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
        self.is_dirty = False

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


class Point2D(SlvsGenericEntity, Entity2D):
    @classmethod
    def is_point(cls):
        return True

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
        self.is_dirty = False

    @property
    def location(self):
        u, v = self.co
        mat_local = Matrix.Translation(Vector((u, v, 0)))
        mat = self.wp.matrix_basis @ mat_local
        return mat @ Vector((0, 0, 0))

    def placement(self):
        return self.location

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


slvs_entity_pointer(Point2D, "sketch")


class SlvsPoint2D(Point2D, PropertyGroup):
    """Representation of a point in 2D space.

    Arguments:
        co (FloatVectorProperty): The coordinates of the point on the worpkplane in the form (U, V)
        sketch (SlvsSketch): The sketch this entity belongs to
    """

    co: FloatVectorProperty(
        name="Coordinates",
        description="The coordinates of the point on it's sketch",
        subtype="XYZ",
        size=2,
        unit="LENGTH",
        update=SlvsGenericEntity.tag_update
    )

    def dependencies(self):
        return [
            self.sketch,
        ]

    def tweak(self, solvesys, pos, group):
        wrkpln = self.sketch.wp
        u, v, _ = wrkpln.matrix_basis.inverted() @ pos

        self.create_slvs_data(solvesys, group=group)

        # NOTE: When simply initializing the point on the tweaking positions
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
        make_coincident(
            solvesys, self.py_data, edge, wrkpln.py_data, group, entity_type=SlvsLine2D
        )

    def draw_props(self, layout):
        sub = super().draw_props(layout)
        sub.prop(self, "co")
        return sub


def round_v(vec, ndigits=None):
    values = []
    for v in vec:
        values.append(round(v, ndigits=ndigits))
    return Vector(values)


class SlvsLine2D(SlvsGenericEntity, PropertyGroup, Entity2D):
    """Representation of a line in 2D space. Connects p1 and p2 and lies on the
    sketche's workplane.

    Arguments:
        p1 (SlvsPoint2D): Line's startpoint
        p2 (SlvsPoint2D): Line's endpoint
        sketch (SlvsSketch): The sketch this entity belongs to
    """

    @classmethod
    def is_line(cls):
        return True

    def dependencies(self):
        return [self.p1, self.p2, self.sketch]

    def is_dashed(self):
        return self.construction

    def update(self):
        if bpy.app.background:
            return

        p1, p2 = self.p1.location, self.p2.location
        coords = (p1, p2)

        kwargs = {"pos": coords}
        self._batch = batch_for_shader(self._shader, "LINES", kwargs)
        self.is_dirty = False

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
        startpoint.handle_right_type = "VECTOR"
        endpoint.handle_left = locations[1]
        endpoint.handle_left_type = "VECTOR"

        return endpoint

    def midpoint(self):
        return (self.p1.co + self.p2.co) / 2

    def direction_vec(self):
        return (self.p2.co - self.p1.co).normalized()

    @property
    def length(self):
        return (self.p2.co - self.p1.co).length

    def overlaps_endpoint(self, co):
        precision = 5
        co_rounded = round_v(co, ndigits=precision)
        if any(
            [
                co_rounded == round_v(v, ndigits=precision)
                for v in (self.p1.co, self.p2.co)
            ]
        ):
            return True
        return False

    def intersect(self, other):
        # NOTE: There can be multiple intersections when intersecting with one or more curves
        def parse_retval(value):
            if not value:
                return ()
            if self.overlaps_endpoint(value) or other.overlaps_endpoint(value):
                return ()
            return (value,)

        if other.is_line():
            return parse_retval(
                intersect_line_line_2d(self.p1.co, self.p2.co, other.p1.co, other.p2.co)
            )
        else:
            return other.intersect(self)

    def replace(self, context, p1, p2, use_self=False):
        # Replace entity by a similar entity with the connection points p1, and p2
        # This is used for trimming, points are expected to lie somewhere on the existing entity
        if use_self:
            self.p1 = p1
            self.p2 = p2
            return self

        sse = context.scene.sketcher.entities
        sketch = context.scene.sketcher.active_sketch
        line = sse.add_line_2d(p1, p2, sketch,)
        line.construction = self.construction
        return line

    def distance_along_segment(self, p1, p2):
        start, end = self.p1.co, self.p2.co
        len_1 = (p1 - end).length
        len_2 = (p2 - start).length

        threshold = 0.0000001
        retval = (len_1 + len_2) % (self.length + threshold)

        return retval


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
        self.is_dirty = False

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
    p2 to p3 or (vice-versa if the option invert_direction is true) with a
    circle segment that is resolution independent. The arc lies on the sketche's workplane.

    Arguments:
        p1 (SlvsPoint2D): Arc's centerpoint
        p2 (SlvsPoint2D): Arc's startpoint
        p2 (SlvsPoint2D): Arc's endpoint
        nm (SlvsNormal3D): Orientation
        sketch (SlvsSketch): The sketch this entity belongs to
    """

    invert_direction: BoolProperty(
        name="Invert direction",
        description="Connect the points in the inverted order",
        update=tag_update,
    )

    @classmethod
    def is_curve(cls):
        return True

    @property
    def start(self):
        return self.p2 if self.invert_direction else self.p1

    @property
    def end(self):
        return self.p1 if self.invert_direction else self.p2

    def dependencies(self):
        return [self.nm, self.ct, self.start, self.end, self.sketch]

    def is_dashed(self):
        return self.construction

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

        kwargs = {"pos": coords}
        self._batch = batch_for_shader(self._shader, "LINE_STRIP", kwargs)
        self.is_dirty = False

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
        """Returns an angle in radians from zero to 2*PI"""
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
        sub = super().draw_props(layout)
        sub.prop(self, "invert_direction")
        return sub

    def is_inside(self, coords):
        # Checks if a position is inside the arcs angle range
        ct = self.ct.co
        p = coords - ct
        p1 = self.start.co - ct
        p2 = self.end.co - ct

        x_axis = Vector((1, 0))

        # angle_signed interprets clockwise as positive, so invert..
        a1 = functions.range_2pi(p.angle_signed(p1))
        a2 = functions.range_2pi(p2.angle_signed(p))

        angle = self.angle

        if not p.length or not p1.length or not p2.length:
            return False

        if a1 < angle > a2:
            return True
        return False

    def overlaps_endpoint(self, co):
        precision = 5
        co_rounded = round_v(co, ndigits=precision)
        if any(
            [
                co_rounded == round_v(v, ndigits=precision)
                for v in (self.p1.co, self.p2.co)
            ]
        ):
            return True
        return False

    def intersect(self, other):
        def parse_retval(retval):
            # Intersect might return None, (value, value) or (value, None)
            values = []
            if hasattr(retval, "__len__"):
                for val in retval:
                    if val is None:
                        continue
                    if not self.is_inside(val):
                        continue
                    if isinstance(other, SlvsArc) and not other.is_inside(val):
                        continue
                    if self.overlaps_endpoint(val) or other.overlaps_endpoint(val):
                        continue

                    values.append(val)
            elif retval is not None:
                if self.overlaps_endpoint(retval) or other.overlaps_endpoint(retval):
                    return ()
                values.append(retval)

            return tuple(values)

        if other.is_line():
            return parse_retval(
                intersect_line_sphere_2d(
                    other.p1.co, other.p2.co, self.ct.co, self.radius
                )
            )
        elif other.is_curve():
            return parse_retval(
                intersect_sphere_sphere_2d(
                    self.ct.co, self.radius, other.ct.co, other.radius
                )
            )

    def distance_along_segment(self, p1, p2):
        ct = self.ct.co
        start, end = self.start.co - ct, self.end.co - ct
        points = (p1, p2) if self.invert_direction else (p2, p1)

        len_1 = functions.range_2pi(end.angle_signed(points[1] - ct))
        len_2 = functions.range_2pi((points[0] - ct).angle_signed(start))

        threshold = 0.000001
        retval = (len_1 + len_2) % (self.angle + threshold)

        return retval

    def replace(self, context, p1, p2, use_self=False):
        if use_self:
            self.p1 = p1
            self.p2 = p2
            return self

        sketch = context.scene.sketcher.active_sketch
        arc = context.scene.sketcher.entities.add_arc(
            sketch.wp.nm, self.ct, p1, p2, sketch
        )
        arc.construction = self.construction
        arc.invert_direction = self.invert_direction
        return arc


slvs_entity_pointer(SlvsArc, "nm")
slvs_entity_pointer(SlvsArc, "ct")
slvs_entity_pointer(SlvsArc, "p1")
slvs_entity_pointer(SlvsArc, "p2")
slvs_entity_pointer(SlvsArc, "sketch")


class SlvsCircle(SlvsGenericEntity, PropertyGroup, Entity2D):
    """Representation of a circle in 2D space. The circle is centered at ct with
    it's size defined by the radius and is resoulution independent.

    Arguments:
        ct (SlvsPoint2D): Circle's centerpoint
        radius (FloatProperty): The radius of the circle
        nm (SlvsNormal2D):
        sketch (SlvsSketch): The sketch this entity belongs to
    """

    radius: FloatProperty(
        name="Radius",
        description="The radius of the circle",
        subtype="DISTANCE",
        min=0.0,
        unit="LENGTH",
        update=tag_update,
    )

    @classmethod
    def is_curve(cls):
        return True

    def dependencies(self):
        return [self.nm, self.ct, self.sketch]

    def is_dashed(self):
        return self.construction

    def update(self):
        if bpy.app.background:
            return

        coords = functions.coords_arc_2d(0, 0, self.radius, CURVE_RESOLUTION)

        u, v = self.ct.co

        mat_local = Matrix.Translation(Vector((u, v, 0)))
        mat = self.wp.matrix_basis @ mat_local
        coords = [(mat @ Vector((*co, 0)))[:] for co in coords]

        kwargs = {"pos": coords}
        self._batch = batch_for_shader(self._shader, "LINE_STRIP", kwargs)
        self.is_dirty = False

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

    @classmethod
    def is_closed(cls):
        return True

    def connection_points(self):
        # NOTE: it should probably be possible to lookup coincident points on circle
        return []

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

    def overlaps_endpoint(self, co):
        return False

    def intersect(self, other):
        def parse_retval(retval):
            # Intersect might return None, (value, value) or (value, None)
            values = []
            if hasattr(retval, "__len__"):
                for val in retval:
                    if val is None:
                        continue
                    if other.overlaps_endpoint(val):
                        continue
                    values.append(val)
            elif retval is not None:
                if other.overlaps_endpoint(retval):
                    return ()
                values.append(retval)

            return tuple(values)

        if other.is_line():
            return parse_retval(
                intersect_line_sphere_2d(
                    other.p1.co, other.p2.co, self.ct.co, self.radius
                )
            )
        elif isinstance(other, SlvsCircle):
            return parse_retval(
                intersect_sphere_sphere_2d(
                    self.ct.co, self.radius, other.ct.co, other.radius
                )
            )
        else:
            return other.intersect(self)

    def replace(self, context, p1, p2, use_self=False):
        if use_self:
            self.p1 = p1
            self.p2 = p2
            return self

        sketch = context.scene.sketcher.active_sketch
        arc = context.scene.sketcher.entities.add_arc(
            sketch.wp.nm, self.ct, p1, p2, sketch
        )
        arc.construction = self.construction
        return arc

    def distance_along_segment(self, p1, p2):
        ct = self.ct.co
        start, end = p1 - ct, p2 - ct
        angle = functions.range_2pi(math.atan2(*end.yx) - math.atan2(*start.yx))
        retval = self.radius * angle
        return retval


slvs_entity_pointer(SlvsCircle, "nm")
slvs_entity_pointer(SlvsCircle, "ct")
slvs_entity_pointer(SlvsCircle, "sketch")


def update_pointers(scene, index_old, index_new):
    """Replaces all references to an entity index with it's new index"""
    logger.debug("Update references {} -> {}".format(index_old, index_new))
    # NOTE: this should go through all entity pointers and update them if necessary.
    # It might be possible to use the msgbus to notify and update the IntProperty pointers

    if scene.sketcher.active_sketch_i == index_old:
        logger.debug(
            "Update reference {} of {} to {}: ".format(
                "active_sketch", scene.sketcher, index_new
            )
        )
        scene.sketcher.active_sketch_i = index_new

    for o in scene.sketcher.all:
        if not hasattr(o, "update_pointers"):
            continue
        o.update_pointers(index_old, index_new)

    scene.sketcher.purge_stale_data()


class SlvsEntities(PropertyGroup):
    """Holds all Solvespace Entities"""
    # NOTE: currently limited to 16 items!
    # See _set_index to see how their index is handled
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

    _entity_collections = (
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

    # __annotations__ = {
    #         list_name : CollectionProperty(type=entity_cls) for entity_cls, list_name in zip(entities, _entity_collections)
    # }
    
    @classmethod
    def _type_index(cls, entity: SlvsGenericEntity) -> int:
        return cls.entities.index(type(entity))

    def _set_index(self, entity: SlvsGenericEntity):
        """Create an index for the entity and assign it.
        Index breakdown

        | entity type index |  entity object index  |
        |:-----------------:|:---------------------:|
        |      4 bits       |       20 bits         | 
        |            total: 3 Bytes                 |
        """
        type_index = self._type_index(entity)
        sub_list = getattr(self, self._entity_collections[type_index])

        local_index = len(sub_list) - 1
        # TODO: handle this case better
        assert local_index < math.pow(2, 20)
        entity.slvs_index = type_index << 20 | local_index

    @staticmethod
    def _breakdown_index(index: int):
        return functions.breakdown_index(index)

    @classmethod
    def recalc_type_index(cls, entity):
        _, local_index = cls._breakdown_index(entity.slvs_index)
        type_index = cls._type_index(entity)
        entity.slvs_index = type_index << 20 | local_index

    def type_from_index(self, index: int) -> Type[SlvsGenericEntity]:
        if index < 0:
            return None

        type_index, _ = self._breakdown_index(index)

        if type_index >= len(self.entities):
            return None
        return self.entities[type_index]

    def _get_list_and_index(self, index: int):
        type_index, local_index = self._breakdown_index(index)
        if type_index < 0 or type_index >= len(self._entity_collections):
            return None, local_index
        return getattr(self, self._entity_collections[type_index]), local_index

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

        if self.get(index).origin:
            return

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
        update_pointers(bpy.context.scene, new_item.slvs_index, index)
        new_item.slvs_index = index

    def add_point_3d(
        self, co: Union[Tuple[float, float, float], Vector]
    ) -> SlvsPoint3D:
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
        return nm

    def add_workplane(self, p1: SlvsPoint3D, nm: SlvsGenericEntity) -> SlvsWorkplane:
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
        return p

    def add_line_2d(
        self, p1: SlvsPoint2D, p2: SlvsPoint2D, sketch: SlvsSketch
    ) -> SlvsLine2D:
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
        return nm

    def add_arc(
        self,
        nm: SlvsNormal2D,
        ct: SlvsPoint2D,
        p1: SlvsPoint2D,
        p2: SlvsPoint2D,
        sketch: SlvsSketch,
    ) -> SlvsArc:
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
        return arc

    def add_circle(
        self, nm: SlvsNormal2D, ct: SlvsPoint2D, radius: float, sketch: SlvsSketch
    ) -> SlvsCircle:
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
        return c

    @property
    def all(self):
        for coll_name in self._entity_collections:
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
        pi_2 = math.pi / 2
        for name, angles in zip(
            ("origin_axis_X", "origin_axis_Y", "origin_axis_Z"),
            (Euler((pi_2, 0.0, pi_2)), Euler((pi_2, 0.0, 0.0)), Euler()),
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
for entity_cls, list_name in zip(SlvsEntities.entities, SlvsEntities._entity_collections):
    SlvsEntities.__annotations__[list_name] = CollectionProperty(type=entity_cls)


slvs_entity_pointer(SlvsEntities, "origin")
slvs_entity_pointer(SlvsEntities, "origin_axis_X")
slvs_entity_pointer(SlvsEntities, "origin_axis_Y")
slvs_entity_pointer(SlvsEntities, "origin_axis_Z")
slvs_entity_pointer(SlvsEntities, "origin_plane_XY")
slvs_entity_pointer(SlvsEntities, "origin_plane_XZ")
slvs_entity_pointer(SlvsEntities, "origin_plane_YZ")


### Constraints

point_3d = (SlvsPoint3D,)
point_2d = (SlvsPoint2D,)
normal_3d = (SlvsNormal3D,)
point = (*point_3d, *point_2d)
line = (SlvsLine3D, SlvsLine2D)
curve = (SlvsCircle, SlvsArc)
segment = (*line, *curve)

ENTITY_PROP_NAMES = ("entity1", "entity2", "entity3", "entity4")


class GenericConstraint:
    failed: BoolProperty(name="Failed")
    visible: BoolProperty(name="Visible", default=True, update=functions.update_cb)
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

    def update_system_cb(self, context):
        """Update scene and re-run the solver.
        NOTE: Should be a staticmethod if it wasn't a callback."""
        sketch = context.scene.sketcher.active_sketch
        solve_system(context, sketch=sketch)

    # TODO: avoid duplicating code
    def update_pointers(self, index_old, index_new):
        def _update(name):
            prop = getattr(self, name)
            if prop == index_old:
                logger.debug(
                    "Update reference {} of {} to {}: ".format(name, self, index_new)
                )
                setattr(self, name, index_new)

        if hasattr(self, "sketch_i"):
            _update("sketch_i")

        for prop_name in dir(self):
            if not prop_name.startswith("entity") or not prop_name.endswith("_i"):
                continue
            _update(prop_name)

    def is_visible(self, context):
        if hasattr(self, "sketch"):
            return self.sketch.is_visible(context) and self.visible
        return self.visible

    def is_active(self, active_sketch):
        if not hasattr(self, "sketch"):
            return not active_sketch

        show_inactive = not functions.get_prefs().hide_inactive_constraints
        if show_inactive and self.is_visible():
            return True

        return self.sketch == active_sketch

    def draw_plane(self):
        if self.sketch_i != -1:
            wp = self.sketch.wp
            return wp.p1.location, wp.normal
        # TODO: return drawing plane for constraints in 3d
        return None, None

    def copy(self, context, entities):
        # copy itself to another set of entities
        c = context.scene.sketcher.constraints.new_from_type(self.type)
        if hasattr(self, "sketch"):
            c.sketch = self.sketch
        if hasattr(self, "setting"):
            c.setting = self.setting
        if hasattr(self, "value"):
            c.value = self.value

        for prop, e in zip(ENTITY_PROP_NAMES, entities):
            setattr(c, prop, e)

        return c

    def draw_props(self, layout: UILayout):
        is_experimental = preferences.is_experimental()

        layout.label(text="Type: " + type(self).__name__)

        if self.failed:
            layout.label(text="Failed", icon="ERROR")

        # Info block
        layout.separator()
        if is_experimental:
            sub = layout.column()
            sub.scale_y = 0.8
            sub.label(text="Dependencies:")
            for e in self.dependencies():
                sub.label(text=str(e))

        # General props
        layout.separator()
        layout.prop(self, "visible")

        # Specific props
        layout.separator()
        sub = layout.column()

        # Delete
        layout.separator()
        props = layout.operator(Operators.DeleteConstraint, icon='X')
        props.type = self.type
        props.index = self.index()

        return sub

    def index(self):
        """Return elements index inside its collection"""
        # HACK: Elements of collectionproperties currently don't expose an index
        # method, path_from_id writes the index however, use this hack instead
        # of looping over elements
        return int(self.path_from_id().split('[')[1].split(']')[0])


# NOTE: When tweaking it's necessary to constrain a point that is only temporary available
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


line_arc_circle = (*line, *curve)


class SlvsEqual(GenericConstraint, PropertyGroup):
    """Forces two lengths, or radiuses to be equal.

    If a line and an arc of a circle are selected, then the length of the line is
    forced equal to the length (not the radius) of the arc.
    """

    # TODO: Also supports equal angle

    type = "EQUAL"
    label = "Equal"
    signature = (line_arc_circle, line_arc_circle)

    @classmethod
    def get_types(cls, index, entities):
        e = entities[1] if index == 0 else entities[0]
        if e:
            if type(e) in (SlvsLine2D, SlvsArc):
                return (SlvsLine2D, SlvsArc)
            elif type(e) == SlvsCircle:
                return curve
            return (type(e),)
        return cls.signature[index]

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


def get_side_of_line(line_start, line_end, point):
    line_end = line_end - line_start
    point = point - line_start
    return -(
        (line_end.x - line_start.x) * (point.y - line_start.y)
        - (line_end.y - line_start.y) * (point.x - line_start.x)
    )


align_items = [
    ("NONE", "None", "", 0),
    ("HORIZONTAL", "Horizontal", "", 1),
    ("VERTICAL", "Vertical", "", 2),
]


class SlvsDistance(GenericConstraint, PropertyGroup):
    """Sets the distance between a point and some other entity (point/line/Workplane).
    """

    def get_distance_value(self):
        return self.get('value', self.rna_type.properties['value'].default)

    def set_distance_value(self, value):
        self['value'] = abs(value)

    label = "Distance"
    value: FloatProperty(
        name=label,
        subtype="DISTANCE",
        unit="LENGTH",
        update=GenericConstraint.update_system_cb,
        get=get_distance_value,
        set=set_distance_value,
    )
    flip: BoolProperty(name="Flip", update=GenericConstraint.update_system_cb)
    align: EnumProperty(name="Align", items=align_items, update=GenericConstraint.update_system_cb,)
    draw_offset: FloatProperty(name="Draw Offset", default=0.3)
    draw_outset: FloatProperty(name="Draw Outset", default=0.0)
    type = "DISTANCE"
    signature = ((*point, *line), (*point, *line, SlvsWorkplane))

    @classmethod
    def get_types(cls, index, entities):
        e = entities[1] if index == 0 else entities[0]

        if e:
            if index == 1 and e.is_line():
                # Allow constraining a single line
                return None
            if e.is_3d():
                return ((SlvsPoint3D, ), (SlvsPoint3D, SlvsLine3D, SlvsWorkplane))[index]
            return (point_2d, (*point_2d, SlvsLine2D))[index]
        return cls.signature[index]

    def needs_wp(self):
        if isinstance(self.entity2, SlvsWorkplane):
            return WpReq.FREE
        return WpReq.OPTIONAL

    def use_flipping(self):
        # Only use flipping for constraint between point and line/workplane
        return type(self.entity2) in (*line, SlvsWorkplane)

    def use_align(self):
        if type(self.entity2) in (*line, SlvsWorkplane):
            return False
        return True

    def get_value(self):
        value = self.value
        if self.use_flipping() and self.flip:
            return value * -1
        return value

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        if self.entity1 == self.entity2:
            raise AttributeError("Cannot create constraint between one entity itself")

        e1, e2 = self.entity1, self.entity2
        if e1.is_line():
            e1, e2 = e1.p1, e1.p2

        func = None
        set_wp = False
        alignment = self.align
        align = self.use_align() and alignment != "NONE"
        handles = []

        value = self.get_value()

        if type(e2) in line:
            func = solvesys.addPointLineDistance
            set_wp = True
        elif isinstance(e2, SlvsWorkplane):
            func = solvesys.addPointPlaneDistance
        elif type(e2) in point:
            if align and all([e.is_2d() for e in (e1, e2)]):
                # Get Point in between
                p1, p2 = e1.co, e2.co
                coords = (p2.x, p1.y)

                params = [solvesys.addParamV(v, group) for v in coords]
                wp = self.get_workplane()
                p = solvesys.addPoint2d(wp, *params, group=group)

                handles.append(
                    solvesys.addPointsHorizontal(p, e2.py_data, wp, group=group)
                )
                handles.append(
                    solvesys.addPointsVertical(p, e1.py_data, wp, group=group)
                )

                base_point = e1 if alignment == "VERTICAL" else e2
                handles.append(
                    solvesys.addPointsDistance(
                        value, p, base_point.py_data, wrkpln=wp, group=group
                    )
                )
                return handles
            else:
                func = solvesys.addPointsDistance
            set_wp = True

        kwargs = {
            "group": group,
        }

        if set_wp:
            kwargs["wrkpln"] = self.get_workplane()

        return func(value, e1.py_data, e2.py_data, **kwargs)

    def matrix_basis(self):
        if self.sketch_i == -1 or not self.entity1.is_2d():
            # TODO: Support distance in 3d
            return Matrix()

        e1, e2 = self.entity1, self.entity2
        if e1.is_line():
            e1, e2 = e1.p1, e1.p2

        sketch = self.sketch
        x_axis = Vector((1, 0))
        alignment = self.align
        align = alignment != "NONE"

        if type(e2) in point_2d:
            p1, p2 = e1.co, e2.co
            if align:
                v_rotation = (
                    Vector((1.0, 0.0))
                    if alignment == "HORIZONTAL"
                    else Vector((0.0, 1.0))
                )
            else:
                v_rotation = p2 - p1
            v_translation = (p2 + p1) / 2

            angle = v_rotation.angle_signed(x_axis)
            mat_rot = Matrix.Rotation(angle, 2, "Z")

        elif isinstance(e2, SlvsLine2D):
            line = e2
            orig = line.p1.co
            end = line.p2.co - orig
            angle = functions.range_2pi(math.atan2(end[1], end[0])) + math.pi / 2

            mat_rot = Matrix.Rotation(angle, 2, "Z")
            p1 = e1.co - orig
            v_translation = (p1 + p1.project(end)) / 2 + orig

        mat_local = Matrix.Translation(v_translation.to_3d()) @ mat_rot.to_4x4()
        return sketch.wp.matrix_basis @ mat_local

    def init_props(self, **kwargs):
        # Set initial distance value to the current spacing
        e1, e2 = self.entity1, self.entity2
        if e1.is_line():
            value = e1.length
        elif isinstance(e2, SlvsWorkplane):
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
                value, get_side_of_line(e2.p1.location, e2.p2.location, e1.location),
            )
        else:
            value = (e1.location - e2.location).length

        if self.use_flipping() and value < 0:
            value = abs(value)
            self.flip = not self.flip

        self.value = value
        return value, None

    def text_inside(self, ui_scale):
        return (ui_scale * abs(self.draw_outset)) < self.value / 2

    def update_draw_offset(self, pos, ui_scale):
        self.draw_offset = pos[1] / ui_scale
        self.draw_outset = pos[0] / ui_scale

    def draw_props(self, layout):
        sub = super().draw_props(layout)

        sub.prop(self, "value")

        row = sub.row()
        row.active = self.use_flipping()
        row.prop(self, "flip")

        sub.label(text="Alignment:")
        row = sub.row()
        row.active = self.use_align()
        row.prop(self, "align", text="")

        if preferences.is_experimental():
            sub.prop(self, "draw_offset")

        return sub

    def value_placement(self, context):
        """location to display the constraint value"""
        region = context.region
        rv3d = context.space_data.region_3d
        ui_scale = context.preferences.system.ui_scale

        offset = ui_scale * self.draw_offset
        outset = ui_scale * self.draw_outset
        coords = self.matrix_basis() @ Vector((outset, offset, 0))
        return location_3d_to_region_2d(region, rv3d, coords)


slvs_entity_pointer(SlvsDistance, "entity1")
slvs_entity_pointer(SlvsDistance, "entity2")
slvs_entity_pointer(SlvsDistance, "sketch")


class SlvsDiameter(GenericConstraint, PropertyGroup):
    """ Sets the diameter of an arc or a circle. """

    def use_radius_getter(self):
        return self.get("setting", self.bl_rna.properties["setting"].default)

    def use_radius_setter(self, setting):
        old_setting = self.get("setting", self.bl_rna.properties["setting"].default)
        self["setting"] = setting

        distance = None
        if old_setting and not setting:
            distance = self.value * 2
        elif not old_setting and setting:
            distance = self.value / 2

        if distance is not None:
            # Avoid triggering the property's update callback
            self["value"] = distance

    label = "Diameter"
    value: FloatProperty(
        name="Size", subtype="DISTANCE", unit="LENGTH", update=GenericConstraint.update_system_cb
    )
    setting: BoolProperty(
        name="Use Radius", get=use_radius_getter, set=use_radius_setter
    )
    leader_angle: FloatProperty(name="Leader Angle", default=45, subtype="ANGLE")
    draw_offset: FloatProperty(name="Draw Offset", default=0)
    type = "DIAMETER"
    signature = (curve,)

    @property
    def diameter(self):
        value = self.value
        if self.setting:
            return value * 2
        return value

    @property
    def radius(self):
        value = self.value
        if self.setting:
            return value
        return value / 2

    def needs_wp(self):
        return WpReq.OPTIONAL

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        return solvesys.addDiameter(self.diameter, self.entity1.py_data, group=group)

    def init_props(self, **kwargs):
        # Get operators setting value
        setting = kwargs.get("setting")

        value = self.entity1.radius
        if setting is None and self.entity1.bl_rna.name == "SlvsArc":
            self["setting"] = True

        if not setting:
            value = value * 2

        return value, None

    def matrix_basis(self):
        if self.sketch_i == -1:
            return Matrix()
        sketch = self.sketch
        origin = self.entity1.ct.co
        rotation = functions.range_2pi(math.radians(self.leader_angle))
        mat_local = Matrix.Translation(origin.to_3d())
        return sketch.wp.matrix_basis @ mat_local

    def text_inside(self):
        return self.draw_offset < self.radius

    def update_draw_offset(self, pos, ui_scale):
        self.draw_offset = pos.length
        self.leader_angle = math.atan2(pos.y, pos.x)

    def draw_props(self, layout):
        sub = super().draw_props(layout)

        sub.prop(self, "value")

        row = sub.row()
        row.prop(self, "setting")
        return sub

    def value_placement(self, context):
        """location to display the constraint value"""
        region = context.region
        rv3d = context.space_data.region_3d
        offset = self.draw_offset
        coords = functions.pol2cart(offset, self.leader_angle)
        coords2 = self.matrix_basis() @ Vector((coords[0], coords[1], 0.0))
        return location_3d_to_region_2d(region, rv3d, coords2)


slvs_entity_pointer(SlvsDiameter, "entity1")
slvs_entity_pointer(SlvsDiameter, "sketch")


class SlvsAngle(GenericConstraint, PropertyGroup):
    """Sets the angle between two lines, applies in 2D only.

    The constraint's setting can be used to to constrain the supplementary angle.
    """

    def invert_angle_getter(self):
        return self.get("setting", self.bl_rna.properties["setting"].default)

    def invert_angle_setter(self, setting):
        self["value"] = math.pi - self.value
        self["setting"] = setting

    label = "Angle"
    value: FloatProperty(
        name=label, subtype="ANGLE", unit="ROTATION", update=GenericConstraint.update_system_cb
    )
    setting: BoolProperty(name="Measure supplementary angle", get=invert_angle_getter, set=invert_angle_setter)
    draw_offset: FloatProperty(name="Draw Offset", default=1)
    draw_outset: FloatProperty(name="Draw Outset", default=0)
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

    def init_props(self, **kwargs):
        '''
        initializes value (angle, in radians),
            setting ("measure supplimentary angle")
            and distance to dimension text (draw_offset)
        '''

        line1, line2 = self.entity1, self.entity2
        vec1, vec2 = line1.direction_vec(), line2.direction_vec()
        angle = self._get_angle(vec1, vec2)
        setting = angle > 90
        if not setting:
            angle = 180 - angle

        origin = functions.get_line_intersection(
            *functions.line_abc_form(line1.p1.co, line1.p2.co),
            *functions.line_abc_form(line2.p1.co, line2.p2.co),
        )
        dist = max(
            (line1.midpoint() - origin).length,
            (line2.midpoint() - origin).length,
            0.5
        )
        self.draw_offset = dist if not setting else -dist
        return math.radians(angle), setting

    def text_inside(self):
        return abs(self.draw_outset) < (self.value/2)

    def update_draw_offset(self, pos, ui_scale):
        self.draw_offset = math.copysign(pos.length / ui_scale, pos.x)
        self.draw_outset = math.atan(pos.y / pos.x)

    def draw_props(self, layout):
        sub = super().draw_props(layout)
        sub.prop(self, "value")
        sub.prop(self, "setting")
        return sub

    def value_placement(self, context):
        """location to display the constraint value"""
        region = context.region
        rv3d = context.space_data.region_3d
        ui_scale = context.preferences.system.ui_scale

        offset = ui_scale * self.draw_offset
        outset = self.draw_outset
        co = pol2cart(offset, outset)
        coords = self.matrix_basis() @ Vector((co[0], co[1], 0))
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
    signature = ((SlvsLine2D, SlvsPoint2D), (SlvsPoint2D,))

    @classmethod
    def get_types(cls, index, entities):
        if index == 1:
            # return None if first entity is line
            if entities[0] and entities[0].is_line():
                return None

        return cls.signature[index]

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        wp = self.get_workplane()
        if self.entity1.is_point():
            return solvesys.addPointsHorizontal(
                self.entity1.py_data, self.entity2.py_data, wp, group=group
            )
        return solvesys.addLineHorizontal(
            self.entity1.py_data, wrkpln=wp, group=group
        )


slvs_entity_pointer(SlvsHorizontal, "entity1")
slvs_entity_pointer(SlvsHorizontal, "entity2")
slvs_entity_pointer(SlvsHorizontal, "sketch")


class SlvsVertical(GenericConstraint, PropertyGroup):
    """Forces a line segment to be vertical. It applies in 2D Space only because
    the meaning of horizontal or vertical is defined by the workplane.
    """

    type = "VERTICAL"
    label = "Vertical"
    signature = ((SlvsLine2D, SlvsPoint2D), (SlvsPoint2D,))

    @classmethod
    def get_types(cls, index, entities):
        if index == 1:
            # return None if first entity is line
            if entities[0] and entities[0].is_line():
                return None

        return cls.signature[index]

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        wp = self.get_workplane()
        if self.entity1.is_point():
            return solvesys.addPointsVertical(
                self.entity1.py_data, self.entity2.py_data, wp, group=group
            )
        return solvesys.addLineVertical(
            self.entity1.py_data, wrkpln=wp, group=group
        )


slvs_entity_pointer(SlvsVertical, "entity1")
slvs_entity_pointer(SlvsVertical, "entity2")
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
    return []


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
                    e1.direction(point), e1.py_data, e2.py_data, group=group,
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
        kwargs = {
            "group": group,
        }

        wp = self.get_workplane()
        if wp:
            kwargs["wrkpln"] = wp

        return solvesys.addMidPoint(
            self.entity1.py_data, self.entity2.py_data, **kwargs,
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
                e1.py_data, e2.py_data, e3.py_data, self.get_workplane(), group=group,
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
        name=label, subtype="UNSIGNED", update=GenericConstraint.update_system_cb, min=0.0
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
            self.value, e1.py_data, e2.py_data, self.get_workplane(), group=group,
        )

    def init_props(self, **kwargs):
        line1, line2 = self.entity1, self.entity2

        value = line1.length / line2.length
        return value, None

    def draw_props(self, layout):
        sub = super().draw_props(layout)
        sub.prop(self, "value")
        return sub


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


class SlvsConstraints(PropertyGroup):

    _constraints = (
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

    __annotations__ = {
        cls.type.lower(): CollectionProperty(type=cls) for cls in _constraints
    }

    @classmethod
    def cls_from_type(cls, type: str):
        for constraint in cls._constraints:
            if type == constraint.type:
                return constraint
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

    def get_list(self, type: str):
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

    def add_coincident(
        self,
        entity1: SlvsGenericEntity,
        entity2: SlvsGenericEntity,
        sketch: SlvsSketch = None,
    ) -> SlvsCoincident:
        """Add a coincident constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.

        Returns:
            SlvsCoincident: The created constraint.
        """

        if all([type(e) in point for e in (entity1, entity2)]):
            # TODO: Implicitly merge points
            return

        c = self.coincident.add()
        c.entity1 = entity1
        c.entity2 = entity2
        if sketch:
            c.sketch = sketch
        return c

    def add_equal(
        self,
        entity1: SlvsGenericEntity,
        entity2: SlvsGenericEntity,
        sketch: Union[SlvsSketch, None] = None,
    ) -> SlvsEqual:
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
        if sketch is not None:
            c.sketch = sketch
        return c

    def add_distance(
        self,
        entity1: SlvsGenericEntity,
        entity2: SlvsGenericEntity,
        sketch: Union[SlvsSketch, None] = None,
        init: bool = False,
    ) -> SlvsDistance:
        """Add a distance constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.
            init: Initialize the constraint based on the given entities.

        Returns:
            SlvsDistance: The created constraint.
        """
        c = self.distance.add()
        c.entity1 = entity1
        c.entity2 = entity2
        if sketch is not None:
            c.sketch = sketch
        if init:
            c.init_props()
        return c

    def add_angle(
        self,
        entity1: SlvsGenericEntity,
        entity2: SlvsGenericEntity,
        sketch: SlvsSketch = None,
        init: bool = False,
    ) -> SlvsAngle:
        """Add an angle constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.
            init: Initialize the constraint based on the given entities.

        Returns:
            SlvsAngle: The created constraint.
        """
        c = self.angle.add()
        c.entity1 = entity1
        c.entity2 = entity2
        if sketch is not None:
            c.sketch = sketch
        if init:
            c.init_props()
        return c

    def add_diameter(
        self, entity1: SlvsGenericEntity, sketch: SlvsSketch = None, init: bool = False
    ) -> SlvsDiameter:
        """Add a diameter constraint.

        Arguments:
            entity1: -
            sketch: The sketch this constraint belongs to.
            init: Initialize the constraint based on the given entities.

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

    def add_parallel(
        self,
        entity1: SlvsGenericEntity,
        entity2: SlvsGenericEntity,
        sketch: Union[SlvsSketch, None] = None,
    ) -> SlvsParallel:
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
        if sketch is not None:
            c.sketch = sketch
        return c

    def add_horizontal(
        self, entity1: SlvsGenericEntity, sketch: Union[SlvsSketch, None] = None
    ) -> SlvsHorizontal:
        """Add a horizontal constraint.

        Arguments:
            entity1: -
            sketch: The sketch this constraint belongs to.

        Returns:
            SlvsHorizontal: The created constraint.
        """
        c = self.horizontal.add()
        c.entity1 = entity1
        if sketch is not None:
            c.sketch = sketch
        return c

    def add_vertical(
        self, entity1: SlvsGenericEntity, sketch: Union[SlvsSketch, None] = None
    ) -> SlvsVertical:
        """Add a vertical constraint.

        Arguments:
            entity1: -
            sketch: The sketch this constraint belongs to.

        Returns:
            SlvsVertical: The created constraint.
        """
        c = self.vertical.add()
        c.entity1 = entity1
        if sketch is not None:
            c.sketch = sketch
        return c

    def add_tangent(
        self,
        entity1: SlvsGenericEntity,
        entity2: SlvsGenericEntity,
        sketch: Union[SlvsSketch, None] = None,
    ) -> SlvsTangent:
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
        if sketch is not None:
            c.sketch = sketch
        return c

    def add_midpoint(
        self,
        entity1: SlvsGenericEntity,
        entity2: SlvsGenericEntity,
        sketch: Union[SlvsSketch, None] = None,
    ) -> SlvsMidpoint:
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
        if sketch is not None:
            c.sketch = sketch
        return c

    def add_perpendicular(
        self,
        entity1: SlvsGenericEntity,
        entity2: SlvsGenericEntity,
        sketch: Union[SlvsSketch, None] = None,
    ) -> SlvsPerpendicular:
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
        if sketch is not None:
            c.sketch = sketch
        return c

    def add_ratio(
        self,
        entity1: SlvsGenericEntity,
        entity2: SlvsGenericEntity,
        sketch: Union[SlvsSketch, None] = None,
        init: bool = False,
    ) -> SlvsRatio:
        """Add a ratio constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.
            init: Initialize the constraint based on the given entities.

        Returns:
            SlvsRatio: The created constraint.
        """
        c = self.ratio.add()
        c.entity1 = entity1
        c.entity2 = entity2
        if sketch is not None:
            c.sketch = sketch
        if init:
            c.init_props()
        return c


for cls in SlvsConstraints._constraints:
    name = cls.type.lower()
    func_name = "add_" + name

    # Create constraint collections
    annotations = {}
    if hasattr(SlvsConstraints, "__annotations__"):
        annotations = SlvsConstraints.__annotations__.copy()


class SketcherProps(PropertyGroup):
    """The base structure for CAD Sketcher"""

    entities: PointerProperty(type=SlvsEntities)
    constraints: PointerProperty(type=SlvsConstraints)
    show_origin: BoolProperty(name="Show Origin Entities")
    selectable_constraints: BoolProperty(
        name="Constraints Selectability",
        default=True,
        options={"SKIP_SAVE"},
        update=functions.update_cb
    )

    version: IntVectorProperty(
        name="Addon Version",
        description="CAD Sketcher addon version this scene was saved with",
    )

    # This is needed for the sketches ui list
    ui_active_sketch: IntProperty()

    @property
    def all(self) -> Generator[Union[SlvsGenericEntity, SlvsConstraints], None, None]:
        """Iterate over entities and constraints of every type"""
        for entity in self.entities.all:
            yield entity
        for constraint in self.constraints.all:
            yield constraint

    def solve(self, context: Context):
        return solve_system(context)

    def purge_stale_data(self):
        global_data.hover = -1
        global_data.selected.clear()
        global_data.batches.clear()
        for e in self.entities.all:
            e.dirty = True


slvs_entity_pointer(SketcherProps, "active_sketch", update=functions.update_cb)


classes = (
    *SlvsEntities.entities,
    SlvsEntities,
    *SlvsConstraints._constraints,
    SlvsConstraints,
    SketcherProps,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.sketcher = PointerProperty(type=SketcherProps)
    bpy.types.Object.sketch_index = IntProperty(name="Parent Sketch", default=-1)


def unregister():
    del bpy.types.Object.sketch_index
    del bpy.types.Scene.sketcher

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
