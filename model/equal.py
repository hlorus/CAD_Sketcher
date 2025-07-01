import logging

from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory

from ..solver import Solver
from .base_constraint import GenericConstraint
from .utilities import slvs_entity_pointer
from .categories import LINE, CURVE
from .line_2d import SlvsLine2D
from .arc import SlvsArc
from .circle import SlvsCircle

logger = logging.getLogger(__name__)


line_arc_circle = (*LINE, *CURVE)


class SlvsEqual(GenericConstraint, PropertyGroup):
    """Forces two lengths, or radiuses to be equal.

    If a line and an arc of a circle are selected, then the length of the line is
    forced equal to the length (not the radius) of the arc.
    """

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
                return CURVE
            return (type(e),)
        return cls.signature[index]

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        e1, e2 = self.entity1, self.entity2

        wp = self.get_workplane()
        kwargs = {}
        if wp:
            kwargs["workplane"] = wp

        return solvesys.equal(group, e1.py_data, e2.py_data, **kwargs)

    def placements(self):
        return (self.entity1, self.entity2)


slvs_entity_pointer(SlvsEqual, "entity1")
slvs_entity_pointer(SlvsEqual, "entity2")
slvs_entity_pointer(SlvsEqual, "sketch")

register, unregister = register_classes_factory((SlvsEqual,))
