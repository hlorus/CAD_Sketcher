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
    global REGION3D
    
    # Check if REGION3D is still available
    if REGION3D is None:
        return None  # Stop animation
    
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

    use_active: bpy.props.BoolProperty(name="Use Active Sketch", default=False)
    duration: bpy.props.FloatProperty(name="duration", default=0.3, min=0, max=2)


    def execute(self, context):
        global REGION3D, START_LOCATION, START_ROTATION, TARGET_MATRIX, START_TIME, DURATION

        REGION3D = context.region_data
        DURATION = self.duration

        # Check if region_data is available
        if REGION3D is None:
            self.report({'WARNING'}, "No 3D viewport available for alignment")
            return {'CANCELLED'}

        # Store the current location and rotation
        START_LOCATION = REGION3D.view_location.copy()
        START_ROTATION = REGION3D.view_rotation.copy()

        from ..model.sketch_ref import get_active_sketch
        sketch = get_active_sketch(context) if self.use_active else None

        if sketch:
            wp_obj = sketch.workplane_object
            if not wp_obj and sketch.target_object and sketch.target_object.parent:
                wp_obj = sketch.target_object.parent
            if wp_obj:
                TARGET_MATRIX = wp_obj.matrix_world.copy()
            else:
                TARGET_MATRIX = mathutils.Matrix.Identity(4)
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
