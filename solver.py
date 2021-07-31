import logging
from enum import Enum

logger = logging.getLogger(__name__)


class Status(Enum):
    OKAY = 0, "Okay", "Successfully solved sketch"
    INCONSISTENT = (
        1,
        "Inconsistent",
        "Cannot solve sketch because of inconsistent constraints",
    )
    DIDNT_CONVERGE = 2, "Didnt Converge", "Cannot solve sketch because ..."
    TOO_MANY_UNKNOWNS = (
        3,
        "Too Many Unknowns",
        "Cannot solve sketch because of too many unknowns",
    )

    def __new__(cls, *args, **kwds):
        obj = object.__new__(cls)
        obj._value_ = args[0]
        return obj

    def __init__(self, _val: int, label: str, description: str = None):
        self._label_ = label
        self._description_ = description

    def __str__(self):
        return self.value

    @property
    def label(self):
        return self._label_

    @property
    def description(self):
        return self._description_


class Solver:
    group_fixed = 0
    group_active = 1

    # iterate over constraints of active group and lazily init required entities
    def __init__(self, context):
        self.context = context
        self.entities = []

        self.tweak_entity = None
        self.tweak_pos = None

        logger.info("--- Start solving ---")
        from python_solvespace import slvs

        self.solvesys = slvs.SolverSystem()

        self.FREE_IN_3D = slvs.Entity.FREE_IN_3D
        self.sketch = context.scene.sketcher.active_sketch

        self.ok = False
        self.result = None

    def get_workplane(self):
        if self.sketch:
            return self.sketch.wp.py_data
        return self.FREE_IN_3D

    def _init_slvs_data(self):
        context = self.context
        logger.debug("Initialize entities:")

        for e in context.scene.sketcher.entities.all:
            self.entities.append(e)

            # TODO: Dont allow tweaking fixed entities
            if self.tweak_entity and e == self.tweak_entity:
                self.solvesys.set_group(self.group_active)
                if hasattr(e, "tweak"):
                    e.tweak(self.solvesys, self.tweak_pos)
                    self.solvesys.dragged(e.py_data, self.get_workplane())
                else:
                    if not self.sketch:
                        p = self.solvesys.add_point_3d(*self.tweak_pos)
                    else:
                        wp = self.sketch.wp
                        u, v, _ = wp.matrix_basis.inverted() @ self.tweak_pos
                        p = self.solvesys.add_point_2d(u, v, wp.py_data)

                    e.create_slvs_data(self.solvesys)
                    wp = self.get_workplane()
                    self.solvesys.coincident(p, e.py_data, wp)
                    self.solvesys.dragged(p, wp)
                continue

            group = self.group_active if self.is_active(e) else self.group_fixed
            self.solvesys.set_group(group)
            e.create_slvs_data(self.solvesys)

            if group:
                logger.debug(e)

        logger.debug("Initialize constraints:")
        for c in context.scene.sketcher.constraints.all:
            group = self.group_active if c.is_active(context) else self.group_fixed
            self.solvesys.set_group(group)
            c.create_slvs_data(self.solvesys)

            if group:
                logger.debug(c)

        self.solvesys.set_group(self.group_active)

    def tweak(self, entity, pos):
        logger.info("tweak: {} to: {}".format(entity, pos))

        self.tweak_entity = entity

        # NOTE: there should be a difference between 2d coords or 3d location...
        self.tweak_pos = pos

    def is_active(self, e):
        if e.fixed:
            return False
        return e.is_active(self.context)

    # NOTE: When solving not everything might be relevant...
    # An approach could be to find all constraints of a sketch and all neccesary entities
    # and only inizialize them

    # def dummy():
    # wp = None
    # if context.scene.sketcher.active_workplane_i == -1:
    #     group = self.group_3d
    # else:
    #     wp = context.scene.sketcher.active_workplane
    #     # i = context.scene.sketcher.entities.get_local_index(wp.slvs_index)
    #     # group = i + 2
    #     group = group_wp
    #
    # constraints = self.get_constraints(context, wp)
    #
    # entities = []
    # for c in constraints:
    #     # ensure entities are initialized
    #     for e in c.entities(): # should be recursive!
    #         if e not in entities:
    #             entities.append(e)
    #
    #     c.create_slvs_data(solvesys)

    # def get_constraints(self, context, wp):
    #     constraints = []
    #     for c in context.scene.sketcher.constraints.all:
    #         if wp and not hasattr(c, "wp"):
    #             continue
    #         if hasattr(c, "wp") and c.wp != wp:
    #             continue  # c.is_active(group)
    #         constraints.append(c)
    #     return constraints

    def solve(self):
        self.solvesys.set_group(self.group_active)
        self._init_slvs_data()
        retval = self.solvesys.solve()
        self.result = Status(retval)

        if retval == 0:
            self.ok = True
            for e in self.entities:
                e.update_from_slvs(self.solvesys)

        logger.log(20 if self.ok else 30, self.result.description)

        fails = self.solvesys.failures()
        if fails:
            logger.warning("Failed to solve:\n" + str(fails))

        return retval


def solve_system(context):
    solver = Solver(context)
    return solver.solve()
