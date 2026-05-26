# pyright: reportInvalidTypeForm=false
import logging
from typing import List

import bpy
from bpy.types import PropertyGroup, Context
from bpy.props import FloatVectorProperty
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector
from bpy.utils import register_classes_factory

from ..utilities.draw import draw_rect_2d
from ..declarations import WorkSpaceTools
from ..solver import Solver
from .base_entity import SlvsGenericEntity, Entity2D, _entity_dirty_update
from .utilities import slvs_entity_pointer, make_coincident
from .line_2d import SlvsLine2D
from ..utilities.constants import HALF_TURN
from ..utilities.preferences import get_prefs

logger = logging.getLogger(__name__)


class Point2D(Entity2D):
    @classmethod
    def is_point(cls):
        return True

    def _is_selected_line_origin(self, context: Context) -> bool:
        """True when this point is p1 of a selected line in select tool mode."""
        workspace = getattr(context, "workspace", None)
        if workspace is None:
            return False

        tool = workspace.tools.from_space_view3d_mode(context.mode)
        if tool is None or tool.idname != WorkSpaceTools.Select:
            return False

        sketch = context.scene.sketcher.active_sketch
        if sketch is None:
            return False

        sse = context.scene.sketcher.entities
        for entity in sse.selected_active:
            if not isinstance(entity, SlvsLine2D):
                continue
            if entity.sketch != sketch:
                continue
            if entity.p1.slvs_index == self.slvs_index:
                return True
        return False

    def update(self):
        if bpy.app.background:
            return

        u, v = self.co
        mat_local = Matrix.Translation(Vector((u, v, 0)))

        mat = self.wp.matrix_basis @ mat_local
        size = 0.1
        coords = draw_rect_2d(0, 0, size, size)
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

        handle = solvesys.add_point_2d(group, *coords, self.wp.py_data)
        self.py_data = handle

    def update_from_slvs(self, solvesys):
        coords = [solvesys.get_param_value(self.py_data["param"][i]) for i in range(2)]
        self.co = coords

    def closest_picking_point(self, origin, view_vector):
        """Returns the point on this entity which is closest to the picking ray"""
        return self.location

    @property
    def point_size(self):
        if self._is_selected_line_origin(bpy.context):
            return 1.1 * super().point_size
        return super().point_size

    def color(self, context: Context):
        if self._is_selected_line_origin(context):
            return get_prefs().theme_settings.entity.line_origin
        return super().color(context)


class SlvsPoint2D(Point2D, PropertyGroup):
    """Representation of a point in 2D space.

    Arguments:
        co (FloatVectorProperty): The coordinates of the point on the worpkplane in the form (U, V)
        sketch (SlvsSketch): The sketch this entity belongs to
    """

    co: FloatVectorProperty(
        name="Coordinates",
        description="The coordinates of the point on its sketch",
        subtype="XYZ",
        size=2,
        unit="LENGTH",
        update=_entity_dirty_update,
    )
    props = ("co",)

    def dependencies(self) -> List[SlvsGenericEntity]:
        return [
            self.sketch,
        ]

    def draw_props(self, layout):
        sub = super().draw_props(layout)
        sub.prop(self, "co")
        return sub


slvs_entity_pointer(Point2D, "sketch")

register, unregister = register_classes_factory((SlvsPoint2D,))
