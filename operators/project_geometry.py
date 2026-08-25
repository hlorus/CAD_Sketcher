"""Project a single picked mesh element into the active sketch.

A minimal single-state stateful operator: the one state picks a mesh vertex,
edge or face (via the framework's native mesh-element picking), and ``main``
projects just that element as live native curves through the shared
``project_mesh_element`` path. Re-run to project more; shared corners are reused.
"""

import logging

import bpy
from bpy.props import BoolProperty
from bpy.types import Context, Operator

from ..declarations import Operators
from ..model.sketch_ref import get_active_sketch
from ..stateful_operator.constants import mesh_element_types
from ..stateful_operator.integration import StatefulOperator
from ..stateful_operator.state import state_from_args
from ..stateful_operator.utilities.register import register_stateops_factory
from ..utilities.curve_data import refresh_curve_geometry
from ..utilities.projection_anchor import project_curves_element, project_mesh_element
from .base_stateful import GenericEntityOp

logger = logging.getLogger(__name__)

_TYPE_TO_ELEMENT = {
    bpy.types.MeshVertex: "VERTEX",
    bpy.types.MeshEdge: "EDGE",
    bpy.types.MeshPolygon: "FACE",
}


class VIEW3D_OT_slvs_project_geometry(Operator, GenericEntityOp):
    """Project a picked mesh vertex, edge or face into the active sketch"""

    bl_idname = Operators.ProjectGeometry
    bl_label = "Project Geometry"
    bl_options = {"REGISTER", "UNDO"}

    construction: BoolProperty(
        name="Construction Geometry",
        description="Create the projected points and lines as construction geometry",
        default=True,
    )

    states = (
        state_from_args(
            "Element",
            description="Pick a mesh vertex, edge or face to project into the sketch",
            pointer="element",
            types=mesh_element_types,
            property=None,
            use_create=False,
        ),
    )

    @classmethod
    def poll(cls, context: Context):
        return get_active_sketch(context) is not None

    def pick_element(self, context: Context, coords):
        # Raw mesh-element pick first (skip GenericEntityOp's curve/constraint
        # hover handling). With no mesh hit, fall back to a reference curve element
        # so another sketch's line/point can be picked and projected -- agreeing
        # with the hover gizmo, which uses the same reference pick.
        retval = StatefulOperator.pick_element(self, context, coords)
        data = self.state_data
        if retval is not None:
            data.pop("curve_ref", None)
            logger.debug("project pick: mesh element %s", retval)
            return retval

        from ..drawing.reference_pick import pick_reference_element

        active = get_active_sketch(context)
        ref = pick_reference_element(
            context, coords, exclude=active.target_object if active else None
        )
        logger.debug("project pick: no mesh hit; reference curve element -> %s", ref)
        if ref is not None:
            ob, key = ref
            data["curve_ref"] = (ob.name, key)
            data["type"] = None  # not a mesh element; dispatched via curve_ref
            return (ob.name, key)
        data.pop("curve_ref", None)
        return None

    def get_state_pointer(self, index=None, implicit=False):
        # A picked curve element has no mesh/entity pointer, so report the stashed
        # reference as the state's pointer -- otherwise check_props() sees an empty
        # pointer and never calls main() (nothing would project).
        idx = self.state_index if index is None else index
        data = self._state_data.get(idx, {})
        if data.get("curve_ref"):
            return data["curve_ref"]
        return super().get_state_pointer(index=index, implicit=implicit)

    def main(self, context: Context):
        sketch = get_active_sketch(context)
        if sketch is None:
            logger.debug("project main: no active sketch")
            return False
        data = self._state_data.get(0, {})

        curve_ref = data.get("curve_ref")
        logger.debug("project main: curve_ref=%s type=%s", curve_ref, data.get("type"))
        if curve_ref:
            source = bpy.data.objects.get(curve_ref[0])
            if source is None:
                logger.debug("project main: source object %r missing", curve_ref[0])
                return False
            n_points, n_lines, skipped = project_curves_element(
                sketch, source, curve_ref[1], construction=self.construction
            )
            logger.debug(
                "project main: curve element -> points=%s lines=%s skipped=%s",
                n_points,
                n_lines,
                skipped,
            )
            if skipped:
                self.report(
                    {"INFO"}, "This curve element can't be projected yet (arc/circle)"
                )
        else:
            elem = _TYPE_TO_ELEMENT.get(data.get("type"))
            pointer = self.get_state_pointer(index=0, implicit=True)
            if elem is None or not pointer:
                return False
            obj_name, mesh_index = pointer
            source = bpy.data.objects.get(obj_name)
            if source is None or source.type != "MESH":
                return False
            n_points, n_lines = project_mesh_element(
                sketch, source, elem, mesh_index, construction=self.construction
            )

        if n_points or n_lines:
            refresh_curve_geometry(sketch)
            from .. import global_data

            global_data.needs_solve = True
            global_data.needs_redraw = True

        self.target = sketch
        return True

    def fini(self, context: Context, succeed: bool):
        pass


register, unregister = register_stateops_factory((VIEW3D_OT_slvs_project_geometry,))
