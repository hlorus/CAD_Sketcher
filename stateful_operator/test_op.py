from bpy.types import Operator, Context, Object, MeshVertex, MeshEdge, MeshPolygon

from .constants import Operators
from .integration import StatefulOperator
from .state import state_from_args

class View3D_OT_slvs_test(Operator, StatefulOperator):
    """Test stateful operator which prints picked mesh element"""

    bl_idname = Operators.Test
    bl_label = "Test StateOps"
    bl_options = {"REGISTER", "UNDO"}

    states = (
        state_from_args("ob", pointer="object", types=(Object,),),
        state_from_args(
            "Pick Element",
            description="Pick an element to print",
            pointer="element",
            types=(
                MeshVertex,
                MeshEdge,
                MeshPolygon,
            ),
        ),
    )

    def main(self, context: Context):
        element = self.element
        if element:
            self.report({"INFO"}, "Picked element " + str(element))
            return True
        return False