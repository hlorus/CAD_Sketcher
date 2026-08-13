"""Solve legacy 3D entities and constraints outside native curve sketches.

The native-curves solver intentionally handles sketch geometry only. 3D points,
lines and workplanes are still stored in ``scene.sketcher.entities`` and use the
legacy entity API, so keep a small solver path for those entities rather than
routing them through the 2D CurveSolver.
"""

import logging

from .global_data import solver_state_items
from .utilities.bpy import bpyEnum

logger = logging.getLogger(__name__)


class Solver3D:
    group_fixed = 1
    group_3d = 2

    def __init__(self, context):
        self.context = context
        self.entities = []
        self.constraints = {}
        self.ok = True
        self.result = None

        import slvs

        slvs.clear_sketch()
        self.solvesys = slvs

    def _init_entities(self):
        entities = self.context.scene.sketcher.entities
        for entity in entities.all:
            if not entity.is_3d():
                continue

            group = self.group_fixed if entity.fixed else self.group_3d
            entity.create_slvs_data(self.solvesys, group=group)
            self.entities.append(entity)

    def _store_constraint(self, constraint, handles):
        if handles is None:
            return
        if not isinstance(handles, (tuple, list)):
            handles = (handles,)

        for handle in handles:
            if isinstance(handle, dict):
                index = handle.get("h")
            else:
                index = handle
            if index:
                self.constraints[index] = constraint

    def _init_constraints(self):
        for constraint in self.context.scene.sketcher.constraints.all:
            # Native-curve constraints carry curve ids and are handled by
            # CurveSolver. Scene-level 3D constraints use entity pointers.
            if getattr(constraint, "curve_id_1", ""):
                continue

            entities = constraint.entities()
            if not entities or not all(entity.is_3d() for entity in entities):
                continue

            constraint.failed = False
            handles = constraint.py_data(self.solvesys, group=self.group_3d)
            self._store_constraint(constraint, handles)

    def _mark_failed_constraints(self, failed_handles):
        for handle in failed_handles:
            constraint = self.constraints.get(handle)
            if constraint is not None:
                constraint.failed = True

    def solve(self, report=True):
        self._init_entities()
        self._init_constraints()

        result = self.solvesys.solve_sketch(self.group_3d, report)
        if isinstance(result, dict):
            retval = result
            failed_handles = retval.get("failed", ()) or retval.get("bad", ()) or ()
        else:
            retval, failed_handles, *_ = result

        result_code = retval["result"]
        self.ok = result_code in (0, 4)
        self.result = bpyEnum(
            solver_state_items,
            index=5 if result_code > 4 else result_code,
        )

        if report and failed_handles:
            if isinstance(failed_handles, int):
                failed_handles = (failed_handles,)
            self._mark_failed_constraints(failed_handles)

        if self.ok:
            for entity in self.entities:
                entity.update_from_slvs(self.solvesys)

        logger.info("3D solver: %s", self.result.description)
        return self.ok


def solve_system_3d(context):
    """Solve scene-level 3D entities and constraints."""
    return Solver3D(context).solve()
