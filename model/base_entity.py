import logging
from typing import List

import gpu
from bpy.props import IntProperty, StringProperty, BoolProperty
from bpy.types import Context

from .. import global_data
from ..utilities import preferences
from ..shaders import Shaders
from ..declarations import Operators
from ..utilities.preferences import get_prefs
from ..utilities.index import index_to_rgb, breakdown_index
from ..utilities.view import update_cb
from ..utilities.solver import update_system_cb

logger = logging.getLogger(__name__)


class SlvsGenericEntity:
    def entity_name_getter(self):
        return self.get("name", str(self))

    def entity_name_setter(self, new_name):
        self["name"] = new_name

    slvs_index: IntProperty(name="Global Index", default=-1)
    name: StringProperty(
        name="Name",
        get=entity_name_getter,
        set=entity_name_setter,
        options={"SKIP_SAVE"},
    )
    fixed: BoolProperty(name="Fixed", update=update_system_cb)
    visible: BoolProperty(name="Visible", default=True, update=update_cb)
    origin: BoolProperty(name="Origin")
    construction: BoolProperty(name="Construction")
    props = ()
    dirty: BoolProperty(name="Needs Update", default=True, options={"SKIP_SAVE"})

    @classmethod
    @property
    def type(cls) -> str:
        return cls.__name__

    @property
    def is_dirty(self) -> bool:
        if self.dirty:
            return True

        if not hasattr(self, "dependencies"):
            return False
        deps = self.dependencies()
        for e in deps:
            # NOTE: might has to ckech through deps recursively -> e.is_dirty
            if e.dirty:
                return True
        return False

    @is_dirty.setter
    def is_dirty(self, value: bool):
        self.dirty = value

    @property
    def _shader(self):
        if self.is_point():
            return Shaders.uniform_color_3d()
        return Shaders.uniform_color_line_3d()

    @property
    def _id_shader(self):
        if self.is_point():
            return Shaders.id_shader_3d()
        return Shaders.id_line_3d()

    @property
    def point_size(self):
        return 5 * preferences.get_scale()

    @property
    def point_size_select(self):
        return 20 * preferences.get_scale()

    @property
    def line_width(self):
        scale = preferences.get_scale()
        if self.construction:
            return 1.5 * scale
        return 2 * scale

    @property
    def line_width_select(self):
        return 4 * preferences.get_scale()

    def __str__(self):
        _, local_index = breakdown_index(self.slvs_index)
        return "{}({})".format(self.__class__.__name__, str(local_index))

    @property
    def py_data(self):
        return global_data.entities[self.slvs_index]

    @py_data.setter
    def py_data(self, handle):
        global_data.entities[self.slvs_index] = handle

    # NOTE: It's not possible to store python runtime data on an instance of a PropertyGroup,
    # workaround this by saving python objects in a global list
    @property
    def _batch(self):
        index = self.slvs_index
        if index not in global_data.batches:
            return None
        return global_data.batches[index]

    @_batch.setter
    def _batch(self, value):
        global_data.batches[self.slvs_index] = value

    # NOTE: hover and select could be replaced by actual props with getter and setter funcs
    # selected: BoolProperty(name="Selected")

    @property
    def hover(self):
        return global_data.hover == self.slvs_index

    @hover.setter
    def hover(self, value):
        if value:
            global_data.hover = self.slvs_index
        else:
            global_data.hover = -1

    @property
    def selected(self):
        return self.slvs_index in global_data.selected

    @selected.setter
    def selected(self, value):
        slvs_index = self.slvs_index
        list = global_data.selected
        if slvs_index in list:
            i = list.index(slvs_index)
            if not value:
                list.pop(i)
        elif value:
            list.append(slvs_index)

    def is_active(self, active_sketch):
        if hasattr(self, "sketch"):
            return self.sketch == active_sketch
        else:
            return not active_sketch

    def is_selectable(self, context: Context):
        if not self.is_visible(context):
            return False

        if preferences.use_experimental("all_entities_selectable", False):
            return True

        active_sketch = context.scene.sketcher.active_sketch
        if active_sketch and hasattr(self, "sketch"):
            # Allow to select entities that share the active sketch's wp
            return active_sketch.wp == self.sketch.wp
        return self.is_active(active_sketch)

    def is_highlight(self):
        return self.hover or self in global_data.highlight_entities

    def color(self, context: Context):
        prefs = get_prefs()
        ts = prefs.theme_settings
        active = self.is_active(context.scene.sketcher.active_sketch)
        highlight = self.is_highlight()
        fixed = self.fixed
        origin = self.origin

        if not active:
            if highlight:
                return ts.entity.highlight
            if self.selected:
                return ts.entity.inactive_selected
            return ts.entity.inactive

        elif self.selected:
            if highlight:
                return ts.entity.selected_highlight
            return ts.entity.selected
        elif highlight:
            return ts.entity.highlight

        if fixed and not origin:
            return ts.entity.fixed
        return ts.entity.default

    @staticmethod
    def restore_opengl_defaults():
        gpu.state.line_width_set(1)
        gpu.state.point_size_set(1)
        gpu.state.blend_set("NONE")

    def is_visible(self, context: Context) -> bool:
        if self.origin:
            return context.scene.sketcher.show_origin

        if hasattr(self, "sketch"):
            return self.sketch.is_visible(context) and self.visible
        return self.visible

    def is_dashed(self):
        return False

    def draw(self, context):
        if not self.is_visible(context):
            return None

        batch = self._batch
        if not batch:
            return

        shader = self._shader
        shader.bind()

        gpu.state.blend_set("ALPHA")
        gpu.state.point_size_set(self.point_size)

        col = self.color(context)
        shader.uniform_float("color", col)

        if not self.is_point():
            shader.uniform_bool("dashed", (self.is_dashed(),))
            shader.uniform_float("dash_width", 0.05)
            shader.uniform_float("dash_factor", 0.3)
            gpu.state.line_width_set(self.line_width)

        batch.draw(shader)
        gpu.shader.unbind()
        self.restore_opengl_defaults()

    def draw_id(self, context):
        # Note: Design Question, should it be possible to select elements that are not active?!
        # e.g. to activate a sketch
        # maybe it should be dynamically defined what is selectable (points only, lines only, ...)

        batch = self._batch
        if not batch:
            return

        shader = self._id_shader
        shader.bind()

        gpu.state.point_size_set(self.point_size_select)

        shader.uniform_float("color", (*index_to_rgb(self.slvs_index), 1.0))
        if not self.is_point():
            # viewport = [context.area.width, context.area.height]
            # shader.uniform_float("Viewport", viewport)
            shader.uniform_bool("dashed", (False,))
            gpu.state.line_width_set(self.line_width_select)

        batch.draw(shader)
        gpu.shader.unbind()
        self.restore_opengl_defaults()

    def create_slvs_data(self, solvesys):
        """Create a solvespace entity from parameters"""
        raise NotImplementedError

    def update_from_slvs(self, solvesys):
        """Update parameters from the solvespace entity"""
        pass

    def update_pointers(self, index_old, index_new):
        def _update(name):
            prop = getattr(self, name)
            if prop == index_old:
                logger.debug(
                    "Update reference {} of {} to {}: ".format(name, self, index_new)
                )
                setattr(self, name, index_new)

        for prop_name in dir(self):
            if not prop_name.endswith("_i"):
                continue
            _update(prop_name)

        if hasattr(self, "target_object") and self.target_object:
            ob = self.target_object
            if ob.sketch_index == index_old:
                ob.sketch_index = index_new

    def connection_points(self):
        return []

    def dependencies(self) -> List["SlvsGenericEntity"]:
        return []

    def draw_props(self, layout):
        is_experimental = preferences.is_experimental()

        # Header
        layout.prop(self, "name", text="")

        # Info block
        layout.separator()
        layout.label(text="Type: " + type(self).__name__)
        layout.label(text="Is Origin: " + str(self.origin))

        if is_experimental:
            sub = layout.column()
            sub.scale_y = 0.8
            sub.label(text="Index: " + str(self.slvs_index))
            sub.label(text="Dependencies:")
            for e in self.dependencies():
                sub.label(text=str(e))

        # General props
        layout.separator()
        layout.prop(self, "visible")
        layout.prop(self, "fixed")
        layout.prop(self, "construction")

        # Specific prop
        layout.separator()
        sub = layout.column()

        # Delete
        layout.separator()
        layout.operator(Operators.DeleteEntity, icon="X").index = self.slvs_index

        return sub

    def tag_update(self, _context=None):
        # context argument ignored
        if not self.is_dirty:
            self.is_dirty = True

    def new(self, context: Context, **kwargs):
        """Create new entity based on this instance"""
        raise NotImplementedError

    @classmethod
    def is_3d(cls):
        return True

    @classmethod
    def is_2d(cls):
        return False

    @classmethod
    def is_point(cls):
        return False

    @classmethod
    def is_path(cls):
        return False

    @classmethod
    def is_line(cls):
        return False

    @classmethod
    def is_curve(cls):
        return False

    @classmethod
    def is_closed(cls):
        return False

    @classmethod
    def is_segment(cls):
        return False

    @classmethod
    def is_sketch(cls):
        return False


class Entity2D(SlvsGenericEntity):
    @property
    def wp(self):
        return self.sketch.wp

    @classmethod
    def is_3d(cls):
        return False

    @classmethod
    def is_2d(cls):
        return True
