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


class Menus(str, Enum):
    Sketches = "VIEW3D_MT_sketches"


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
    ContextMenu = "view3d.slvs_context_menu"
    DeleteConstraint = "view3d.slvs_delete_constraint"
    DeleteEntity = "view3d.slvs_delete_entity"
    InvokeTool = "view3d.invoke_tool"
    InstallPackage = "view3d.slvs_install_package"
    RegisterDrawCB = "view3d.slvs_register_draw_cb"
    Select = "view3d.slvs_select"
    SelectAll = "view3d.slvs_select_all"
    SetActiveSketch = "view3d.slvs_set_active_sketch"
    SetAllConstraintsVisibility = "view3d.slvs_set_all_constraints_visibility"
    ShowSolverState = "view3d.slvs_show_solver_state"
    Solve = "view3d.slvs_solve"
    Update = "view3d.slvs_update"
    Test = "view3d.slvs_test"
    Trim = "view3d.slvs_trim"
    Tweak = "view3d.slvs_tweak"
    TweakConstraintValuePos = "view3d.slvs_tweak_constraint_value_pos"
    UnregisterDrawCB = "view3d.slvs_unregister_draw_cb"
    WriteSelectionTexture = "view3d.slvs_write_selection_texture"


class Panels(str, Enum):
    Sketcher = "VIEW3D_PT_sketcher"
    SketcherDebugPanel = "VIEW3D_PT_sketcher_debug_panel"
    SketcherAddContraint = "VIEW3D_PT_sketcher_add_contraint"
    SketcherContraints = "VIEW3D_PT_sketcher_constraints"
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
    Select = "sketcher.slvs_select"
    Trim = "sketcher.slvs_trim"
