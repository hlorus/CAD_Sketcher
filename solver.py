import logging
from .functions import bpyEnum
from .global_data import solver_state_items

logger = logging.getLogger(__name__)


class Solver:
    group_fixed = 1
    group_3d = 2
    start_sketch_groups = 3

    # iterate over constraints of active group and lazily init required entities
    def __init__(self, context, sketch):
        self.context = context
        self.entities = []
        self.constraints = {}

        self.tweak_entity = None
        self.tweak_pos = None
        self.tweak_constraint = None

        self.report = False

        logger.info("--- Start solving ---")
        from py_slvs import slvs

        self.solvesys = slvs.System()

        self.FREE_IN_3D = slvs.SLVS_FREE_IN_3D
        self.sketch = sketch

        self.ok = False
        self.result = None

    def get_workplane(self):
        if self.sketch:
            return self.sketch.wp.py_data
        return self.FREE_IN_3D

    def _store_constraint_indices(self, c, indices):
        for i in indices:
            self.constraints[i] = c

    def _get_group(self, sketch):
        type, index = self.context.scene.sketcher.entities._breakdown_index(
            sketch.slvs_index
        )
        return self.start_sketch_groups + index

    def _init_slvs_data(self):
        context = self.context
        logger.debug("Initialize entities:")

        for e in context.scene.sketcher.entities.all:
            self.entities.append(e)

            if e.fixed:
                group = self.group_fixed
            elif hasattr(e, "sketch"):
                group = self._get_group(e.sketch)
            else:
                group = self.group_3d

            if self.tweak_entity and e == self.tweak_entity:
                wp = self.get_workplane()
                if hasattr(e, "tweak"):
                    e.tweak(self.solvesys, self.tweak_pos)

                    self.solvesys.addWhereDragged(e.py_data, wrkpln=wp, group=group)
                else:
                    if not self.sketch:
                        params = [
                            self.solvesys.addParamV(val, group)
                            for val in self.tweak_pos
                        ]
                        p = self.solvesys.addPoint3d(*params, group=group)
                    else:
                        wrkpln = self.sketch.wp
                        u, v, _ = wrkpln.matrix_basis.inverted() @ self.tweak_pos
                        params = [self.solvesys.addParamV(val, group) for val in (u, v)]
                        p = self.solvesys.addPoint2d(
                            wrkpln.py_data, *params, group=group
                        )

                    e.create_slvs_data(self.solvesys, group=group)

                    from .class_defines import make_coincident

                    self.tweak_constraint = make_coincident(
                        self.solvesys, p, e, wp, group
                    )
                    self.solvesys.addWhereDragged(p, wrkpln=wp, group=group)
                continue

            e.create_slvs_data(self.solvesys, group=group)

            logger.debug("g:" + str(group) + " " + str(e))

        logger.debug("Initialize constraints:")

        for c in context.scene.sketcher.constraints.all:

            if hasattr(c, "sketch") and c.sketch:
                group = self._get_group(c.sketch)
            else:
                group = self.group_3d

            if self.report:
                c.failed = False

            # Store a index-constraint mapping
            from collections.abc import Iterable

            indices = c.create_slvs_data(self.solvesys, group=group)
            self._store_constraint_indices(
                c, indices if isinstance(indices, Iterable) else (indices,)
            )

            logger.debug("g:" + str(group) + " " + str(c))

    def tweak(self, entity, pos):
        logger.info("tweak: {} to: {}".format(entity, pos))

        self.tweak_entity = entity

        # NOTE: there should be a difference between 2d coords or 3d location...
        self.tweak_pos = pos

    def is_active(self, e):
        if e.fixed:
            return False
        return e.is_active(self.sketch)

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

    def solve(self, report=True):
        self.report = report
        self._init_slvs_data()

        group = self._get_group(self.sketch) if self.sketch else self.group_3d

        retval = self.solvesys.solve(
            group=group,
            reportFailed=report,
            findFreeParams=False,
        )

        # NOTE: For some reason solve() might return undocumented values,
        # Clamp result value to 4
        if retval > 3:
            logger.warning("Solver returned undocumented value: {}".format(retval))
            retval = 4

        self.result = bpyEnum(solver_state_items, index=retval)

        sketch = self.sketch
        if report and sketch:
            sketch.solver_state = self.result.identifier

        if retval == 0:
            self.ok = True
            for e in self.entities:
                e.update_from_slvs(self.solvesys)
                # TODO: skip entities that aren't in active group

        logger.log(20 if self.ok else 30, self.result.description)

        fails = self.solvesys.Failed
        if report and fails:
            logger.warning("Failed constraints:\n")

            for i in fails:
                if i == self.tweak_constraint:
                    continue
                constr = self.constraints[i]
                constr.failed = True
                logger.debug(constr)

        return retval


def solve_system(context, sketch=None):
    solver = Solver(context, sketch)
    return solver.solve()
