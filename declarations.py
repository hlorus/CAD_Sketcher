# Please keep this file in alphabetical order
from enum import Enum


class Gizmos(str, Enum):
    Angle = "VIEW3D_GT_slvs_angle"
    Constraint = "VIEW3D_GT_slvs_constraint"
    ConstraintValue = "VIEW3D_GT_slvs_constraint_value"
    Diameter = "VIEW3D_GT_slvs_diameter"
    Distance = "VIEW3D_GT_slvs_distance"
    Preselection = "VIEW3D_GT_slvs_preselection"


class GizmoGroups(str, Enum):
    Angle = "VIEW3D_GGT_slvs_angle"
    Constraint = "VIEW3D_GGT_slvs_constraint"
    Diameter = "VIEW3D_GGT_slvs_diameter"
    Distance = "VIEW3D_GGT_slvs_distance"
    Preselection = "VIEW3D_GGT_slvs_preselection"


class Operators(str, Enum):
    AddAngle = "view3d.slvs_add_angle"
    AddArc2D = "view3d.slvs_add_arc2d"
    AddCircle2D = "view3d.slvs_add_circle2d"
    AddCoincident = "view3d.slvs_add_coincident"
    AddDiameter = "view3d.slvs_add_diameter"
    AddDistance = "view3d.slvs_add_distance"
    AddEqual = "view3d.slvs_add_equal"
    AddHorizontal = "view3d.slvs_add_horizontal"
    AddLine2D = "view3d.slvs_add_line2d"
    AddLine3D = "view3d.slvs_add_line3d"
    AddMidPoint = "view3d.slvs_add_midpoint"
    AddParallel = "view3d.slvs_add_parallel"
    AddPerpendicular = "view3d.slvs_add_perpendicular"
    AddPoint2D = "view3d.slvs_add_point2d"
    AddPoint3D = "view3d.slvs_add_point3d"
    AddPresetTheme = "bgs.theme_preset_add"
    AddRatio = "view3d.slvs_add_ratio"
    AddRectangle = "view3d.slvs_add_rectangle"
    AddSketch = "view3d.slvs_add_sketch"
    AddTangent = "view3d.slvs_add_tangent"
    AddVertical = "view3d.slvs_add_vertical"
    AddWorkPlane = "view3d.slvs_add_workplane"
    AddWorkPlaneFace = "view3d.slvs_add_workplane_face"
    AlignWorkplaneCursor = "view3d.slvs_align_workplane_cursor"
    AlignView = "view3d.slvs_align_view"
    BatchSet = "view3d.slvs_batch_set"
    ContextMenu = "view3d.slvs_context_menu"
    Copy = "view3d.slvs_copy"
    DeleteConstraint = "view3d.slvs_delete_constraint"
    DeleteEntity = "view3d.slvs_delete_entity"
    InstallPackage = "view3d.slvs_install_package"
    Paste = "view3d.slvs_paste"
    Move = "view3d.slvs_move"
    Offset = "view3d.slvs_offset"
    NodeFill = "view3d.slvs_node_fill"
    NodeExtrude = "view3d.slvs_node_extrude"
    NodeArrayLinear = "view3d.slvs_node_array_linear"
    RegisterDrawCB = "view3d.slvs_register_draw_cb"
    Select = "view3d.slvs_select"
    SelectAll = "view3d.slvs_select_all"
    SelectBox = "view3d.slvs_select_box"
    SelectInvert = "view3d.slvs_select_invert"
    SelectExtendAll = "view3d.slvs_select_extend_all"
    SelectExtend = "view3d.slvs_select_extend"
    SetActiveSketch = "view3d.slvs_set_active_sketch"
    SetAllConstraintsVisibility = "view3d.slvs_set_all_constraints_visibility"
    ShowSolverState = "view3d.slvs_show_solver_state"
    Solve = "view3d.slvs_solve"
    Update = "view3d.slvs_update"
    Trim = "view3d.slvs_trim"
    Bevel = "view3d.slvs_bevel"
    Tweak = "view3d.slvs_tweak"
    TweakConstraintValuePos = "view3d.slvs_tweak_constraint_value_pos"
    UnregisterDrawCB = "view3d.slvs_unregister_draw_cb"
    WriteSelectionTexture = "view3d.slvs_write_selection_texture"


class Macros(str, Enum):
    DuplicateMove = "view3d.slvs_duplicate_move"


class Menus(str, Enum):
    SelectedMenu = "VIEW3D_MT_selected_menu"


class Panels(str, Enum):
    Sketcher = "VIEW3D_PT_sketcher"
    SketcherDebugPanel = "VIEW3D_PT_sketcher_debug_panel"
    SketcherTools = "VIEW3D_PT_sketcher_tools"
    SketcherConstraints = "VIEW3D_PT_sketcher_constraints"
    SketcherEntities = "VIEW3D_PT_sketcher_entities"


class VisibilityTypes(str, Enum):
    Hide = "HIDE"
    Show = "SHOW"


class WorkSpaceTools(str, Enum):
    AddArc2D = "sketcher.slvs_add_arc2d"
    AddCircle2D = "sketcher.slvs_add_circle2d"
    AddLine2D = "sketcher.slvs_add_line2d"
    AddLine3D = "sketcher.slvs_add_line3d"
    AddPoint2D = "sketcher.slvs_add_point2d"
    AddPoint3D = "sketcher.slvs_add_point3d"
    AddRectangle = "sketcher.slvs_add_rectangle"
    AddWorkplane = "sketcher.slvs_add_workplane"
    AddWorkplaneFace = "sketcher.slvs_add_workplane_face"
    Offset = "sketcher.slvs_offset"
    Select = "sketcher.slvs_select"
    Trim = "sketcher.slvs_trim"
    Bevel = "sketcher.slvs_bevel"


ConstraintOperators = (
    Operators.AddDistance,
    Operators.AddDiameter,
    Operators.AddAngle,
    Operators.AddCoincident,
    Operators.AddEqual,
    Operators.AddVertical,
    Operators.AddHorizontal,
    Operators.AddParallel,
    Operators.AddPerpendicular,
    Operators.AddTangent,
    Operators.AddMidPoint,
    Operators.AddRatio,
)
