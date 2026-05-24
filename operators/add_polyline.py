import logging

import bpy
from bpy.types import Operator, Context
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..utilities.walker import EntityWalker

logger = logging.getLogger(__name__)


class View3D_OT_slvs_add_polyline(Operator):
    """Create a polyline from the currently selected sketch segments.

    Select two or more connected lines or arcs in the active sketch,
    then run this operator to group them into a SlvsPolyline entity.
    Closure is detected automatically.
    """

    bl_idname = Operators.AddPolyline
    bl_label = "Create Polyline"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: Context):
        sketch = context.scene.sketcher.active_sketch
        if sketch is None:
            return False
        sse = context.scene.sketcher.entities
        segments = [
            e
            for e in sse.selected_active
            if e.is_segment() and hasattr(e, "sketch") and e.sketch == sketch
        ]
        return len(segments) >= 2

    def execute(self, context: Context):
        sketch = context.scene.sketcher.active_sketch
        sse = context.scene.sketcher.entities

        segments = [
            e
            for e in sse.selected_active
            if e.is_segment() and hasattr(e, "sketch") and e.sketch == sketch
        ]

        if len(segments) < 2:
            self.report({"WARNING"}, "Select at least 2 connected segments")
            return {"CANCELLED"}

        # Use EntityWalker to find the connected path starting from the first segment
        walker = EntityWalker(context.scene, sketch, entity=segments[0])

        if not walker.paths:
            self.report({"ERROR"}, "Could not find a connected path from selection")
            return {"CANCELLED"}

        # Find the path that contains all selected segments
        target_path = None
        selected_indices = {e.slvs_index for e in segments}
        for path_entities, _ in walker.paths:
            path_indices = {e.slvs_index for e in path_entities}
            if selected_indices.issubset(path_indices):
                target_path = (path_entities, _)
                break

        if target_path is None:
            # Fall back to the first path
            target_path = walker.paths[0]
            logger.warning(
                "Selected segments do not all belong to one path; "
                "using the first connected path found."
            )

        path_entities, _ = target_path
        is_closed = EntityWalker.is_cyclic_path(path_entities)
        segment_indices = [e.slvs_index for e in path_entities]

        if len(segment_indices) > 32:
            self.report(
                {"WARNING"},
                "Path has {} segments; only the first 32 will be stored.".format(
                    len(segment_indices)
                ),
            )

        poly = sse.add_polyline(segment_indices, is_closed, sketch)
        logger.debug("Created {}".format(poly))
        return {"FINISHED"}


register, unregister = register_classes_factory((View3D_OT_slvs_add_polyline,))
