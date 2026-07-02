from bpy.types import Context

from .. import declarations
from . import VIEW3D_PT_sketcher_base

from ...model.constants import SketchCurveType
from ... import global_data


_TYPE_NAMES = {
    SketchCurveType.POINT: "Point",
    SketchCurveType.LINE: "Line",
    SketchCurveType.ARC: "Arc",
    SketchCurveType.CIRCLE: "Circle",
}


class VIEW3D_PT_sketcher_entities(VIEW3D_PT_sketcher_base):
    """Entities Menu: List of curves in the active sketch."""

    bl_label = "Entities"
    bl_idname = declarations.Panels.SketcherEntities
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: Context):
        layout = self.layout
        box = layout.box()
        col = box.column(align=True)
        col.scale_y = 0.8

        from ...model.sketch_ref import get_active_sketch
        sketch = get_active_sketch(context)
        if not sketch or not sketch.target_object or not sketch.target_object.data:
            col.label(text="No active sketch")
            return

        curve_data = sketch.target_object.data
        n = len(curve_data.curves)
        cid_attr = curve_data.attributes.get("curve_id")
        type_attr = curve_data.attributes.get("sketch_type")
        vis_attr = curve_data.attributes.get("visible")
        if not cid_attr or not type_attr:
            return

        for i in range(n):
            cid = cid_attr.data[i].value
            if not cid:
                continue

            ctype = type_attr.data[i].value
            visible = vis_attr.data[i].value if vis_attr else True
            selected = cid in global_data.selected
            name = f"{_TYPE_NAMES.get(ctype, 'Curve')} {cid}"

            row = col.row()
            row.alert = selected

            # Select toggle
            props = row.operator(
                declarations.Operators.Select,
                text="",
                emboss=False,
                icon=("RADIOBUT_ON" if selected else "RADIOBUT_OFF"),
            )
            props.mode = "TOGGLE"
            props.index = cid

            # Visibility toggle
            props = row.operator(
                declarations.Operators.SetCurveFlag,
                text="",
                emboss=False,
                icon=("HIDE_OFF" if visible else "HIDE_ON"),
            )
            props.curve_id = cid
            props.flag = "visible"
            props.value = not visible

            # Name label
            row.label(text=name)

            # Context menu
            props = row.operator(
                declarations.Operators.ContextMenu,
                text="",
                icon="OUTLINER_DATA_GP_LAYER",
                emboss=False,
            )
            props.index = cid

            # Delete
            props = row.operator(
                declarations.Operators.DeleteEntity,
                text="",
                icon="X",
                emboss=False,
            )
            props.index = cid
