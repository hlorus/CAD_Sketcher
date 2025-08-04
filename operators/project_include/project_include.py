import bpy
from bpy.types import Context, Event, MeshPolygon, Operator, TransformOrientation

from ...declarations import Operators
from ...model.group_entities import SlvsEntities
from ...stateful_operator.state import state_from_args
from ...stateful_operator.utilities.geometry import get_evaluated_obj
from ...stateful_operator.utilities.register import register_stateops_factory
from ..base_2d import Operator2d
from .get_object_under_mouse import get_object_under_mouse
from .handle_highlight import clear_highlight, handle_highlight
from .object_interface import FaceInterface, ObjectInterface, ObjectInterfaceProtocol
from .project_vertex_to_workplane import project_vertex_to_workplane
from .projection_data import ProjectionData


class View3D_OT_slvs_project_include(Operator, Operator2d):
    """Add a circle to the active sketch"""

    bl_idname = Operators.ProjectInclude
    bl_label = "Project a mesh onto the current sketch"
    bl_options = {"REGISTER", "UNDO"}
    # _last_obj = None

    _handle = None
    _highlight_face_index = None
    _highlight_obj = None

    states = (
        state_from_args(
            "Face",
            description="Pick a mesh face to project onto the sketch's surface.",
            use_create=False,
            pointer="face",
            types=(MeshPolygon,),
            interactive=True,
        ),
    )

    def main(self, context: Context):

        sse: SlvsEntities = context.scene.sketcher.entities

        # Gets info about clicked object
        obj_name, clicked_face_index = self.get_state_pointer(index=0, implicit=True)
        clicked_obj = get_evaluated_obj(context, bpy.data.objects[obj_name])

        # Gets face rotation
        obj_translation: TransformOrientation = clicked_obj.matrix_world
        projection_data = ProjectionData(
            sketcher_entities=sse,
            sketch=self.sketch,
            object_translation=obj_translation,
        )

        if not self.event.shift:
            # If SHIFT held, project the entire object
            self.project_from_interfaces(
                projection_data,
                [
                    ObjectInterface(clicked_obj),
                ],
            )
        else:
            # Otherwise project the selected face
            self.project_from_interfaces(
                projection_data,
                [
                    FaceInterface(clicked_obj, clicked_face_index),
                ],
            )
        # Theres also probably room to do a multi-select here.

        context.area.tag_redraw()  # Force re-draw of UI (Blender doesn't update after tool usage)
        return True

    def project_from_interfaces(
        self,
        projection_data: ProjectionData,
        object_interfaces: list[ObjectInterfaceProtocol],
        connect_lines: bool = True,
    ):
        sse = projection_data.sketcher_entities

        addedPoints = {}

        for object_interface in object_interfaces:
            for vertex in object_interface.get_verticies():
                x, y = project_vertex_to_workplane(
                    # FOCUS HERE
                    vertex_world=projection_data.object_translation @ vertex.co,
                    origin=projection_data.workplane_origin,
                    wp_quat=projection_data.workplane_quaternion,
                )

                point = sse.add_point_2d(
                    (x, y), projection_data.sketch, fixed=True, index_reference=True
                )
                addedPoints[vertex.index] = point

            if not connect_lines:
                continue

            # Takes the edges of the object and checks if
            # the earlier added sketch points are used in the edges.
            # If yes, then create line from first point to second point
            compareSet = set(addedPoints.keys())

            for edge in object_interface.get_edges():
                if not set(edge.vertices).issubset(compareSet):
                    continue

                p1, p2 = [addedPoints[x] for x in edge.vertices]
                sse.add_line_2d(
                    p1, p2, projection_data.sketch, fixed=True, index_reference=True
                )
        pass

    def evaluate_state(self, context: Context, event: Event, triggered):
        # Overriding evaluate state method to enable highlight behavior.
        # Theres likely a better way to do this, the UX isnt great.

        if event.type in {"RIGHTMOUSE", "ESC"}:
            return self._end(context, False)
        if event.type in {
            "LEFTMOUSE",
            "MOUSEMOVE",
            "INBETWEEN_MOUSEMOVE",
            "LEFT_SHIFT",
            "RIGHT_SHIFT",
        }:

            obj, _ = get_object_under_mouse(context=context, event=event)
            if event.type == "LEFTMOUSE":
                if obj is None:
                    return {"PASS_THROUGH"}

                return super().evaluate_state(
                    context=context, event=event, triggered=triggered
                )

            return {"PASS_THROUGH"}

        return self._end(context, False)

    def modal(self, context, event):
        is_mousemove = self._is_mousemove(event=event, reset=False)
        if is_mousemove:
            self._handle_highlight(context=context, event=event)

            return Operator2d.modal(self, context, event)

        return Operator2d.modal(self, context, event)

    def _handle_highlight(self, context, event):
        return handle_highlight(self=self, context=context, event=event)

    def fini(self, context, succeede):
        clear_highlight(context=context)


register, unregister = register_stateops_factory((View3D_OT_slvs_project_include,))

if __name__ == "__main__":
    register()
