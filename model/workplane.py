import logging
from typing import List

import bpy
import gpu
from mathutils import Vector, Matrix
from bpy.props import FloatProperty, StringProperty
from bpy.types import PropertyGroup
from gpu_extras.batch import batch_for_shader
from bpy.utils import register_classes_factory

from ..declarations import Operators
from .. import global_data
from ..utilities.draw import draw_rect_2d
from ..shaders import Shaders
from ..utilities import preferences
from ..solver import Solver
from .base_entity import SlvsGenericEntity
from .utilities import slvs_entity_pointer

logger = logging.getLogger(__name__)


class SlvsWorkplane(SlvsGenericEntity, PropertyGroup):
    """Representation of a plane which is defined by an origin point
    and a normal. Workplanes are used to define the position of 2D entities
    which only store the coordinates on the plane.

    Arguments:
        p1 (SlvsPoint3D): Origin Point of the Plane
        nm (SlvsNormal3D): Normal which defines the orientation
    """

    size = 0.4

    linked_wp_width: FloatProperty(
        name="Linked WP Width",
        description="Width of the linked-sketch workplane display (set to the source line length on creation).",
        default=0.0,
        min=0.0,
    )
    linked_wp_height: FloatProperty(
        name="Linked WP Height",
        description="Height of the linked-sketch workplane display. Updated on sketch leave to match the extreme point drawn (positive = upward, negative = downward). Falls back to the linked workplane width (square) when 0.",
        default=0.0,
    )
    linked_wp_center_x: FloatProperty(
        name="Linked WP Center X",
        description="Local X center for sketch workplane display bounds.",
        default=0.0,
    )
    linked_wp_center_y: FloatProperty(
        name="Linked WP Center Y",
        description="Local Y center for sketch workplane display bounds.",
        default=0.0,
    )
    tag: StringProperty(
        name="Tag",
        description="Workflow role of this workplane (e.g. Plan, Elevation)",
        default="",
    )

    def dependencies(self) -> List[SlvsGenericEntity]:
        return [self.p1, self.nm]

    @property
    def size(self):
        return preferences.get_prefs().workplane_size

    def _owner_sketch(self, context):
        scene = getattr(context, "scene", None)
        sketcher = getattr(scene, "sketcher", None)
        entities = getattr(sketcher, "entities", None)
        sketches = getattr(entities, "sketches", ())
        for sketch in sketches:
            if getattr(sketch, "wp", None) == self:
                return sketch
        return None

    def _uses_linked_layout(self, context):
        sketch = self._owner_sketch(context)
        return sketch is not None and getattr(sketch, "source_line_i", -1) != -1

    def _rect_coords(self, context):
        if self.linked_wp_width <= 0:
            return draw_rect_2d(0, 0, self.size, self.size)

        w = self.linked_wp_width
        h = self.linked_wp_height if self.linked_wp_height != 0 else w

        if self._uses_linked_layout(context):
            # Linked sketches use origin-anchored local coordinates.
            return draw_rect_2d(w / 2, h / 2, w, abs(h))

        # Regular sketches use a tight local-space bounding box center.
        return draw_rect_2d(self.linked_wp_center_x, self.linked_wp_center_y, w, abs(h))

    def update(self):
        if bpy.app.background:
            return

        p1, nm = self.p1, self.nm

        coords = self._rect_coords(bpy.context)
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
            gpu.matrix.multiply_matrix(self.matrix_basis)
            if self.linked_wp_width <= 0:
                scale = context.region_data.view_distance
                gpu.matrix.scale(Vector((scale, scale, scale)))

            col = self.color(context)
            # Let parent draw outline
            super().draw(context)

            # Additionally draw a face
            col_surface = col[:-1] + (0.2,)

            shader = Shaders.uniform_color_3d()
            shader.bind()
            gpu.state.blend_set("ALPHA")

            shader.uniform_float("color", col_surface)

            coords = self._rect_coords(context)
            coords = [Vector(co)[:] for co in coords]
            indices = ((0, 1, 2), (0, 2, 3))
            batch = batch_for_shader(shader, "TRIS", {"pos": coords}, indices=indices)
            batch.draw(shader)

        self.restore_opengl_defaults()

    def draw_id(self, context):
        with gpu.matrix.push_pop():
            gpu.matrix.multiply_matrix(self.matrix_basis)
            if self.linked_wp_width <= 0:
                scale = context.region_data.view_distance
                gpu.matrix.scale(Vector((scale, scale, scale)))
            super().draw_id(context)

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        handle = solvesys.add_workplane(group, self.p1.py_data, self.nm.py_data)
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

    def draw_props(self, layout):
        # Display the normals props as they're not drawn in the viewport
        sub = self.nm.draw_props(layout)
        row = sub.row()
        row.enabled = not self.origin
        row.operator(Operators.AlignWorkplaneCursor).index = self.slvs_index
        if self.origin:
            sub.label(text="Origin workplane cannot be changed")
        return sub


slvs_entity_pointer(SlvsWorkplane, "p1")
slvs_entity_pointer(SlvsWorkplane, "nm")

register, unregister = register_classes_factory((SlvsWorkplane,))
