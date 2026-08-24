import bpy
from bpy.types import Context, Operator
from bpy.utils import register_classes_factory

from .. import global_data
from ..declarations import Operators
from ..drawing import selection
from ..model.constants import SketchCurveType
from ..model.curve_ref import curve_ref
from ..model.sketch_ref import get_active_sketch
from ..utilities.curve_data import (
    UUID_FIELDS,
    get_curve_data,
    get_uuid,
    invalidate_curve_id_cache,
)


def _snapshot_curve(sketch, curve_id):
    """Snapshot a single curve's data for the copy buffer."""
    cd, idx, curve_slice = get_curve_data(sketch, curve_id)
    if cd is None:
        return None

    # Non-identity curve-domain attributes (skip hidden "."-prefixed ones,
    # which include the INT identity sub-attributes handled via rel_ids below).
    attrs = {}
    for attr in cd.attributes:
        if attr.domain == "CURVE" and not attr.name.startswith("."):
            v = attr.data[idx].value
            attrs[attr.name] = v.decode() if isinstance(v, bytes) else v

    # Logical relationship ids (hex), remapped to new ids on paste.
    rel_ids = {
        field: get_uuid(cd, field, idx) for field in UUID_FIELDS if field != "curve_id"
    }

    n_points = curve_slice.points_length
    first = curve_slice.points[0].index
    positions = []
    point_attrs = {}
    for attr in cd.attributes:
        if attr.domain == "POINT":
            point_attrs[attr.name] = []

    for i in range(n_points):
        pt_idx = first + i
        positions.append(tuple(cd.points[pt_idx].position))
        for attr in cd.attributes:
            if attr.domain == "POINT":
                if attr.data_type == "FLOAT_VECTOR":
                    point_attrs[attr.name].append(tuple(attr.data[pt_idx].vector))
                else:
                    point_attrs[attr.name].append(attr.data[pt_idx].value)

    return {
        "curve_id": curve_id,
        "rel_ids": rel_ids,
        "positions": positions,
        "curve_attrs": attrs,
        "point_attrs": point_attrs,
        "n_points": n_points,
    }


_CURVE_ID_FIELDS = ("curve_id_1", "curve_id_2", "curve_id_3")

# Never snapshot these: identity (minted fresh per paste), the auto-assigned
# name, and transient solver state. curve_id_N is the source of truth for a
# constraint's geometry; the ``*_i`` fields are derived entity/sketch indices
# whose stale values would drag curve_id_N back to the source on restore.
_SKIP_CONSTRAINT_PROPS = {"rna_type", "constraint_uid", "name", "failed"}


def _constraint_refs(c):
    """The curve_ids a constraint references (its geometry dependencies)."""
    return [cid for f in _CURVE_ID_FIELDS if (cid := getattr(c, f, ""))]


def snapshot_constraints(sketch, copied_ids):
    """Snapshot constraints whose every referenced curve was copied.

    Each snapshot keeps the constraint type, its semantic properties and any
    custom props. ``curve_id_*`` are remapped to the pasted copies on paste, and
    ``constraint_uid`` is dropped so each paste gets a fresh identity (and, for
    dimensional constraints, its own value slot rather than sharing the source's).
    """
    copied_ids = set(copied_ids)
    snaps = []
    for c in sketch.constraints.all:
        refs = _constraint_refs(c)
        if not refs or not all(r in copied_ids for r in refs):
            continue
        rna_names = {p.identifier for p in c.rna_type.properties}
        props = {}
        for prop in c.rna_type.properties:
            pid = prop.identifier
            if pid in _SKIP_CONSTRAINT_PROPS or pid.endswith("_i"):
                continue
            if prop.is_readonly:
                continue
            try:
                props[pid] = getattr(c, pid)
            except Exception:
                continue
        # Only genuine custom ID-props: c.keys() also lists the backing store of
        # defined StringProperties (curve_id_*, constraint_uid), and re-applying
        # those would clobber the remapped/fresh values set above.
        custom = {k: c[k] for k in c.keys() if k not in rna_names}
        snaps.append({"type": c.type.lower(), "props": props, "custom": custom})
    return snaps


def paste_constraints(sketch, snaps, id_map):
    """Recreate snapshotted constraints on the pasted geometry.

    ``id_map`` maps each copied curve_id to its pasted copy. Constraints get a
    fresh uid (and dimensional value endpoint); the source value is re-applied
    afterwards so the copy is independent of the original.
    """
    sc = sketch.constraints
    for snap in snaps:
        coll = getattr(sc, snap["type"], None)
        if coll is None:
            continue
        c = coll.add()
        deferred_value = None
        for key, val in snap["props"].items():
            if key in _CURVE_ID_FIELDS:
                setattr(c, key, id_map.get(val, "") if val else "")
            elif key == "value":
                # A dimensional value lives at scene[slvs:c:uid]; set it only
                # after the fresh uid + endpoint exist below.
                deferred_value = val
            else:
                try:
                    setattr(c, key, val)
                except (AttributeError, TypeError):
                    pass
        for key, val in snap["custom"].items():
            c[key] = val

        # Fresh identity so the copy doesn't share the source's uid (and value).
        c.constraint_uid = ""
        sc._init_constraint(c)
        if deferred_value is not None:
            try:
                c.value = deferred_value
            except (AttributeError, TypeError):
                pass


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

        if not selection.selected:
            return {"CANCELLED"}

        # Collect selected curve_ids and their point dependencies
        all_cids = set(selection.selected)
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

        # Snapshot constraints internal to the copied set (all their referenced
        # curves are copied), so paste carries the relationships too.
        copied_ids = {snap["curve_id"] for snap in buffer}
        constraints = snapshot_constraints(sketch, copied_ids)

        global_data.COPY_BUFFER = {"curves": buffer, "constraints": constraints}
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

        curves = buffer.get("curves", [])
        constraint_snaps = buffer.get("constraints", [])
        if not curves:
            return {"CANCELLED"}

        from ..utilities.curve_data import (
            _allocate_curve_id,
            ensure_sketch_curve_object,
            ensure_standard_attributes,
            set_attribute,
        )

        curve_data = ensure_sketch_curve_object(sketch)
        if not curve_data:
            return {"CANCELLED"}

        # Map old curve_ids to new ones
        id_map = {}
        for snap in curves:
            id_map[snap["curve_id"]] = _allocate_curve_id(sketch)

        # Create all pasted curves in one shot — calling add_curves/set_types/
        # ensure_standard_attributes per curve is O(curves²) as the sketch grows.
        selection.selected.clear()
        base_idx = len(curve_data.curves)
        curve_data.add_curves([snap["n_points"] for snap in curves])
        curve_data.set_types(type="BEZIER")
        ensure_standard_attributes(curve_data)

        for offset, snap in enumerate(curves):
            new_cid = id_map[snap["curve_id"]]

            curve_idx = base_idx + offset
            curve_slice = curve_data.curves[curve_idx]

            # Set positions
            for i, pos in enumerate(snap["positions"]):
                curve_data.points[curve_slice.points[i].index].position = pos

            # Identity: fresh curve_id + relationship ids remapped to the copies.
            set_attribute(curve_data.attributes, "curve_id", new_cid, curve_idx)
            for field, old_val in snap["rel_ids"].items():
                set_attribute(
                    curve_data.attributes, field, id_map.get(old_val, ""), curve_idx
                )

            # Other curve-domain attributes (name, sketch_type, flags, ...).
            for name, value in snap["curve_attrs"].items():
                attr = curve_data.attributes.get(name)
                if not attr:
                    continue
                if isinstance(value, str):
                    attr.data[curve_idx].value = value.encode()
                else:
                    attr.data[curve_idx].value = value

            # Set point-domain attributes
            for name, values in snap["point_attrs"].items():
                attr = curve_data.attributes.get(name)
                if not attr:
                    continue
                for i, val in enumerate(values):
                    pt_idx = curve_slice.points[i].index
                    if attr.data_type == "FLOAT_VECTOR":
                        attr.data[pt_idx].vector = val
                    else:
                        attr.data[pt_idx].value = val

            # Select pasted curves (skip points)
            ctype = snap["curve_attrs"].get("sketch_type", -1)
            if ctype != SketchCurveType.POINT:
                selection.selected.append(new_cid)

        invalidate_curve_id_cache(sketch)

        # Recreate the copied constraints on the pasted geometry (remapped ids).
        paste_constraints(sketch, constraint_snaps, id_map)

        curve_data.update_tag()
        context.area.tag_redraw()

        bpy.ops.view3d.slvs_move("INVOKE_DEFAULT")
        return {"FINISHED"}


register, unregister = register_classes_factory(
    (View3D_OT_slvs_copy, View3D_OT_slvs_paste)
)
