import logging

from bpy.types import PropertyGroup
from bpy.props import FloatProperty, IntProperty, StringProperty
from bpy.utils import register_classes_factory

from ..curve_solver import Solver
from ..global_data import WpReq
from .base_constraint import DimensionalConstraint
from .utilities import slvs_entity_pointer
from .categories import LINE
from .line_2d import SlvsLine2D
from ..utilities.solver import update_system_cb

logger = logging.getLogger(__name__)


class SlvsRatio(DimensionalConstraint, PropertyGroup):
    """Defines the ratio between the lengths of two line segments.

    The order matters; the ratio is defined as length of entity1 : length of entity2.
    """

    type = "RATIO"
    label = "Ratio"

    value: FloatProperty(
        name=label,
        subtype="UNSIGNED",
        update=update_system_cb,
        min=0.0,
    )

    signature = (
        LINE,
        LINE,
    )

    curve_id_1: StringProperty(name="Curve ID 1", default="")
    curve_id_2: StringProperty(name="Curve ID 2", default="")

    def create_slvs_data_from_curves(self, solvesys, handle_map, wp, group):
        h1 = handle_map.get(self.curve_id_1)
        h2 = handle_map.get(self.curve_id_2)
        if h1 is None or h2 is None:
            return None
        kwargs = {}
        if wp:
            kwargs['workplane'] = wp
        return solvesys.ratio(group, h1, h2, self.value, **kwargs)

    def needs_wp(self):
        if isinstance(self.entity1, SlvsLine2D) or isinstance(self.entity2, SlvsLine2D):
            return WpReq.NOT_FREE
        return WpReq.FREE

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        e1, e2 = self.entity1, self.entity2

        wp = self.get_workplane()
        kwargs = {}
        if wp:
            kwargs['workplane'] = wp
        
        return solvesys.ratio(
            group,
            e1.py_data,
            e2.py_data,
            self.value,
            **kwargs,
        )

    def init_props(self, **kwargs):
        r1, r2 = self.ref(1), self.ref(2)
        if r1 and r2:
            if r2.length == 0.0:
                return {"value": 0.0}
            return {"value": r1.length / r2.length}
        return {"value": 0.0}

    def placements(self):
        return (self.ref(1), self.ref(2))


slvs_entity_pointer(SlvsRatio, "entity1")
slvs_entity_pointer(SlvsRatio, "entity2")
slvs_entity_pointer(SlvsRatio, "sketch")

register, unregister = register_classes_factory((SlvsRatio,))
