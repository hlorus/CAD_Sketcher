import logging
from .utilities.bpy import bpyEnum
from .global_data import solver_state_items

logger = logging.getLogger(__name__)

tweak_vectors = []
class Solver:
    def __init__(self, context, sketch, all=False):
        from solvespace import Entity
        self.context = context
        self.tweak_entity = Entity.NO_ENTITY
        self.tweak_pos = [0, 0, 0]
        self.tweak_is_first = False
        self.sketch = sketch
        self.all = all
        self.groups = []
        self.failed_sketches = []
        self.entities = []

    def tweak(self, entity, pos, is_first):
        logger.debug("tweak: {} to: {}".format(entity, pos))
        self.tweak_entity = entity
        # NOTE: there should be a difference between 2d coords or 3d location...
        self.tweak_pos = pos
        self.tweak_is_first = is_first
        if is_first:
            tweak_vectors = []

    def get_workplane(self):
        from solvespace import Entity
        if self.sketch:
            return self.sketch.wp.py_data
        return Entity.FREE_IN_3D

    def _init_slvs_data(self):
        from solvespace import SK, Group, Vector
        SK.clear()
        fixed = Group()
        SK.add_group(fixed)
        self.groups.append(fixed)
        free_in_3d = Group()
        SK.add_group(free_in_3d)
        self.groups.append(free_in_3d)

        sketcher = self.context.scene.sketcher
        # if sketcher.active_workplane_i == -1:
        #     group = self.group_3d
        # else:
        #     wp = context.scene.sketcher.active_workplane
        #     group = group_wp

        for s in sketcher.entities.sketches:
            sk = Group()
            SK.add_group(sk)
            SK.set_active_group(sk)
            self.groups.append(sk)

        for e in sketcher.entities.all:
            if e.fixed:
                group = fixed
            elif hasattr(e, "sketch") and e.sketch is not None:
                # todo, get actual group from sketch
                group = SK.get_active_group() # e.sketch.slvs_index
            else:
                group = free_in_3d
            SK.set_active_group(group)
            self.entities.append(e)
            if self.tweak_entity and e == self.tweak_entity:
                wp = self.get_workplane()
                # if hasattr(e, "tweak"):
                #     e.tweak(SK, self.tweak_pos, group)
                # else:
                if not self.sketch:
                    p = SK.add_point_3d(self.tweak_pos[0], self.tweak_pos[1], self.tweak_pos[2])
                else:
                    wrkpln = self.sketch.wp
                    u, v, _ = wrkpln.matrix_basis.inverted() @ self.tweak_pos
                    p = SK.add_point_2d(u, v, wrkpln.py_data)
                SK.dragged(p, wp)
                e.create_slvs_data(SK)
                te = self.tweak_entity
                if te.is_point():
                    SK.coincident(p, e.py_data, wp)
                if te.is_curve():
                    SK.coincident(p, e.py_data, wp)
                    SK.dragged(e.ct.py_data, wp)
                if te.is_line():
                    mouse_pos = Vector.make(self.tweak_pos[0], self.tweak_pos[1], self.tweak_pos[2])
                    if self.tweak_is_first:
                        tweak_vectors.clear()
                        tweak_vectors.append(te.p1.py_data.point_get_num().minus(mouse_pos))
                        tweak_vectors.append(te.p2.py_data.point_get_num().minus(mouse_pos))
                        print("tweak_vectors", tweak_vectors)
                        continue
                    print("tweak_vectors", tweak_vectors)
                    te.p1.py_data.point_force_to(
                        mouse_pos.plus(tweak_vectors[0]))
                    te.p2.py_data.point_force_to(
                        mouse_pos.plus(tweak_vectors[1]))
                continue
            e.create_slvs_data(SK)

        for c in self.context.scene.sketcher.constraints.all:
            c.create_slvs_data(SK)

    def needs_update(self, e):
        if hasattr(e, "sketch") and e.sketch in self.failed_sketches:
            # Skip entities that belong to a failed sketch
            return False
        # TODO: skip entities that aren't in active group
        return True

    def solve(self, report=False):
        print("===================SOLVE================")
        from solvespace import SK, SolverSystem, SolveResult
        self._init_slvs_data()
        if self.all or self.sketch is None:
            groups = self.groups
        else:
            groups = [SK.get_active_group()]
        for g in groups:
            # self.context.scene.sketcher.entities.sketches
            # self.failed_sketches.append(g)
            sys = SolverSystem()
            result = sys.solve(g)
            print("result.status", result.status)
            for e in self.entities:
                if not self.needs_update(e):
                    continue
                e.update_from_slvs(SK)
            return result.status == SolveResult.OKAY

    # groups = []
    # # group_fixed = 1
    # # group_3d = 2
    # start_sketch_groups = 2

    # # iterate over constraints of active group and lazily init required entities
    # def __init__(self, context, sketch, all=False):
    #     self.context = context
    #     self.entities = []
    #     self.constraints = {}

    #     self.tweak_entity = None
    #     self.tweak_pos = None
    #     self.tweak_constraint = None

    #     self.report = False
    #     self.all = all
    #     self.failed_sketches = []

    #     # group = self._get_group(sketch) if sketch else self.group_3d
    #     logger.info(
    #         "--- Start solving ---\nAll:{}, Sketch:{}, g:{}".format(all, sketch, group)
    #     )

    #     from solvespace import SK, SolverSystem, Entity, Group

    #     group_fixed = Group()
    #     SK.add_group(group_fixed)
    #     self.groups.append(group_fixed)

    #     group_3d = Group()
    #     SK.add_group(group_3d)
    #     self.groups.append(group_3d)

    #     SK.set_active_group(group_3d)
    #     # start_sketch_groups = Group()
    #     # SK.add_group(start_sketch_groups)
    #     self.solvesys = SolverSystem()

    #     self.FREE_IN_3D = Entity._FREE_IN_3D
    #     self.sketch = sketch

    #     self.ok = True
    #     self.result = None

    # def get_workplane(self):
    #     if self.sketch:
    #         return self.sketch.wp.py_data
    #     return self.FREE_IN_3D

    # def _store_constraint_indices(self, c, indices):
    #     for i in indices:
    #         self.constraints[i] = c

    # def _get_group(self, sketch):
    #     if not sketch:
    #         return self.groups[1] # 3d group
    #     type, index = self.context.scene.sketcher.entities._breakdown_index(
    #         sketch.slvs_index
    #     )
    #     return self.groups[self.start_sketch_groups + index]

    # def _init_slvs_data(self):
    #     context = self.context

    #     # Initialize Entities
    #     for e in context.scene.sketcher.entities.all:
    #         self.entities.append(e)

    #         if e.fixed:
    #             group = self.groups[0] # fixed
    #         elif hasattr(e, "sketch"):
    #             group = self._get_group(e.sketch)
    #         else:
    #             group = self.groups[1] # 3d
    #         self.solvesys.set_active_group(group)
    #         if self.tweak_entity and e == self.tweak_entity:
    #             wp = self.get_workplane()
    #             if hasattr(e, "tweak"):
    #                 e.tweak(self.solvesys, self.tweak_pos, group)
    #             else:
    #                 if not self.sketch:
    #                     p = self.solvesys.add_point_3d(*self.tweak_pos)
    #                 else:
    #                     wrkpln = self.sketch.wp
    #                     u, v, _ = wrkpln.matrix_basis.inverted() @ self.tweak_pos
    #                     p = self.solvesys.add_point_2d(u, v, wrkpln.py_data)

    #                 e.create_slvs_data(self.solvesys)

    #                 self.tweak_constraint = self.solvesys.coincident(p, e.py_data, wp)
    #                 self.solvesys.dragged(p, wp)
    #             continue

    #         e.create_slvs_data(self.solvesys)

    #     def _get_msg_entities():
    #         msg = "Initialize entities:"
    #         for e in context.scene.sketcher.entities.all:
    #             msg += "\n  - {}".format(e)
    #         return msg

    #     logger.debug(_get_msg_entities())

    #     # Initialize Constraints
    #     for c in context.scene.sketcher.constraints.all:
    #         if hasattr(c, "sketch") and c.sketch:
    #             group = self._get_group(c.sketch)
    #         else:
    #             group = self.group_3d

    #         if self.report:
    #             c.failed = False

    #         # Store a index-constraint mapping
    #         from collections.abc import Iterable

    #         indices = c.create_slvs_data(self.solvesys)
    #         self._store_constraint_indices(
    #             c, indices if isinstance(indices, Iterable) else (indices,)
    #         )

    #     def _get_msg_constraints():
    #         msg = "Initialize constraints:"
    #         for c in context.scene.sketcher.constraints.all:
    #             msg += "\n  - {}".format(c)
    #         return msg

    #     logger.debug(_get_msg_constraints())

    # def tweak(self, entity, pos):
    #     logger.debug("tweak: {} to: {}".format(entity, pos))

    #     self.tweak_entity = entity

    #     # NOTE: there should be a difference between 2d coords or 3d location...
    #     self.tweak_pos = pos

    # def is_active(self, e):
    #     if e.fixed:
    #         return False
    #     return e.is_active(self.sketch)

    # # NOTE: When solving not everything might be relevant...
    # # An approach could be to find all constraints of a sketch and all necessary entities
    # # and only initialize them

    # # def dummy():
    # # wp = None
    # # if context.scene.sketcher.active_workplane_i == -1:
    # #     group = self.group_3d
    # # else:
    # #     wp = context.scene.sketcher.active_workplane
    # #     # i = context.scene.sketcher.entities.get_local_index(wp.slvs_index)
    # #     # group = i + 2
    # #     group = group_wp
    # #
    # # constraints = self.get_constraints(context, wp)
    # #
    # # entities = []
    # # for c in constraints:
    # #     # ensure entities are initialized
    # #     for e in c.entities(): # should be recursive!
    # #         if e not in entities:
    # #             entities.append(e)
    # #
    # #     c.create_slvs_data(solvesys)

    # # def get_constraints(self, context, wp):
    # #     constraints = []
    # #     for c in context.scene.sketcher.constraints.all:
    # #         if wp and not hasattr(c, "wp"):
    # #             continue
    # #         if hasattr(c, "wp") and c.wp != wp:
    # #             continue  # c.is_active(group)
    # #         constraints.append(c)
    # #     return constraints

    # def needs_update(self, e):
    #     if hasattr(e, "sketch") and e.sketch in self.failed_sketches:
    #         # Skip entities that belong to a failed sketch
    #         return False
    #     # TODO: skip entities that aren't in active group
    #     return True

    # def solve(self, report=True):
    #     self.report = report
    #     self._init_slvs_data()
    #     if self.all:
    #         sse = self.context.scene.sketcher.entities
    #         sketches = [None, *sse.sketches]
    #     else:
    #         sketches = [
    #             self.sketch,
    #         ]

    #     for sketch in sketches:
    #         retval = self.solvesys.solve()

    #         if retval > 5:
    #             logger.debug("Solver returned undocumented value: {}".format(retval))

    #         self.result = bpyEnum(solver_state_items, index=retval)

    #         if report and sketch:
    #             sketch.solver_state = self.result.index
    #             sketch.dof = self.solvesys.dof()

    #         if retval != 0 and retval != 5:
    #             self.ok = False

    #             # Store sketch failures
    #             self.failed_sketches.append(sketch)

    #         logger.info(self.result.description)

    #         fails = self.solvesys.failures()
    #         print("fails: {}".format(fails))
    #         if report and fails:

    #             for i in fails:
    #                 if i == self.tweak_constraint:
    #                     continue
    #                 constr = self.constraints[i]
    #                 constr.failed = True

    #             def _get_msg_failed():
    #                 msg = "Failed constraints:"
    #                 for i in fails:
    #                     constr = self.constraints[i]
    #                     msg += "\n  - {}".format(constr)
    #                 return msg

    #             logger.debug(_get_msg_failed())

    #     # Update entities from solver
    #     for e in self.entities:
    #         if not self.needs_update(e):
    #             continue

    #         e.update_from_slvs(self.solvesys)

    #     def _get_msg_update():
    #         msg = "Update entities from solver:"
    #         for e in self.entities:
    #             if not self.needs_update(e):
    #                 continue
    #             msg += "\n - " + str(e)
    #         return msg

    #     logger.debug(_get_msg_update())
    #     logger.debug(self.solvesys.constraints())
    #     return self.ok


def solve_system(context, sketch=None):
    solver = Solver(context, sketch)
    return solver.solve()
