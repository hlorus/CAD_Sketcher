"""
Add integration with native blender types, following are supported:

- bpy.types.Object
- bpy.types.MeshVertex
- bpy.types.MeshEdge
- bpy.types.MeshPolygon
"""


from typing import Optional

import bpy
from bpy.types import Context

from .constants import mesh_element_types
from .logic import StatefulOperatorLogic
from .utilities.generic import get_pointer_get_set, to_list
from .utilities.geometry import (
    get_evaluated_obj,
    get_mesh_element,
    get_placement_pos,
    get_scale_from_pos,
)


class PointerKind:
    """Handles one family of pointer types for get/set_state_pointer.

    A pointer state stores a picked element's identity in ``_state_data``; the
    handler that ``handles`` the stored ``type`` knows how to read it back
    (``resolve``), write it (``store``), and which concrete type names it can
    rebuild on redo (``type_registry``). Registering handlers (see
    ``_pointer_handlers``) replaces the old per-type if/elif chains and the
    call-super-then-fall-through ladder between the native and extension layers.
    """

    # Base types this handler owns (matched by issubclass).
    types = ()

    def handles(self, ptype):
        return isinstance(ptype, type) and issubclass(ptype, self.types)

    def type_registry(self):
        """Concrete type name -> class, for rebuilding data['type'] on redo."""
        return {t.__name__: t for t in self.types}

    def resolve(self, op, data, implicit):
        """Return the pointer value: the implicit id, or the resolved element."""
        raise NotImplementedError

    def store(self, op, data, values, implicit):
        """Write the pointer identity from ``values`` into ``data``."""
        raise NotImplementedError


class ObjectPointer(PointerKind):
    types = (bpy.types.Object,)

    def resolve(self, op, data, implicit):
        obj_name = data.get("object_name")
        if not obj_name:
            return None
        blender_obj = bpy.data.objects.get(obj_name)
        if blender_obj is None:
            return None
        if implicit:
            return obj_name
        return get_evaluated_obj(bpy.context, blender_obj)

    def store(self, op, data, values, implicit):
        v = values[0] if values else None
        data["object_name"] = v if (implicit or v is None) else v.name
        return True


class MeshElementPointer(PointerKind):
    types = mesh_element_types  # (MeshVertex, MeshEdge, MeshPolygon)

    def resolve(self, op, data, implicit):
        obj_name = data.get("object_name")
        blender_obj = bpy.data.objects.get(obj_name) if obj_name else None
        if blender_obj is None:
            return None
        index = data.get("mesh_index")
        if implicit:
            return obj_name, index
        obj = get_evaluated_obj(bpy.context, blender_obj)
        ptype = data["type"]
        if ptype is bpy.types.MeshVertex:
            return obj.data.vertices[index]
        if ptype is bpy.types.MeshPolygon:
            return obj.data.polygons[index]
        # MeshEdge
        edges = getattr(obj.data, "edges", None)
        if edges is None:
            # A curve/sketch edge has no mesh edge to return; hand back the
            # object so the pointer still reads as "set" (the picker resolves
            # the actual endpoints from the stored index).
            return obj
        if index >= len(edges):
            return None
        return edges[index]

    def store(self, op, data, values, implicit):
        v0 = values[0] if values else None
        v1 = values[1] if values and len(values) > 1 else None
        data["object_name"] = v0 if (implicit or v0 is None) else v0.name
        data["mesh_index"] = v1 if (implicit or v1 is None) else v1.index
        return True


_NATIVE_POINTER_KINDS = (ObjectPointer(), MeshElementPointer())


class StatefulOperator(StatefulOperatorLogic):
    """Extends logic class with native blender integration"""

    @classmethod
    def register_properties(cls):
        from bpy.props import BoolProperty, IntProperty, StringProperty

        states = cls.get_states_definition()
        annotations = cls.__annotations__.copy()

        for i, s in enumerate(states):
            pointer_name = s.pointer

            if not pointer_name:
                continue

            if pointer_name in annotations.keys():
                # Skip pointers that have a property defined
                # Note: pointer might not need implicit props, thus no need for getter/setter
                continue

            if hasattr(cls, pointer_name):
                # This can happen when the addon is re-enabled in the same session
                continue

            get, set = get_pointer_get_set(i)
            setattr(cls, pointer_name, get)
            # Note: keep state pointers read-only, only set with set_state_pointer()

        for a in annotations.keys():
            if hasattr(cls, a):
                raise NameError(
                    "Cannot register implicit pointer properties, class {} already has attribute of name {}".format(
                        cls, a
                    )
                )

        # Hidden per-pointer-state persistence props so the redo/execute path
        # can rebuild the picked pointer on a fresh instance where the transient
        # _state_data is gone (see logic._store_pointers / _restore_pointers).
        for i, s in enumerate(states):
            if not s.pointer:
                continue
            annotations.setdefault("ptr%d_kind" % i, StringProperty(options={"HIDDEN"}))
            annotations.setdefault("ptr%d_existing" % i, BoolProperty(options={"HIDDEN"}))
            annotations.setdefault("ptr%d_name" % i, StringProperty(options={"HIDDEN"}))
            annotations.setdefault(
                "ptr%d_index" % i, IntProperty(default=-1, options={"HIDDEN"})
            )
        setattr(cls, "__annotations__", annotations)

    def state_property(self, state_index):
        return None

    # -- pointer handlers -----------------------------------------------------

    def _pointer_handlers(self):
        """The pointer-kind handlers, most specific first. The extension layer
        appends its entity/curve-ref handlers via super()."""
        return _NATIVE_POINTER_KINDS

    def _pointer_handler_for(self, ptype):
        for handler in self._pointer_handlers():
            if handler.handles(ptype):
                return handler
        return None

    def _pointer_type_registry(self):
        registry = {}
        for handler in self._pointer_handlers():
            registry.update(handler.type_registry())
        return registry

    def get_state_pointer(
        self, index: Optional[int] = None, implicit: Optional[bool] = False
    ):
        # Rebuild the pointer value from its implicitly stored identity.
        if index is None:
            index = self.state_index
        data = self._state_data.get(index, {})
        ptype = data.get("type")
        if not ptype:
            return None
        handler = self._pointer_handler_for(ptype)
        if handler is None:
            return None
        return handler.resolve(self, data, implicit)

    def set_state_pointer(self, values, index=None, implicit=False):
        if index is None:
            index = self.state_index
        data = self._state_data.get(index, {})
        ptype = data.get("type")
        if ptype is None:
            return None
        handler = self._pointer_handler_for(ptype)
        if handler is None:
            return None
        return handler.store(self, data, values, implicit)

    def state_func(self, context: Context, coords):
        pos = get_placement_pos(context, coords)

        prop_name = self.state.property
        prop = self.rna_type.properties.get(prop_name)
        if not prop:
            return super().state_func(context, coords)

        if prop.array_length > 1:
            return pos

        if prop.type in ("FLOAT", "INT"):
            # Take the delta between the state start position and current position in screenspace X-Axis
            # and scale the value by the zoom level at the state start position

            type_cast = float if prop.type == "FLOAT" else int
            old_pos = get_placement_pos(context, self.state_init_coords)
            scale = get_scale_from_pos(old_pos, context.region_data) / 500

            # NOTE: self.state_init_coords is not set for non-interactive states
            return type_cast((coords.x - self.state_init_coords.x) * scale)

        return super().state_func(context, coords)

    def pick_element(self, context: Context, coords):
        # return a list of implicit prop values if pointer need implicit props
        state = self.state
        data = self.state_data

        types = {
            "vertex": (bpy.types.MeshVertex in state.types),
            "edge": (bpy.types.MeshEdge in state.types),
            "face": (bpy.types.MeshPolygon in state.types),
        }

        do_object = bpy.types.Object in state.types
        do_mesh_elem = any(types.values())

        if not do_object and not do_mesh_elem:
            return

        ob, element_type, index = get_mesh_element(context, coords, **types)

        # NOTE: scene.ray_cast() cannot pick empties (no geometry).
        # Empties are picked via custom ID buffer or selection prefill.

        if not ob:
            return None

        if bpy.types.Object in state.types:
            data["type"] = bpy.types.Object
            return ob.name

        # element_type is None when the ray hit an object but no vertex/edge/face
        # landed within threshold. For a mesh-element state that's a miss --
        # return None so callers can fall back (e.g. the curve-edge revolve axis).
        type_map = {
            "VERTEX": bpy.types.MeshVertex,
            "EDGE": bpy.types.MeshEdge,
            "FACE": bpy.types.MeshPolygon,
        }
        if element_type not in type_map:
            return None
        data["type"] = type_map[element_type]

        return ob.name, index

    def gather_selection(self, context: Context):
        # Return list filled with all selected verts/edges/faces/objects
        selected = []
        states = self.get_states()
        types = []
        for s in states:
            types.extend(s.types)

        # Note: Where to take mesh elements from? Editmode data is only written
        # when left probably making it impossible to use selected elements in realtime.
        if any([t == bpy.types.Object for t in types]):
            selected.extend(context.selected_objects)

        return selected

    # Gets called for every state
    def parse_selection(self, context, selected, index=None):
        # Look for a valid element in selection
        # should go through objects, vertices, entities depending on state.types

        result = None
        if index is None:
            index = self.state_index
        # Use the operator-aware state list so per-state ``get_types`` narrowing
        # (e.g. an EQUAL slot restricted once the other slot is picked) applies
        # during selection prefill, exactly as it does for interactive picking.
        state = self.get_states()[index]
        data = self.get_state_data(index)

        if state.pointer:
            types = state.types
            for i, e in enumerate(selected):
                if self._matches_types(e, types):
                    result = selected.pop(i)
                    break

        if result:
            data["type"] = type(result)
            self.set_state_pointer(to_list(result), index=index)
            self.state_data["is_existing_entity"] = True
            return True

    @staticmethod
    def _matches_types(element, types):
        """Check if element matches accepted types (supports both entities and CurveRefs)."""
        if type(element) in types:
            return True

        # Map CurveRef types to legacy entity types
        from ..model.curve_ref import (
            ArcRef,
            CircleRef,
            CurveRef,
            LineRef,
            PointRef,
        )
        if not isinstance(element, CurveRef):
            return False

        from ..model.types import (
            SlvsArc,
            SlvsCircle,
            SlvsLine2D,
            SlvsPoint2D,
        )
        _map = {
            PointRef: SlvsPoint2D,
            LineRef: SlvsLine2D,
            ArcRef: SlvsArc,
            CircleRef: SlvsCircle,
        }
        mapped = _map.get(type(element))
        return mapped in types if mapped else False

    # True -> expose an eyedropper next to picked pointer states in the redo
    # panel that re-enters this op to edit just that state (edit_state re-entry).
    editable = False

    def _declared_prop_names(self):
        names = set()
        for klass in type(self).__mro__:
            names.update(klass.__dict__.get("__annotations__", {}))
        return names

    def _pointer_repick_label(self, i):
        """Label for a picked pointer, read from its persisted props."""
        kind = getattr(self, "ptr%d_kind" % i, "")
        name = getattr(self, "ptr%d_name" % i, "")
        index = getattr(self, "ptr%d_index" % i, -1)
        if name and index >= 0:
            return "%s [%d]" % (name, index)
        if name:
            return name
        if index >= 0:
            return "%s #%d" % (kind or "Element", index)
        return kind or "-"

    def _state_is_editable(self, i, state):
        """Whether state ``i`` offers a redo-panel eyedropper to re-pick it.
        Default: the op's ``editable`` flag applies to every picked pointer.
        Subclasses can restrict it (e.g. to object pointers only)."""
        return self.editable

    def _draw_state_row(self, layout, i, state):
        """Draw one state's redo-panel row: a picked pointer (label + eyedropper
        to re-pick) or the state's editable property."""
        # A picked pointer is rendered from its persisted identity (which
        # survives into the redo panel, unlike the transient _state_data).
        picked = state.pointer and getattr(self, "ptr%d_existing" % i, False)
        if picked and getattr(self, "ptr%d_kind" % i, ""):
            row = layout.row(align=True)
            row.label(text=self._pointer_repick_label(i))
            if self._state_is_editable(i, state):
                # Re-enter THIS op to edit just state i. Use the class bl_idname
                # (dotted, via the str-Enum .value); the instance form is the RNA
                # identifier which layout.operator won't accept. Forward the op's
                # current props so it restores full state, then edits state i.
                idname = getattr(type(self).bl_idname, "value", type(self).bl_idname)
                op = row.operator(idname, text="", icon="EYEDROPPER")
                for name in self._declared_prop_names():
                    if name == "edit_state" or name.startswith("_"):
                        continue
                    try:
                        val = getattr(self, name)
                    except (AttributeError, TypeError):
                        continue
                    if hasattr(val, "__len__") and not isinstance(val, str):
                        val = tuple(val)
                    try:
                        setattr(op, name, val)
                    except (AttributeError, TypeError):
                        pass
                op.edit_state = i
            return

        props = self.get_property(index=i)
        if props:
            for p in props:
                layout.prop(self, p, text="")

    def draw(self, context):
        layout = self.layout

        for i, state in enumerate(self.get_states()):
            if i != 0:
                layout.separator()
            layout.label(text=state.name)
            self._draw_state_row(layout, i, state)

        if hasattr(self, "draw_settings"):
            self.draw_settings(context)

    def create_snapshot(self, context: Context):
        """Snapshot relevant Blender data references"""
        return None

    def restore_snapshot(self, context: Context, snapshot):
        """Restore Blender references - mostly validation"""
        pass
