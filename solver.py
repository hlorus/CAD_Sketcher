import logging
from .utilities.bpy import bpyEnum
from .global_data import solver_state_items

# TODO: Move to utilities.data_handling
from .model.utilities import make_coincident

logger = logging.getLogger(__name__)


class Solver:
    group_fixed = 1
    group_3d = 2
    start_sketch_groups = 3

    # iterate over constraints of active group and lazily init required entities
    def __init__(self, context, sketch, all=False):
        self.context = context
        self.entities = []
        self.constraints = {}

        self.tweak_entity = None
        self.tweak_pos = None
        self.tweak_constraint = None

        self.report = False
        self.all = all
        self.failed_sketches = []

        group = self._get_group(sketch) if sketch else self.group_3d
        logger.info(
            "--- Start solving ---\nAll:{}, Sketch:{}, g:{}".format(all, sketch, group)
        )
        from py_slvs import slvs

        self.solvesys = slvs.System()

        self.FREE_IN_3D = slvs.SLVS_FREE_IN_3D
        self.sketch = sketch

        self.ok = True
        self.result = None

    def get_workplane(self):
        if self.sketch:
            return self.sketch.wp.py_data
        return self.FREE_IN_3D

    def _store_constraint_indices(self, c, indices):
        for i in indices:
            self.constraints[i] = c

    def _get_group(self, sketch):
        if not sketch:
            return self.group_3d
        type, index = self.context.scene.sketcher.entities._breakdown_index(
            sketch.slvs_index
        )
        return self.start_sketch_groups + index

    def _init_slvs_data(self):
        context = self.context

        # Initialize Entities
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
                    e.tweak(self.solvesys, self.tweak_pos, group)
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

                    self.tweak_constraint = make_coincident(
                        self.solvesys, p, e, wp, group
                    )
                    self.solvesys.addWhereDragged(p, wrkpln=wp, group=group)
                continue

            e.create_slvs_data(self.solvesys, group=group)

        def _get_msg_entities():
            msg = "Initialize entities:"
            for e in context.scene.sketcher.entities.all:
                msg += "\n  - {}".format(e)
            return msg

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(_get_msg_entities())

        # Initialize Constraints
        for c in context.scene.sketcher.constraints.all:
            if hasattr(c, "sketch") and c.sketch:
                group = self._get_group(c.sketch)
            else:
                group = self.group_3d

            if self.report:
                c.failed = False

            # Store a index-constraint mapping
            from collections.abc import Iterable

            indices = c.py_data(self.solvesys, group=group)
            self._store_constraint_indices(
                c, indices if isinstance(indices, Iterable) else (indices,)
            )

        def _get_msg_constraints():
            msg = "Initialize constraints:"
            for c in context.scene.sketcher.constraints.all:
                msg += "\n  - {}".format(c)
            return msg

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(_get_msg_constraints())

    def tweak(self, entity, pos):
        logger.debug("tweak: {} to: {}".format(entity, pos))

        self.tweak_entity = entity

        # NOTE: there should be a difference between 2d coords or 3d location...
        self.tweak_pos = pos

    def is_active(self, e):
        if e.fixed:
            return False
        return e.is_active(self.sketch)

    # NOTE: When solving not everything might be relevant...
    # An approach could be to find all constraints of a sketch and all necessary entities
    # and only initialize them

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

    def needs_update(self, e):
        if hasattr(e, "sketch") and e.sketch in self.failed_sketches:
            # Skip entities that belong to a failed sketch
            return False
        # TODO: skip entities that aren't in active group
        return True

    def solve(self, report=True):
        self.report = report
        self._init_slvs_data()

        if self.all:
            sse = self.context.scene.sketcher.entities
            sketches = [None, *sse.sketches]
        else:
            sketches = [
                self.sketch,
            ]

        for sketch in sketches:
            g = self._get_group(sketch)
            retval = self.solvesys.solve(
                group=g,
                reportFailed=report,
                findFreeParams=False,
            )

            if retval > 5:
                logger.debug("Solver returned undocumented value: {}".format(retval))

            self.result = bpyEnum(solver_state_items, index=retval)

            if report and sketch:
                sketch.solver_state = self.result.identifier
                sketch.dof = self.solvesys.Dof

            if retval != 0 and retval != 5:
                self.ok = False

                # Store sketch failures
                self.failed_sketches.append(sketch)

            logger.info(self.result.description)

            fails = self.solvesys.Failed
            if report and fails:

                for i in fails:
                    if i == self.tweak_constraint:
                        continue
                    constr = self.constraints[i]
                    constr.failed = True

                def _get_msg_failed():
                    msg = "Failed constraints:"
                    for i in fails:
                        constr = self.constraints[i]
                        msg += "\n  - {}".format(constr)
                    return msg

                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(_get_msg_failed())

        # Update entities from solver
        for e in self.entities:
            if not self.needs_update(e):
                continue

            e.update_from_slvs(self.solvesys)

        def _get_msg_update():
            msg = "Update entities from solver:"
            for e in self.entities:
                if not self.needs_update(e):
                    continue
                msg += "\n - " + str(e)
            return msg

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(_get_msg_update())

        return self.ok


def solve_system(context, sketch=None):
    solver = Solver(context, sketch)
    return solver.solve()
