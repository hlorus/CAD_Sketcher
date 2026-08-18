from typing import Any, Optional

import bpy
import numpy as np
from bpy.props import FloatVectorProperty
from bpy.types import Context

from .. import global_data
from ..drawing import selection
from ..model.types import SlvsGenericEntity, SlvsNormal3D, SlvsPoint2D, SlvsPoint3D
from ..serialize import scene_from_dict, scene_to_dict
from ..stateful_operator.integration import StatefulOperator
from .utilities import get_hovered


class GenericEntityOp(StatefulOperator):
    """Extend StatefulOperator with extension specific types"""

    def modal(self, context, event):
        # Alt+wheel cycles the hovered entity through the overlapping stack under
        # the cursor while drawing/constraining (issue #50). The preselection
        # gizmo keeps selection.hover_candidates current during the modal, so this
        # just steps hover; the next pick/commit reads it. Everything else falls
        # through to the normal stateful modal (plain wheel still navigates).
        if (
            event.value == "PRESS"
            and event.alt
            and event.type in {"WHEELUPMOUSE", "WHEELDOWNMOUSE"}
            and len(selection.hover_candidates) > 1
        ):
            direction = 1 if event.type == "WHEELUPMOUSE" else -1
            if selection.cycle_hover(direction, lock=True):
                if context.area:
                    context.area.tag_redraw()
                return {"RUNNING_MODAL"}

        # Alt+click: pick the next occluded candidate. Step hover, then fall
        # through so the normal LEFTMOUSE confirm commits the cycled entity
        # (check_event treats LEFTMOUSE-press as confirm regardless of Alt). If the
        # hover was just positioned with Alt+wheel, commit it instead of advancing.
        if (
            event.type == "LEFTMOUSE"
            and event.value == "PRESS"
            and event.alt
            and len(selection.hover_candidates) > 1
        ):
            if not selection.take_hover_lock():
                selection.cycle_hover(1)

        return super().modal(context, event)

    def check_event(self, event):
        # Shift = "place it raw": bypass both geometry snapping and inferred
        # auto-constraints.
        #  - Snapping is a live preview, so track Shift on every event.
        #  - Auto-constraints are applied at the confirm click, so capture Shift
        #    there (not sticky) — releasing Shift restores normal behaviour.
        global_data.snap_bypass = bool(event.shift)
        if (
            event.type in ("LEFTMOUSE", "RET", "NUMPAD_ENTER")
            and event.value == "PRESS"
        ):
            self.state_data["skip_auto_constraints"] = bool(event.shift)
        return super().check_event(event)

    def use_auto_constraints(self, context: Context, state_data=None) -> bool:
        """Whether inferred constraints should be added for this state.

        Combines the persistent "Auto Constraints" toggle with the per-state
        Shift bypass set in ``check_event``.
        """
        if state_data is None:
            state_data = self.state_data
        return context.scene.sketcher.auto_axis_constraints and not state_data.get(
            "skip_auto_constraints", False
        )

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
        hovered_cid = ""
        if not hovered and hasattr(self, "_check_constrain"):
            hover = selection.hover
            if hover and self._check_constrain(context, hover):
                hovered_cid = hover

        data["hovered"] = hovered_cid
        data["type"] = type(hovered) if hovered else None
        return hovered.curve_id if hovered else None

    def add_coincident(self, context: Context, point, state, state_data):
        if not self.use_auto_constraints(context, state_data):
            return
        hovered_cid = state_data.get("hovered", "")
        if hovered_cid and hasattr(self, "sketch") and self.sketch:
            from ..model.curve_ref import CurveRef

            point_cid = (
                point.curve_id
                if isinstance(point, CurveRef)
                else state_data.get("curve_id", "")
            )

            state_data["coincident"] = self.sketch.constraints.add_coincident(
                curve_id_1=point_cid,
                curve_id_2=hovered_cid,
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

        if any(
            [
                issubclass(t, (SlvsGenericEntity, CurveRef))
                for t in state.types
                if isinstance(t, type)
            ]
        ):
            return pointer_name + "_fallback"
        return ""

    def get_state_pointer(self, index: Optional[int] = None, implicit=False):
        retval = super().get_state_pointer(index=index, implicit=implicit)
        if retval:
            return retval

        if index is None:
            index = self.state_index

        data = self._state_data.get(index, {})
        if "type" not in data.keys():
            return None

        pointer_type = data["type"]
        if not pointer_type:
            return None

        from ..model.curve_ref import CurveRef

        if pointer_type is not None and issubclass(pointer_type, CurveRef):
            cid = data.get("curve_id", "")
            if implicit:
                return cid
            if not cid:
                return None
            from ..model.curve_ref import curve_ref
            from ..model.sketch_ref import get_active_sketch

            sketch = (
                self.sketch
                if hasattr(self, "sketch")
                else get_active_sketch(bpy.context)
            )
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

        data = self._state_data.get(index, {})
        pointer_type = data.get("type")
        if pointer_type is None:
            return None

        from ..model.curve_ref import CurveRef

        if issubclass(pointer_type, CurveRef):
            value = values[0] if values is not None else None
            if value is None:
                cid = ""
            elif implicit:
                cid = value
            elif isinstance(value, CurveRef):
                cid = value.curve_id
            else:
                cid = str(value)
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
        if sketch and selection.selected:
            from ..model.curve_ref import curve_ref

            for cid in selection.selected:
                ref = curve_ref(sketch, cid)
                if ref.valid:
                    selected.append(ref)
        return selected

    def on_before_redo_states(self, context: Context):
        selection.ignore_list.clear()

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
            domain_len = n_points if attr.domain == "POINT" else n_curves
            if attr.data_type == "FLOAT_VECTOR":
                data = np.zeros(domain_len * 3, dtype=np.float32)
                attr.data.foreach_get("vector", data)
            elif attr.data_type == "BOOLEAN":
                data = np.zeros(domain_len, dtype=np.bool_)
                attr.data.foreach_get("value", data)
            elif attr.data_type in ("INT", "INT8"):
                data = np.zeros(domain_len, dtype=np.int32)
                attr.data.foreach_get("value", data)
            elif attr.data_type in ("INT32_2D", "INT16_2D"):
                data = np.zeros(domain_len * 2, dtype=np.int32)
                attr.data.foreach_get("value", data)
            elif attr.data_type == "FLOAT":
                data = np.zeros(domain_len, dtype=np.float32)
                attr.data.foreach_get("value", data)
            elif attr.data_type == "STRING":
                from ..utilities.curve_data import get_str_attr

                data = [get_str_attr(attr, i) for i in range(domain_len)]
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
        if snapshot["n_curves"] == 0:
            if len(curve_data.curves) > 0:
                curve_data.remove_curves()
            return

        # Fast path: when the topology is unchanged (e.g. an interactive move,
        # which only shifts point positions), skip the expensive
        # remove_curves/add_curves rebuild and just overwrite the data in place.
        # This runs every mouse-move, so the rebuild otherwise scales the whole
        # sketch's geometry per frame.
        counts = snapshot["point_counts"]
        same_topology = len(curve_data.curves) == snapshot["n_curves"] and len(
            curve_data.points
        ) == int(counts.sum())
        if same_topology:
            cur_counts = np.zeros(len(curve_data.curves), dtype=np.int32)
            curve_data.curves.foreach_get("points_length", cur_counts)
            same_topology = np.array_equal(cur_counts, counts)

        if not same_topology:
            if len(curve_data.curves) > 0:
                curve_data.remove_curves()
            curve_data.add_curves(counts.tolist())
            curve_data.set_types(type="BEZIER")

        curve_data.points.foreach_set("position", snapshot["positions"])

        for name, attr_info in snapshot["attributes"].items():
            attr = curve_data.attributes.get(name)
            if not attr:
                attr = curve_data.attributes.new(
                    name, type=attr_info["type"], domain=attr_info["domain"]
                )
            if attr_info["type"] == "FLOAT_VECTOR":
                attr.data.foreach_set("vector", attr_info["data"])
            elif attr_info["type"] == "STRING":
                for i, v in enumerate(attr_info["data"]):
                    attr.data[i].value = v.encode() if isinstance(v, str) else v
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
        from ..model.sketch_ref import get_sketches
        from ..utilities.curve_data import invalidate_curve_id_cache

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
        scene = context.scene
        return {
            "scene": scene_to_dict(scene),
            "curves": self._snapshot_all_curves(context),
            # Dimensional constraint values live in scene["slvs:c:{uid}"] custom
            # properties, which the property-group serialization above does not
            # capture. Snapshot them explicitly so restore can put them back.
            "constraint_values": {
                k: scene[k] for k in scene.keys() if str(k).startswith("slvs:c:")
            },
        }

    def restore_snapshot(self, context: Context, snapshot: Any) -> None:
        """Restore sketcher state from serialized snapshot"""
        if not snapshot:
            return

        scene = context.scene
        scene_from_dict(scene, snapshot["scene"])
        self._restore_all_curves(context, snapshot.get("curves"))

        # Re-apply dimensional values LAST. Restoring the constraints fires the
        # `is_reference` update callback (assign_init_props), which re-measures
        # the constraint with not-yet-resolved geometry refs and clobbers the
        # stored value with 0. Overwriting from the snapshot repairs that. (#564)
        for key, value in snapshot.get("constraint_values", {}).items():
            scene[key] = value
