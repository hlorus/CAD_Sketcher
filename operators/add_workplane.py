import logging

import bpy
from bpy.types import Operator, Context

from .. import global_data
from ..model.types import SlvsNormal3D
from ..model.categories import NORMAL3D

from ..utilities.geometry import get_face_orientation
from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from ..stateful_operator.state import state_from_args
from ..stateful_operator.utilities.geometry import get_evaluated_obj, get_mesh_element
from ..solver import solve_system
from .base_3d import Operator3d
from .constants import types_point_3d
from .utilities import ignore_hover
from ..utilities.view import get_placement_pos

logger = logging.getLogger(__name__)


class View3D_OT_slvs_add_workplane(Operator, Operator3d):
    """Add a workplane"""

    bl_idname = Operators.AddWorkPlane
    bl_label = "Add Solvespace Workplane"
    bl_options = {"REGISTER", "UNDO"}

    wp_state1_doc = ("Origin", "Pick or place workplanes's origin.")
    wp_state2_doc = ("Orientation", "Set workplane's orientation.")

    states = (
        state_from_args(
            wp_state1_doc[0],
            description=wp_state1_doc[1],
            pointer="p1",
            types=types_point_3d,
        ),
        state_from_args(
            wp_state2_doc[0],
            description=wp_state2_doc[1],
            state_func="get_orientation",
            pointer="nm",
            types=NORMAL3D,
            interactive=True,
            create_element="create_normal3d",
        ),
    )

    def get_normal(self, context: Context, index: int):
        states = self.get_states_definition()
        state = states[index]
        data = self._state_data[index]
        type = data["type"]
        sse = context.scene.sketcher.entities

        if type == bpy.types.MeshPolygon:
            ob_name, nm_index = self.get_state_pointer(index=index, implicit=True)
            ob = bpy.data.objects[ob_name]
            return sse.add_ref_normal_3d(ob, nm_index)
        return getattr(self, state.pointer)

    def get_orientation(self, context: Context, coords):
        # TODO: also support edges
        data = self.state_data
        ob, type, index = get_mesh_element(context, coords, edge=False, face=True)

        p1 = self.get_point(context, 0)
        mousepos = get_placement_pos(context, coords)
        vec = mousepos - p1.location
        return global_data.Z_AXIS.rotation_difference(vec).to_euler()

    def create_normal3d(self, context: Context, values, state, state_data):
        sse = context.scene.sketcher.entities

        v = values[0].to_quaternion()
        nm = sse.add_normal_3d(v)
        state_data["type"] = SlvsNormal3D
        return nm.slvs_index

    def main(self, context: Context):
        sse = context.scene.sketcher.entities
        p1 = self.get_point(context, 0)
        nm = self.get_normal(context, 1)
        self.target = sse.add_workplane(p1, nm)
        ignore_hover(self.target)
        return True

    def fini(self, context: Context, succeede: bool):
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))

        if succeede:
            if self.has_coincident():
                solve_system(context)


class View3D_OT_slvs_add_workplane_face(Operator, Operator3d):
    """Add a statically placed workplane, orientation and location is copied from selected mesh face"""

    bl_idname = Operators.AddWorkPlaneFace
    bl_label = "Add Solvespace Workplane"
    bl_options = {"REGISTER", "UNDO"}

    wp_face_state1_doc = (
        "Face",
        "Pick a mesh face to use as workplanes's transformation.",
    )

    states = (
        state_from_args(
            wp_face_state1_doc[0],
            description=wp_face_state1_doc[1],
            use_create=False,
            pointer="face",
            types=(bpy.types.MeshPolygon,),
            interactive=True,
        ),
    )

    def main(self, context: Context):
        sse = context.scene.sketcher.entities

        ob_name, face_index = self.get_state_pointer(index=0, implicit=True)
        ob = get_evaluated_obj(context, bpy.data.objects[ob_name])
        mesh = ob.data
        face = mesh.polygons[face_index]

        mat_obj = ob.matrix_world
        quat = get_face_orientation(mesh, face)
        quat.rotate(mat_obj)
        pos = mat_obj @ face.center
        origin = sse.add_point_3d(pos)
        nm = sse.add_normal_3d(quat)

        self.target = sse.add_workplane(origin, nm)
        ignore_hover(self.target)
        context.area.tag_redraw() # Force re-draw of UI (Blender doesn't update after tool usage)
        return True


register, unregister = register_stateops_factory(
    (View3D_OT_slvs_add_workplane, View3D_OT_slvs_add_workplane_face)
)
