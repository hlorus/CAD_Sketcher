from typing import Optional, Any

import numpy as np
import bpy
from bpy.types import Context
from bpy.props import FloatVectorProperty

from .. import global_data
from ..stateful_operator.integration import StatefulOperator
from ..model.types import SlvsGenericEntity, SlvsPoint3D, SlvsPoint2D, SlvsNormal3D
from .utilities import get_hovered
from ..serialize import scene_to_dict, scene_from_dict


class GenericEntityOp(StatefulOperator):
    """Extend StatefulOperator with extension specific types"""

    def check_event(self, event):
        return super().check_event(event)

    def pick_element(self, context, coords):
        retval = super().pick_element(context, coords)
        if retval is not None:
            return retval

        state = self.state
        data = self.state_data

        hovered = get_hovered(context, *state.types)

        if hovered and self.is_in_previous_states(hovered):
            hovered = None

        # Set the hovered curve_id for constraining if not directly used
        hovered_cid = 0
        if not hovered and hasattr(self, "_check_constrain"):
            hover = global_data.hover
            if hover and self._check_constrain(context, hover):
                hovered_cid = hover

        data["hovered"] = hovered_cid
        data["type"] = type(hovered) if hovered else None
        return hovered.curve_id if hovered else None

    def add_coincident(self, context: Context, point, state, state_data):
        hovered_cid = state_data.get("hovered", 0)
        if hovered_cid and hasattr(self, "sketch") and self.sketch:
            from ..model.curve_ref import CurveRef
            point_cid = point.curve_id if isinstance(point, CurveRef) else state_data.get("curve_id", 0)

            state_data["coincident"] = self.sketch.constraints.add_coincident(
                curve_id_1=point_cid, curve_id_2=hovered_cid,
            )

    def has_coincident(self):
        for state_index, data in self._state_data.items():
            if data.get("coincident", None):
                return True
        return False

    @classmethod
    def register_properties(cls):
        super().register_properties()

        states = cls.get_states_definition()

        for s in states:
            if not s.pointer:
                continue

            name = s.pointer
            types = s.types

            annotations = {}
            if hasattr(cls, "__annotations__"):
                annotations = cls.__annotations__.copy()

            # handle SlvsPoint3D fallback props
            if any([t == SlvsPoint3D for t in types]):
                kwargs = {"size": 3, "subtype": "XYZ", "unit": "LENGTH"}
                annotations[name + "_fallback"] = FloatVectorProperty(
                    name=name, **kwargs
                )

            # handle SlvsPoint2D fallback props
            if any([t == SlvsPoint2D for t in types]):
                kwargs = {"size": 2, "subtype": "XYZ", "unit": "LENGTH"}
                annotations[name + "_fallback"] = FloatVectorProperty(
                    name=name, **kwargs
                )

            if any([t == SlvsNormal3D for t in types]):
                kwargs = {"size": 3, "subtype": "EULER", "unit": "ROTATION"}
                annotations[name + "_fallback"] = FloatVectorProperty(
                    name=name, **kwargs
                )

            for a in annotations.keys():
                if hasattr(cls, a):
                    raise NameError(
                        (
                            f"Class {cls} already has attribute of name {a},"
                            f"cannot register implicit pointer properties"
                        )
                    )
            setattr(cls, "__annotations__", annotations)

    def state_property(self, state_index):
        # Return state_prop / properties. Handle multiple types
        props = super().state_property(state_index)
        if props:
            return props

        state = self.get_states_definition()[state_index]

        pointer_name = state.pointer
        if not pointer_name:
            return ""

        from ..model.curve_ref import CurveRef
        if any([issubclass(t, (SlvsGenericEntity, CurveRef)) for t in state.types if isinstance(t, type)]):
            return pointer_name + "_fallback"
        return ""

    def get_state_pointer(self, index: Optional[int] = None, implicit=False):
        retval = super().get_state_pointer(index=index, implicit=implicit)
        if retval:
            return retval

        if index is None:
            index = self.state_index

        state = self.get_states_definition()[index]
        data = self._state_data.get(index, {})
        if "type" not in data.keys():
            return None

        pointer_type = data["type"]
        if not pointer_type:
            return None

        from ..model.curve_ref import CurveRef
        if pointer_type is not None and issubclass(pointer_type, CurveRef):
            cid = data.get("curve_id", 0)
            if implicit:
                return cid
            if not cid:
                return None
            from ..model.curve_ref import curve_ref
            from ..model.sketch_ref import get_active_sketch
            sketch = self.sketch if hasattr(self, "sketch") else get_active_sketch(bpy.context)
            return curve_ref(sketch, cid)

        if issubclass(pointer_type, SlvsGenericEntity):
            i = data.get("entity_index", -1)
            if implicit:
                return i
            if i == -1:
                return None
            return bpy.context.scene.sketcher.entities.get(i)

    def set_state_pointer(self, values, index=None, implicit=False):
        retval = super().set_state_pointer(values, index=index, implicit=implicit)
        if retval:
            return retval

        if index is None:
            index = self.state_index

        state = self.get_states_definition()[index]
        data = self._state_data.get(index, {})
        pointer_type = data.get("type")
        if pointer_type is None:
            return None

        from ..model.curve_ref import CurveRef
        if issubclass(pointer_type, CurveRef):
            value = values[0] if values is not None else None
            if value is None:
                cid = 0
            elif implicit:
                cid = value
            elif isinstance(value, CurveRef):
                cid = value.curve_id
            else:
                cid = int(value)
            data["curve_id"] = cid
            return True

        if issubclass(pointer_type, SlvsGenericEntity):
            value = values[0] if values is not None else None
            if value is None:
                i = -1
            elif implicit:
                i = value
            else:
                i = value.slvs_index
            data["entity_index"] = i
            return True

    def gather_selection(self, context: Context):
        # Return list filled with all selected verts/edges/faces/objects
        selected = super().gather_selection(context)

        from ..model.sketch_ref import get_active_sketch
        sketch = get_active_sketch(context)
        if sketch and global_data.selected:
            from ..model.curve_ref import curve_ref
            for cid in global_data.selected:
                ref = curve_ref(sketch, cid)
                if ref.valid:
                    selected.append(ref)
        return selected

    def on_before_redo_states(self, context: Context):
        global_data.ignore_list.clear()

    @staticmethod
    def _snapshot_curve_data(curve_data):
        """Snapshot a hair_curves object's geometry and attributes."""
        n_curves = len(curve_data.curves)
        if n_curves == 0:
            return {"n_curves": 0}

        n_points = len(curve_data.points)

        point_counts = np.zeros(n_curves, dtype=np.int32)
        curve_data.curves.foreach_get("points_length", point_counts)

        positions = np.zeros(n_points * 3, dtype=np.float32)
        curve_data.points.foreach_get("position", positions)

        attrs = {}
        for attr in curve_data.attributes:
            if attr.name == "position":
                continue
            domain_len = n_points if attr.domain == 'POINT' else n_curves
            if attr.data_type == 'FLOAT_VECTOR':
                data = np.zeros(domain_len * 3, dtype=np.float32)
                attr.data.foreach_get("vector", data)
            elif attr.data_type == 'BOOLEAN':
                data = np.zeros(domain_len, dtype=np.bool_)
                attr.data.foreach_get("value", data)
            elif attr.data_type in ('INT', 'INT8'):
                data = np.zeros(domain_len, dtype=np.int32)
                attr.data.foreach_get("value", data)
            elif attr.data_type == 'FLOAT':
                data = np.zeros(domain_len, dtype=np.float32)
                attr.data.foreach_get("value", data)
            else:
                continue
            attrs[attr.name] = {
                "data": data,
                "type": attr.data_type,
                "domain": attr.domain,
            }

        return {
            "n_curves": n_curves,
            "point_counts": point_counts,
            "positions": positions,
            "attributes": attrs,
        }

    @staticmethod
    def _restore_curve_data(curve_data, snapshot):
        """Restore a hair_curves object from a snapshot."""
        if len(curve_data.curves) > 0:
            curve_data.remove_curves()

        if snapshot["n_curves"] == 0:
            return

        curve_data.add_curves(snapshot["point_counts"].tolist())
        curve_data.set_types(type="BEZIER")
        curve_data.points.foreach_set("position", snapshot["positions"])

        for name, attr_info in snapshot["attributes"].items():
            attr = curve_data.attributes.get(name)
            if not attr:
                attr = curve_data.attributes.new(
                    name, type=attr_info["type"], domain=attr_info["domain"]
                )
            if attr_info["type"] == 'FLOAT_VECTOR':
                attr.data.foreach_set("vector", attr_info["data"])
            else:
                attr.data.foreach_set("value", attr_info["data"])

        curve_data.update_tag()

    @staticmethod
    def _snapshot_constraints(curve_data):
        """Snapshot constraint PropertyGroups on a Curves data block."""
        sc = curve_data.sketch_constraints
        snapshot = {}
        for data_coll in sc.get_lists():
            items = []
            for c in data_coll:
                item = {}
                for prop in c.rna_type.properties:
                    if prop.identifier == "rna_type":
                        continue
                    if prop.is_readonly:
                        continue
                    item[prop.identifier] = getattr(c, prop.identifier)
                # Also save custom properties
                for key in c.keys():
                    item["_custom_" + key] = c[key]
                items.append(item)
            if items:
                snapshot[c.type.lower() if items else ""] = items
        return snapshot

    @staticmethod
    def _restore_constraints(curve_data, snapshot):
        """Restore constraint PropertyGroups on a Curves data block."""
        if not snapshot:
            return
        sc = curve_data.sketch_constraints
        # Clear existing
        for data_coll in sc.get_lists():
            while len(data_coll) > 0:
                data_coll.remove(0)
        # Restore
        for coll_name, items in snapshot.items():
            data_coll = getattr(sc, coll_name, None)
            if data_coll is None:
                continue
            for item_data in items:
                c = data_coll.add()
                for key, value in item_data.items():
                    if key.startswith("_custom_"):
                        c[key[8:]] = value
                    elif hasattr(c, key):
                        try:
                            setattr(c, key, value)
                        except (AttributeError, TypeError):
                            pass

    def _snapshot_all_curves(self, context):
        """Snapshot curve data + constraints for all sketches."""
        from ..model.sketch_ref import get_sketches
        curve_snapshots = {}
        for sketch in get_sketches(context):
            obj = sketch.target_object
            if obj and obj.data:
                curve_snapshots[obj.name] = {
                    "curve_data": self._snapshot_curve_data(obj.data),
                    "constraints": self._snapshot_constraints(obj.data),
                }
            else:
                curve_snapshots[obj.name] = {
                    "curve_data": {"n_curves": 0},
                    "constraints": {},
                }
        return curve_snapshots

    def _restore_all_curves(self, context, curve_snapshots):
        """Restore curve data + constraints for all sketches."""
        from ..utilities.curve_data import invalidate_curve_id_cache
        from ..model.sketch_ref import get_sketches
        invalidate_curve_id_cache()

        if not curve_snapshots:
            return
        for sketch in get_sketches(context):
            obj = sketch.target_object
            if not obj or not obj.data:
                continue

            snap = curve_snapshots.get(obj.name)
            if snap:
                self._restore_curve_data(obj.data, snap["curve_data"])
                self._restore_constraints(obj.data, snap.get("constraints", {}))
            else:
                if len(obj.data.curves) > 0:
                    obj.data.remove_curves()

    def create_snapshot(self, context: Context) -> Any:
        """Create a complete snapshot of all sketcher state using serialization"""
        return {
            "scene": scene_to_dict(context.scene),
            "curves": self._snapshot_all_curves(context),
        }

    def restore_snapshot(self, context: Context, snapshot: Any) -> None:
        """Restore sketcher state from serialized snapshot"""
        if not snapshot:
            return

        scene_from_dict(context.scene, snapshot["scene"])
        self._restore_all_curves(context, snapshot.get("curves"))
