import logging

from bpy.types import Operator, Context

from ..model.curve_ref import CurveRef, curve_ref
from ..model.sketch_ref import get_active_sketch
from ..model.categories import SEGMENT
from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from ..stateful_operator.state import state_from_args
from ..utilities.trimming import TrimSegment
from ..utilities.curve_data import get_uuid, has_uuid_field
from .base_2d import Operator2d
from ..utilities.view import refresh, get_pos_2d

logger = logging.getLogger(__name__)


class View3D_OT_slvs_trim(Operator, Operator2d):
    """Trim segment to its closest intersections"""

    bl_idname = Operators.Trim
    bl_label = "Trim Segment"
    bl_options = {"REGISTER", "UNDO"}

    trim_state1_doc = ("Segment", "Segment to trim.")

    states = (
        state_from_args(
            trim_state1_doc[0],
            description=trim_state1_doc[1],
            pointer="segment",
            types=SEGMENT,
            pick_element="pick_element_coords",
            use_create=False,
        ),
    )

    def pick_element_coords(self, context, coords):
        data = self.state_data
        data["mouse_pos"] = get_pos_2d(context, self._get_wp(), coords)
        return super().pick_element(context, coords)

    @staticmethod
    def _delete_segment(context, sketch, segment):
        """Delete a segment and its orphan endpoints."""
        from ..operators.delete_entity import _get_constraint_indices_for_curve_id
        from ..utilities.curve_data import remove_native_curve_by_id
        from ..model.constants import SketchCurveType

        # Collect endpoint curve_ids
        endpoint_cids = set()
        for attr in ("start_point_id", "end_point_id"):
            pt_cid = segment._get_attr_value(attr, 0)
            if pt_cid:
                endpoint_cids.add(pt_cid)

        # Remove constraints referencing this segment
        for data_coll, indices in _get_constraint_indices_for_curve_id(segment.curve_id, context):
            for i in reversed(indices):
                data_coll.remove(i)

        # Remove the segment
        segment.remove()

        # Check which endpoints are now orphans
        cd = sketch.data
        if not cd:
            return
        n = len(cd.curves)

        referenced = set()
        type_attr = cd.attributes.get("sketch_type")
        for i in range(n):
            if type_attr and type_attr.data[i].value == SketchCurveType.POINT:
                continue
            referenced.add(get_uuid(cd, "start_point_id", i))
            referenced.add(get_uuid(cd, "end_point_id", i))
            referenced.add(get_uuid(cd, "center_point_id", i))

        for cid in endpoint_cids:
            if cid not in referenced:
                remove_native_curve_by_id(sketch, cid)

    def main(self, context: Context):
        return True

    def fini(self, context: Context, succeede: bool):
        if not succeede:
            return False

        sketch = get_active_sketch(context)
        segment = self.segment

        if not segment or not isinstance(segment, CurveRef):
            return False

        mouse_pos = self._state_data[0].get("mouse_pos")
        if mouse_pos is None:
            return False

        topo = sketch.topology

        # Create trim manager
        trim = TrimSegment(sketch, segment, mouse_pos, topo)

        # Find intersections with all other segments
        from ..model.constants import SketchCurveType
        cd = sketch.data
        type_attr = cd.attributes.get("sketch_type")

        if has_uuid_field(cd, "curve_id") and type_attr:
            for i in range(len(cd.curves)):
                ctype = type_attr.data[i].value
                if ctype == SketchCurveType.POINT:
                    continue
                cid = get_uuid(cd, "curve_id", i)
                if cid == segment.curve_id:
                    continue

                other = curve_ref(sketch, cid)
                if not other.valid:
                    continue

                for co in topo.intersect(segment, other):
                    trim.add(co, source_cid=cid)

        # Find coincident/midpoint constraints on this segment
        sc = sketch.constraints
        for coll_name in ("coincident", "midpoint"):
            coll = getattr(sc, coll_name, None)
            if not coll:
                continue
            for j, c in enumerate(coll):
                c1 = getattr(c, "curve_id_1", "")
                c2 = getattr(c, "curve_id_2", "")
                if segment.curve_id not in (c1, c2):
                    continue
                # The other curve_id is the point
                pt_cid = c1 if c2 == segment.curve_id else c2
                if pt_cid:
                    from ..model.curve_ref import PointRef
                    pt = PointRef(sketch, pt_cid)
                    if pt.valid:
                        trim.add(pt.co, constraint_index=j, constraint_type=coll_name)

        if not trim.check():
            # No intersections — delete the whole segment + orphan endpoints
            self._delete_segment(context, sketch, segment)
            sketch.geometry_solved = False
            refresh(context)
            return

        trim.execute(context)
        sketch.geometry_solved = False
        refresh(context)


register, unregister = register_stateops_factory((View3D_OT_slvs_trim,))
