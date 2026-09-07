from bpy.props import BoolProperty, FloatProperty, StringProperty
from bpy.types import Context, Event, Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..drawing import selection
from ..model.curve_ref import curve_ref


class View3D_OT_slvs_set_curve_flag(Operator):
    """Toggle a flag on a curve"""

    bl_idname = Operators.SetCurveFlag
    bl_label = "Set Curve Flag"
    bl_options = {"UNDO"}

    curve_id: StringProperty()
    flag: StringProperty()
    value: BoolProperty()

    def execute(self, context: Context):
        from ..model.sketch_ref import get_active_sketch

        sketch = get_active_sketch(context)
        if not sketch:
            return {"CANCELLED"}

        # A specific curve_id targets one curve; otherwise apply to the whole
        # current selection (used by the selected-elements context menu).
        curve_ids = [self.curve_id] if self.curve_id else list(selection.selected)
        changed = False
        for cid in curve_ids:
            ref = curve_ref(sketch, cid)
            if ref.valid:
                setattr(ref, self.flag, self.value)
                changed = True

        if not changed:
            return {"CANCELLED"}
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class View3D_OT_slvs_rename_curve(Operator):
    """Rename this entity"""

    bl_idname = Operators.RenameCurve
    bl_label = "Rename Entity"
    bl_options = {"UNDO"}

    curve_id: StringProperty()
    new_name: StringProperty(name="Name")

    def invoke(self, context: Context, event: Event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: Context):
        self.layout.prop(self, "new_name")

    def execute(self, context: Context):
        from ..model.sketch_ref import get_active_sketch

        sketch = get_active_sketch(context)
        if not sketch:
            return {"CANCELLED"}
        ref = curve_ref(sketch, self.curve_id)
        if not ref.valid:
            return {"CANCELLED"}
        ref.name = self.new_name
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


def _solve_and_refresh(context: Context, sketch) -> None:
    """Re-solve the sketch and rebuild its display geometry after an edit."""
    from ..curve_solver import solve_system
    from ..utilities.curve_data import refresh_curve_geometry

    sketch.geometry_solved = False
    solve_system(context, sketch=sketch)
    refresh_curve_geometry(sketch)
    if context.area:
        context.area.tag_redraw()


class View3D_OT_slvs_set_point_coords(Operator):
    """Edit this point's coordinates"""

    bl_idname = Operators.SetPointCoords
    bl_label = "Set Coordinates"
    # REGISTER so the Adjust Last Operation panel can also tweak the coordinates.
    bl_options = {"REGISTER", "UNDO"}

    curve_id: StringProperty()
    # Separate scalar fields: drawing one vector prop as per-index rows in the
    # dialog left the Y/Z rows uncommitted, so only X ever moved.
    x: FloatProperty(name="X")
    y: FloatProperty(name="Y")
    z: FloatProperty(name="Z")
    # 3D sketches expose a Z component; 2D sketches keep the point on the plane.
    use_z: BoolProperty(default=False, options={"SKIP_SAVE"})

    def invoke(self, context: Context, event: Event):
        from ..model.sketch_ref import get_active_sketch

        sketch = get_active_sketch(context)
        if not sketch:
            return {"CANCELLED"}
        ref = curve_ref(sketch, self.curve_id)
        if not ref.valid or not ref.is_point():
            return {"CANCELLED"}

        pos = ref._first_point_3d()
        self.x, self.y, self.z = pos.x, pos.y, pos.z
        self.use_z = bool(sketch.is_3d)
        # props_popup (not props_dialog): it executes live on each field change,
        # so the point tracks every edit. A dialog only commits on OK and can
        # drop the value of the field still being edited when OK is pressed.
        return context.window_manager.invoke_props_popup(self, event)

    def draw(self, context: Context):
        col = self.layout.column()
        col.prop(self, "x")
        col.prop(self, "y")
        if self.use_z:
            col.prop(self, "z")

    def execute(self, context: Context):
        from ..model.native_3d import rebuild_3d_lines
        from ..model.sketch_ref import get_active_sketch

        sketch = get_active_sketch(context)
        if not sketch:
            return {"CANCELLED"}
        ref = curve_ref(sketch, self.curve_id)
        if not ref.valid or not ref.is_point():
            return {"CANCELLED"}

        if sketch.is_3d:
            # 3D points carry a real local Z, so write the position directly
            # (the 2D co setter would flatten it) and rebuild the wire display.
            if not ref._resolve():
                return {"CANCELLED"}
            curve_data = sketch.target_object.data
            pt_idx = ref._curve_slice.points[0].index
            curve_data.points[pt_idx].position = (self.x, self.y, self.z)
            rebuild_3d_lines(sketch)
            curve_data.update_tag()
        else:
            ref.co = (self.x, self.y)

        _solve_and_refresh(context, sketch)
        return {"FINISHED"}


class View3D_OT_slvs_flip_arc(Operator):
    """Connect the arc's endpoints in the inverted order"""

    bl_idname = Operators.FlipArc
    bl_label = "Invert Direction"
    bl_options = {"UNDO"}

    curve_id: StringProperty()

    def execute(self, context: Context):
        from ..model.sketch_ref import get_active_sketch
        from ..utilities.curve_data import rebuild_segments

        sketch = get_active_sketch(context)
        if not sketch:
            return {"CANCELLED"}
        ref = curve_ref(sketch, self.curve_id)
        if not ref.valid or not ref.is_arc():
            return {"CANCELLED"}

        # Arc geometry always sweeps CCW from start to end, so swapping the
        # endpoint references yields the complementary arc between the same
        # points. rebuild_segments re-bakes it (adapting the control-point count
        # to the new sweep angle).
        start = ref._get_attr_value("start_point_id", "")
        end = ref._get_attr_value("end_point_id", "")
        ref._set_attr_value("start_point_id", end)
        ref._set_attr_value("end_point_id", start)
        rebuild_segments(sketch)

        _solve_and_refresh(context, sketch)
        return {"FINISHED"}


register, unregister = register_classes_factory(
    (
        View3D_OT_slvs_set_curve_flag,
        View3D_OT_slvs_rename_curve,
        View3D_OT_slvs_set_point_coords,
        View3D_OT_slvs_flip_arc,
    )
)
