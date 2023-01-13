import logging

from bpy.types import PropertyGroup
from bpy.props import FloatProperty
from bpy.utils import register_classes_factory

from ..solver import Solver
from ..global_data import WpReq
from .base_constraint import GenericConstraint
from .utilities import slvs_entity_pointer
from .categories import LINE
from .line_2d import SlvsLine2D

logger = logging.getLogger(__name__)


class SlvsRatio(GenericConstraint, PropertyGroup):
    """Defines the ratio between the lengths of two line segments.

    The order matters; the ratio is defined as length of entity1 : length of entity2.
    """

    type = "RATIO"
    label = "Ratio"

    value: FloatProperty(
        name=label,
        subtype="UNSIGNED",
        update=GenericConstraint.update_system_cb,
        min=0.0,
    )

    signature = (
        LINE,
        LINE,
    )

    def needs_wp(self):
        if isinstance(self.entity1, SlvsLine2D) or isinstance(self.entity2, SlvsLine2D):
            return WpReq.NOT_FREE
        return WpReq.FREE

    def create_slvs_data(self, solvesys):
        e1, e2 = self.entity1, self.entity2

        return solvesys.ratio(
            e1.py_data,
            e2.py_data,
            self.value,
            self.get_workplane(),
        )

    def init_props(self, **kwargs):
        line1, line2 = self.entity1, self.entity2

        value = line1.length / line2.length
        return value, None

    def draw_props(self, layout):
        sub = super().draw_props(layout)
        sub.prop(self, "value")
        return sub

    def placements(self):
        return (self.entity1, self.entity2)


slvs_entity_pointer(SlvsRatio, "entity1")
slvs_entity_pointer(SlvsRatio, "entity2")
slvs_entity_pointer(SlvsRatio, "sketch")

register, unregister = register_classes_factory((SlvsRatio,))
