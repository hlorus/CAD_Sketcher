import logging
from typing import List

import bpy
import gpu
from bpy import app
from bpy.types import PropertyGroup
from bpy.props import (
    BoolProperty,
    IntProperty,
    IntVectorProperty,
)
from bpy.utils import register_classes_factory

from .. import global_data

from .base_entity import Entity2D
from .utilities import slvs_entity_pointer

logger = logging.getLogger(__name__)


class SlvsPolyline(Entity2D, PropertyGroup):
    """A named sequence of connected sketch segments forming an open or closed polyline.

    Groups lines/arcs drawn consecutively into a logical unit with optional
    BIM semantic tagging (SLAB, HOLE, WALL_RUN).

    Arguments:
        sketch (SlvsSketch): The sketch this polyline belongs to
    """

    segment_indices: IntVectorProperty(
        name="Segment Indices",
        description="slvs_index values of the member segments",
        size=32,
        default=(-1,) * 32,
    )
    segment_count: IntProperty(
        name="Segment Count",
        description="Number of active entries in segment_indices",
        default=0,
        min=0,
    )
    closed: BoolProperty(
        name="Closed",
        description="Whether this polyline forms a closed loop",
        default=False,
    )
    props = ()

    @property
    def selected(self):
        return self.slvs_index in global_data.selected

    @selected.setter
    def selected(self, value):
        # Toggle the polyline itself in the selection list
        idx = self.slvs_index
        lst = global_data.selected
        if idx in lst:
            if not value:
                lst.pop(lst.index(idx))
        elif value:
            lst.append(idx)
        # Propagate to member segments
        sse = bpy.context.scene.sketcher.entities
        for i in range(self.segment_count):
            seg_idx = int(self.segment_indices[i])
            if seg_idx == -1:
                continue
            seg = sse.get(seg_idx)
            if seg is not None:
                seg.selected = value

    def dependencies(self) -> List:
        sse = bpy.context.scene.sketcher.entities
        deps = []
        for i in range(self.segment_count):
            idx = int(self.segment_indices[i])
            if idx == -1:
                continue
            e = sse.get(idx)
            if e is not None:
                deps.append(e)
        sk = self.sketch
        if sk is not None:
            deps.append(sk)
        return deps

    def update(self):
        self.dirty = False

    def create_slvs_data(self, solvesys, group=None):
        pass

    def draw(self, context):
        if not self.is_visible(context):
            return
        if not (self.selected or self.is_highlight()):
            return

        from ..utilities.preferences import get_prefs

        prefs = get_prefs()
        ts = prefs.theme_settings
        col = ts.entity.selected if self.selected else ts.entity.highlight

        for seg in self.dependencies():
            if seg is self.sketch:
                continue
            batch = seg._batch
            if not batch:
                continue
            shader = seg._shader
            shader.bind()
            gpu.state.blend_set("ALPHA")
            shader.uniform_float("color", col)
            lw = seg.line_width_select
            gpu.state.line_width_set(lw)
            if seg.is_dashed():
                shader.uniform_bool("dashed", (False,))
            if app.version >= (4, 5):
                shader.uniform_float("lineWidth", lw)
                shader.uniform_float(
                    "viewportSize", (context.region.width, context.region.height)
                )
            batch.draw(shader)
            gpu.shader.unbind()
            gpu.state.line_width_set(1)
            gpu.state.blend_set("NONE")

    def draw_id(self, context):
        pass

    @classmethod
    def is_path(cls):
        return False

    @classmethod
    def is_segment(cls):
        return False

    def draw_props(self, layout):
        from ..utilities import preferences
        from ..declarations import Operators

        # Header
        layout.prop(self, "name", text="")

        # Info block
        layout.separator()
        layout.label(text="Type: " + type(self).__name__)
        layout.label(text="Is Origin: " + str(self.origin))
        layout.label(text="Is Closed: " + str(self.closed))
        layout.label(text="Segments: " + str(self.segment_count))

        if preferences.is_experimental():
            sub_exp = layout.column()
            sub_exp.scale_y = 0.8
            sub_exp.label(text="Index: " + str(self.slvs_index))
            sub_exp.label(text="Dependencies:")
            for e in self.dependencies():
                sub_exp.label(text=str(e))

        # General props
        layout.separator()
        layout.prop(self, "visible")
        layout.prop(self, "fixed")
        layout.prop(self, "construction")

        # Specific props
        layout.separator()
        sub = layout.column()

        # Delete
        layout.separator()
        layout.operator(Operators.DeleteEntity, icon="X").index = self.slvs_index
        return sub


slvs_entity_pointer(SlvsPolyline, "sketch")

register, unregister = register_classes_factory((SlvsPolyline,))
