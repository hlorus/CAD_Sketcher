import logging
from typing import List

import bpy
from bpy.props import StringProperty, BoolProperty
from bpy.types import UILayout, Property, Context

from ..global_data import WpReq
from ..utilities import preferences
from ..declarations import Operators
from .constants import ENTITY_PROP_NAMES
from .base_entity import SlvsGenericEntity
from ..utilities.view import update_cb, refresh
from ..utilities.solver import update_system_cb
from ..utilities.bpy import setprop

logger = logging.getLogger(__name__)


class GenericConstraint:
    if bpy.app.version >= (5, 0):
        def _name_get_transform(self, curr_value, is_set):
            return curr_value if is_set else str(self)

        name: StringProperty(name="Name", get_transform=_name_get_transform)
    else:
        def _name_getter(self):
            return self.get("name", str(self))

        def _name_setter(self, new_name):
            self["name"] = new_name

        name: StringProperty(name="Name", get=_name_getter, set=_name_setter)
    failed: BoolProperty(name="Failed")
    constraint_uid: StringProperty(name="Constraint UID", default="")
    visible: BoolProperty(name="Visible", default=True, update=update_cb)
    is_reference = False  # Only DimensionalConstraint can be reference
    signature = ()
    props = ()

    def needs_wp(args):
        return WpReq.OPTIONAL

    def __str__(self):
        return self.label

    def get_workplane(self):
        # NOTE: this could also check through the constraints entity workplanes
        needs_wp = self.needs_wp()

        workplane = None
        if self.sketch_i != -1 and self.sketch:
            workplane = self.sketch.wp

        if workplane and needs_wp != WpReq.FREE:
            return workplane.py_data
        elif needs_wp == WpReq.NOT_FREE:
            return None
        else:
            import slvs

            return slvs.E_FREE_IN_3D

    def entities(self):
        props = []
        for prop_name in dir(self):
            if prop_name.endswith("_i") or not prop_name.startswith("entity"):
                continue
            entity = getattr(self, prop_name)
            if not entity:
                continue
            props.append(entity)
        return props

    def dependencies(self) -> List[SlvsGenericEntity]:
        deps = self.entities()
        if hasattr(self, "sketch"):
            s = self.sketch
            if s:
                deps.append(s)
        return deps

    # TODO: avoid duplicating code
    def update_pointers(self, index_old, index_new):
        def _update(name):
            prop = getattr(self, name)
            if prop == index_old:
                logger.debug(
                    "Update reference {} of {} to {}: ".format(name, self, index_new)
                )
                setattr(self, name, index_new)

        if hasattr(self, "sketch_i"):
            _update("sketch_i")

        for prop_name in dir(self):
            if not prop_name.startswith("entity") or not prop_name.endswith("_i"):
                continue
            _update(prop_name)

    def is_visible(self, context):
        if hasattr(self, "sketch"):
            return self.sketch.is_visible(context) and self.visible
        return self.visible

    def is_orphan(self):
        """Check if this constraint's sketch object has been deleted."""
        import bpy
        c_sketch_name = self.get("_sketch_object", "")
        if c_sketch_name:
            return bpy.data.objects.get(c_sketch_name) is None
        return False

    def is_active(self, active_sketch):
        if self.is_orphan():
            return False

        if not hasattr(self, "sketch"):
            return not active_sketch

        show_inactive = not preferences.use_experimental(
            "hide_inactive_constraints", True
        )
        if show_inactive:
            return True

        # Compare by sketch object name (new) or entity pointer (legacy)
        c_sketch_name = self.get("_sketch_object", "")
        if c_sketch_name and active_sketch:
            active_obj = active_sketch.target_object if hasattr(active_sketch, 'target_object') else active_sketch
            if active_obj:
                return c_sketch_name == active_obj.name
        return self.sketch == active_sketch

    def draw_plane(self):
        from mathutils import Vector

        sketch = self._get_sketch() if hasattr(self, '_get_sketch') else None
        if not sketch and self.sketch_i != -1 and self.sketch:
            sketch = self.sketch

        if sketch:
            wp_obj = getattr(sketch, 'workplane_object', None)
            if not wp_obj and hasattr(sketch, 'target_object') and sketch.target_object:
                wp_obj = sketch.target_object.parent
            if wp_obj:
                mat = wp_obj.matrix_world
                return mat.translation.copy(), Vector(mat.col[2][:3]).normalized()
            wp = getattr(sketch, 'wp', None)
            if wp:
                return wp.p1.location, wp.normal

        # Scene-level 3D dimensions are drawn in the local XY plane produced by
        # their matrix_basis(). Reuse that plane for label dragging so the gizmo
        # remains editable outside sketch mode as well.
        matrix_func = getattr(self, "matrix_basis", None)
        if callable(matrix_func):
            try:
                mat = matrix_func()
                normal = Vector(mat.col[2][:3])
                if normal.length:
                    return mat.translation.copy(), normal.normalized()
            except Exception:
                logger.debug("Could not resolve 3D constraint draw plane", exc_info=True)

        return None, None

    def copy(self, context, entities):
        # copy itself to another set of entities
        from .sketch_ref import get_active_constraints
        c = get_active_constraints(context).new_from_type(self.type)
        if hasattr(self, "sketch"):
            c.sketch = self.sketch
        if hasattr(self, "setting"):
            c.setting = self.setting
        if hasattr(self, "value"):
            c.value = self.value

        for prop, e in zip(ENTITY_PROP_NAMES, entities):
            setattr(c, prop, e)

        return c

    def draw_props(self, layout: UILayout):
        is_experimental = preferences.is_experimental()

        layout.prop(self, "name", text="")
        if self.failed:
            layout.label(text="Failed", icon="ERROR")

        layout.separator()
        if is_experimental:
            sub = layout.column()
            sub.scale_y = 0.8
            sub.label(text="Dependencies:")
            for e in self.dependencies():
                sub.label(text=str(e))

        layout.separator()
        layout.prop(self, "visible")
        layout.separator()
        return layout

    def index(self):
        return int(self.path_from_id().split("[")[1].split("]")[0])

    def placements(self):
        return []

    def curve_id_placements(self):
        ids = []
        if getattr(self, 'curve_id_1', ""):
            ids.append(self.curve_id_1)
        if getattr(self, 'curve_id_2', ""):
            ids.append(self.curve_id_2)
        if getattr(self, 'curve_id_3', ""):
            ids.append(self.curve_id_3)
        return ids

    def marker_position(self, sketch):
        return None

    def _get_sketch(self):
        sketch = self.sketch if hasattr(self, "sketch") and self.sketch else None
        if sketch:
            return sketch
        import bpy
        id_data = getattr(self, "id_data", None)
        if id_data and hasattr(id_data, "sketch_constraints"):
            for obj in bpy.data.objects:
                if obj.data is id_data:
                    from .sketch_ref import Sketch
                    return Sketch(obj)
            for obj in bpy.data.objects:
                if obj.data and obj.data.name == id_data.name:
                    from .sketch_ref import Sketch
                    return Sketch(obj)
        from .sketch_ref import get_active_sketch
        return get_active_sketch(bpy.context)

    def ref(self, n=1):
        cid = getattr(self, f"curve_id_{n}", "")
        if not cid:
            return None
        sketch = self._get_sketch()
        if not sketch:
            return None
        from .curve_ref import curve_ref
        return curve_ref(sketch, cid)

    def create_slvs_data(self, solvesys, **kwargs):
        raise NotImplementedError()

    def py_data(self, solvesys, **kwargs):
        return self.create_slvs_data(solvesys, **kwargs)


class DimensionalConstraint(GenericConstraint):

    value: Property
    setting: BoolProperty

    def _set_value(self, displayed_value: float):
        if not self.is_reference:
            self._set_value_force(self.from_displayed_value(displayed_value))

    def _get_scene(self):
        import bpy
        return bpy.context.scene

    def _set_value_force(self, value: float):
        scene = self._get_scene()
        uid = getattr(self, "constraint_uid", "")
        if scene is not None and uid:
            scene[f"slvs:c:{uid}"] = value

    def _get_value(self):
        if self.is_reference:
            val = self.init_props()["value"]
            return self.to_displayed_value(val)
        scene = self._get_scene()
        uid = getattr(self, "constraint_uid", "")
        if scene is not None and uid:
            key = f"slvs:c:{uid}"
            if key in scene:
                return self.to_displayed_value(float(scene[key]))
        val = self.init_props().get("value", 0.0)
        return self.to_displayed_value(val)

    def assign_settings(self, **settings):
        for key, value in settings.items():
            if value is None:
                continue
            if key == "value":
                setprop(self, key, value)
                continue
            try:
                current = getattr(self, key)
            except Exception:
                current = object()
            if current == value:
                continue
            setprop(self, key, value)

    def assign_init_props(self, context: Context = None, **kwargs):
        self.assign_settings(**self.init_props(**kwargs))

    def on_reference_checked(self, context: Context = None):
        update_system_cb(self, context)
        self.assign_init_props()
        refresh(context)
