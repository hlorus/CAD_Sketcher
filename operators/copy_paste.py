from copy import deepcopy
from ..model.sketch_ref import get_active_sketch

import bpy
from bpy.types import Context, Operator
from bpy.utils import register_classes_factory

from .. import global_data
from ..declarations import Operators
from ..model.curve_ref import curve_ref, PointRef, LineRef, ArcRef, CircleRef
from ..model.constants import SketchCurveType
from ..utilities.curve_data import get_curve_data, invalidate_curve_id_cache


def _snapshot_curve(sketch, curve_id):
    """Snapshot a single curve's data for the copy buffer."""
    cd, idx, curve_slice = get_curve_data(sketch, curve_id)
    if cd is None:
        return None

    attrs = {}
    for attr in cd.attributes:
        if attr.domain == 'CURVE':
            v = attr.data[idx].value
            attrs[attr.name] = v.decode() if isinstance(v, bytes) else v
        # Point-domain attrs stored per point

    n_points = curve_slice.points_length
    first = curve_slice.points[0].index
    positions = []
    point_attrs = {}
    for attr in cd.attributes:
        if attr.domain == 'POINT':
            point_attrs[attr.name] = []

    for i in range(n_points):
        pt_idx = first + i
        positions.append(tuple(cd.points[pt_idx].position))
        for attr in cd.attributes:
            if attr.domain == 'POINT':
                if attr.data_type == 'FLOAT_VECTOR':
                    point_attrs[attr.name].append(tuple(attr.data[pt_idx].vector))
                else:
                    point_attrs[attr.name].append(attr.data[pt_idx].value)

    return {
        "curve_id": curve_id,
        "positions": positions,
        "curve_attrs": attrs,
        "point_attrs": point_attrs,
        "n_points": n_points,
    }


class View3D_OT_slvs_copy(Operator):
    """Copy selected entities"""

    bl_idname = Operators.Copy
    bl_label = "Copy"
    bl_options = {"UNDO"}

    def execute(self, context: Context):
        sketch = get_active_sketch(context)
        if not sketch:
            self.report({"INFO"}, "Copying is not supported in 3d space")
            return {"CANCELLED"}

        if not global_data.selected:
            return {"CANCELLED"}

        # Collect selected curve_ids and their point dependencies
        all_cids = set(global_data.selected)
        for cid in list(all_cids):
            ref = curve_ref(sketch, cid)
            if not ref.valid:
                continue
            # Include relationship points
            for attr in ("start_point_id", "end_point_id", "center_point_id"):
                pt_cid = ref._get_attr_value(attr, 0)
                if pt_cid:
                    all_cids.add(pt_cid)

        # Snapshot each curve
        buffer = []
        for cid in all_cids:
            snap = _snapshot_curve(sketch, cid)
            if snap:
                buffer.append(snap)

        global_data.COPY_BUFFER = buffer
        return {"FINISHED"}


class View3D_OT_slvs_paste(Operator):
    """Paste copied entities"""

    bl_idname = Operators.Paste
    bl_label = "Paste"
    bl_options = {"UNDO"}

    def execute(self, context: Context):
        sketch = get_active_sketch(context)
        if not sketch:
            self.report({"INFO"}, "Pasting is not supported in 3d space")
            return {"CANCELLED"}

        buffer = global_data.COPY_BUFFER
        if not buffer:
            return {"CANCELLED"}

        from ..utilities.curve_data import (
            _allocate_curve_id, ensure_sketch_curve_object,
            ensure_standard_attributes, set_attribute,
        )

        curve_data = ensure_sketch_curve_object(sketch)
        if not curve_data:
            return {"CANCELLED"}

        # Map old curve_ids to new ones
        id_map = {}
        for snap in buffer:
            id_map[snap["curve_id"]] = _allocate_curve_id(sketch)

        # Create curves
        global_data.selected.clear()
        for snap in buffer:
            new_cid = id_map[snap["curve_id"]]
            n_points = snap["n_points"]

            curve_data.add_curves([n_points])
            curve_data.set_types(type="BEZIER")
            ensure_standard_attributes(curve_data)

            curve_idx = len(curve_data.curves) - 1
            curve_slice = curve_data.curves[curve_idx]

            # Set positions
            for i, pos in enumerate(snap["positions"]):
                curve_data.points[curve_slice.points[i].index].position = pos

            # Set curve-domain attributes
            from ..utilities.curve_data import _STRING_ATTRS
            for name, value in snap["curve_attrs"].items():
                attr = curve_data.attributes.get(name)
                if not attr:
                    continue
                if name == "curve_id":
                    v = new_cid.encode() if isinstance(new_cid, str) else new_cid
                    attr.data[curve_idx].value = v
                elif name in _STRING_ATTRS:
                    v = id_map.get(value, "")
                    attr.data[curve_idx].value = v.encode() if isinstance(v, str) else v
                else:
                    attr.data[curve_idx].value = value

            # Set point-domain attributes
            for name, values in snap["point_attrs"].items():
                attr = curve_data.attributes.get(name)
                if not attr:
                    continue
                for i, val in enumerate(values):
                    pt_idx = curve_slice.points[i].index
                    if attr.data_type == 'FLOAT_VECTOR':
                        attr.data[pt_idx].vector = val
                    else:
                        attr.data[pt_idx].value = val

            # Select pasted curves (skip points)
            ctype = snap["curve_attrs"].get("sketch_type", -1)
            if ctype != SketchCurveType.POINT:
                global_data.selected.append(new_cid)

        invalidate_curve_id_cache(sketch)
        curve_data.update_tag()
        context.area.tag_redraw()

        bpy.ops.view3d.slvs_move("INVOKE_DEFAULT")
        return {"FINISHED"}


register, unregister = register_classes_factory(
    (View3D_OT_slvs_copy, View3D_OT_slvs_paste)
)
