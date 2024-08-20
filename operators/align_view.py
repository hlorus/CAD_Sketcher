import bpy
import mathutils

import time
import logging

from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory

logger = logging.getLogger(__name__)


START_TIME = 0
DURATION = 1.0
REGION3D = None
START_LOCATION = None
START_ROTATION = None
TARGET_MATRIX = None


def animate_viewport():
    # Calculate the elapsed time
    elapsed_time = time.time() - START_TIME
    t = min(elapsed_time / DURATION, 1.0)  # Normalize time to [0, 1]

    # Interpolate the location and rotation
    REGION3D.view_location = START_LOCATION.lerp(TARGET_MATRIX.translation, t)
    REGION3D.view_rotation = START_ROTATION.slerp(TARGET_MATRIX.to_quaternion(), t)

    # Continue the animation if not finished
    if t < 1.0:
        return 0.02  # Continue the timer



class View3D_OT_slvs_align_view(bpy.types.Operator):
    bl_idname = Operators.AlignView
    bl_label = "Align View to Sketch"
    bl_description = "Align the viewport to a given sketch"
    bl_options = {'UNDO'}

    sketch_index: bpy.props.IntProperty(name="Sketch Index", default=-1, description="Index of the sketch to align to, -1 for default view")
    use_active: bpy.props.BoolProperty(name="Use Active Sketch", default=False, description="Use the active sketch instead of the index")
    duration: bpy.props.FloatProperty(name="duration", default=0.3, min=0, max=2, description="Duration of the animation in seconds")


    def execute(self, context):
        global REGION3D, START_LOCATION, START_ROTATION, TARGET_MATRIX, START_TIME, DURATION

        REGION3D = context.region_data
        DURATION = self.duration

        # Store the current location and rotation
        START_LOCATION = REGION3D.view_location.copy()
        START_ROTATION = REGION3D.view_rotation.copy()

        sketcher = context.scene.sketcher
        sketch = sketcher.active_sketch if self.use_active else sketcher.entities.get(self.sketch_index)

        if sketch:
            TARGET_MATRIX = sketch.wp.matrix_basis
            REGION3D.view_perspective = "ORTHO"
        else:
            # Restore the viewport to its default
            TARGET_MATRIX = mathutils.Quaternion((0.7123758792877197, 0.4410620927810669, 0.28735825419425964, 0.4641229212284088)).to_matrix().to_4x4()
            REGION3D.view_perspective = "PERSP"

        # Start the animation
        START_TIME = time.time()
        bpy.app.timers.register(animate_viewport)

        return {'FINISHED'}



register, unregister = register_stateops_factory((View3D_OT_slvs_align_view,))