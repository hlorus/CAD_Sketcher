import logging
from collections import Counter

import bpy
from bpy.types import Operator, Context
from bpy.utils import register_classes_factory

from ..declarations import Operators

logger = logging.getLogger(__name__)


def _endpoints(seg):
    """Return the (p1, p2) endpoint entities of a segment, or (None, None)."""
    if hasattr(seg, "p1") and hasattr(seg, "p2"):
        return seg.p1, seg.p2
    return None, None


def _chain_segments(segments):
    """Sort segments into a connected chain using only the given segments.

    Returns (ordered_segments, is_closed).
    Any segments that cannot be connected are appended at the end in list order.
    """
    if not segments:
        return [], False

    remaining = list(segments)
    ordered = [remaining.pop(0)]

    changed = True
    while remaining and changed:
        changed = False
        _, tail = _endpoints(ordered[-1])
        for seg in list(remaining):
            p1, p2 = _endpoints(seg)
            if p1 is None:
                continue
            if tail is not None and p1 == tail:
                ordered.append(seg)
                remaining.remove(seg)
                changed = True
                break
            if tail is not None and p2 == tail:
                # Segment is reversed — still add it; direction lives in entity
                ordered.append(seg)
                remaining.remove(seg)
                changed = True
                break

    ordered.extend(remaining)  # attach any disconnected stragglers

    # Detect closure: every endpoint appears exactly twice in the chain
    all_pts = []
    for s in ordered:
        p1, p2 = _endpoints(s)
        if p1 is not None:
            all_pts.extend([p1, p2])
    is_closed = len(ordered) >= 2 and all(v == 2 for v in Counter(all_pts).values())

    return ordered, is_closed


class View3D_OT_slvs_add_polyline(Operator):
    """Create a polyline from the currently selected sketch segments.

    Select two or more connected lines or arcs in the active sketch,
    then run this operator to group them into a SlvsPolyline entity.
    Only the selected segments are used; closure is detected automatically.
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

        # Collect selected segments in entity-list order (stable, predictable)
        segments = [
            e
            for e in sse.all
            if e.is_segment()
            and hasattr(e, "sketch")
            and e.sketch == sketch
            and e.selected
        ]

        if len(segments) < 2:
            self.report({"WARNING"}, "Select at least 2 connected segments")
            return {"CANCELLED"}

        ordered, is_closed = _chain_segments(segments)
        segment_indices = [e.slvs_index for e in ordered]

        if len(segment_indices) > 32:
            self.report(
                {"WARNING"},
                "Path has {} segments; only the first 32 will be stored.".format(
                    len(segment_indices)
                ),
            )
            segment_indices = segment_indices[:32]

        poly = sse.add_polyline(segment_indices, is_closed, sketch)
        logger.debug("Created {}".format(poly))
        return {"FINISHED"}


register, unregister = register_classes_factory((View3D_OT_slvs_add_polyline,))
