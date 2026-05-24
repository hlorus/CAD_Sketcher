from bpy.types import UIList, Context, UILayout, PropertyGroup

from ..declarations import Operators
from ..model.types import SlvsLine2D


class VIEW3D_UL_sketches(UIList):
    """Creates UI list of available Sketches"""

    def draw_item(
        self,
        context: Context,
        layout: UILayout,
        data: PropertyGroup,
        item: PropertyGroup,
        icon: int,
        active_data: PropertyGroup,
        active_propname: str,
        index: int = 0,
    ):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            if item:
                active = index == getattr(active_data, active_propname)

                row = layout.row(align=True)
                row.alignment = "LEFT"
                row.prop(
                    item,
                    "visible",
                    icon_only=True,
                    icon=("HIDE_OFF" if item.visible else "HIDE_ON"),
                    emboss=False,
                )
                row.prop(item, "name", text="", emboss=False, icon_value=icon)

                row = layout.row()
                row.alignment = "RIGHT"

                if item.solver_state != "OKAY":
                    row.operator(
                        Operators.ShowSolverState,
                        text="",
                        emboss=False,
                        icon_value=layout.enum_item_icon(
                            item, "solver_state", item.solver_state
                        ),
                    ).index = item.slvs_index

                row.operator(
                    Operators.SetActiveSketch,
                    icon="OUTLINER_DATA_GP_LAYER",
                    text="",
                    emboss=False,
                ).index = item.slvs_index

                if active:
                    row.operator(
                        Operators.DeleteEntity,
                        text="",
                        icon="X",
                        emboss=False,
                    ).index = item.slvs_index
                else:
                    row.separator()
                    row.separator()

                if item.tag:
                    ext_count = sum(
                        1
                        for e in item.sketch_entities(context)
                        if isinstance(e, SlvsLine2D) and getattr(e, "linked", False)
                    )
                    tag_text = (
                        item.tag
                        if ext_count == 0
                        else "{} [{}]".format(item.tag, ext_count)
                    )
                    row.label(text=tag_text)

            else:
                layout.label(text="", translate=False, icon_value=icon)
        elif self.layout_type in {"GRID"}:
            layout.alignment = "CENTER"
            layout.label(text="", icon_value=icon)
