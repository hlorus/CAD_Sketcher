import logging

from bpy.types import PropertyGroup
from bpy.props import StringProperty
from bpy.utils import register_classes_factory

from ..curve_solver import Solver
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

    curve_id_1: StringProperty(name="Curve ID 1", default="")
    curve_id_2: StringProperty(name="Curve ID 2", default="")

    @classmethod
    def get_types(cls, index, entities):
        e = entities[1] if index == 0 else entities[0]
        if e:
            if e.is_line() or e.is_arc():
                return (SlvsLine2D, SlvsArc)
            elif e.is_circle():
                return CURVE
            return cls.signature[index]
        return cls.signature[index]

    @staticmethod
    def _compatible(r1, r2):
        """A line's length can't be equal to a circle's radius.

        solvespace supports line=line, line=arc (length), and
        arc/circle=arc/circle (radius), but has no line-vs-circle equality --
        passing that pair crashes the solver, so reject it here.
        """
        if not r1 or not r2:
            return True
        return not (
            (r1.is_line() and r2.is_circle())
            or (r1.is_circle() and r2.is_line())
        )

    def create_slvs_data_from_curves(self, solvesys, handle_map, wp, group):
        h1 = handle_map.get(self.curve_id_1)
        h2 = handle_map.get(self.curve_id_2)
        if h1 is None or h2 is None:
            return None
        if not self._compatible(self.ref(1), self.ref(2)):
            self.failed = True
            return None
        kwargs = {}
        if wp:
            kwargs['workplane'] = wp
        return solvesys.equal(group, h1, h2, **kwargs)

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        e1, e2 = self.entity1, self.entity2

        wp = self.get_workplane()
        kwargs = {}
        if wp:
            kwargs["workplane"] = wp

        return solvesys.equal(group, e1.py_data, e2.py_data, **kwargs)

    def placements(self):
        return (self.ref(1), self.ref(2))


slvs_entity_pointer(SlvsEqual, "entity1")
slvs_entity_pointer(SlvsEqual, "entity2")
slvs_entity_pointer(SlvsEqual, "sketch")

register, unregister = register_classes_factory((SlvsEqual,))
