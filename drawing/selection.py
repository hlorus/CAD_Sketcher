"""Transient interactive selection / hover / highlight state.

This is runtime-only viewport state -- what is currently selected, hovered, or
highlighted -- owned by the drawing + selection system. It is intentionally
*not* persisted: nothing here is written to curve attributes or saved with the
file, so selecting or hovering never dirties the datablock. The overlay reads
this directly at draw time; the select/pick operators mutate it.
"""

# curve_ids of the currently selected geometry (list: order + duplicates as the
# select operators expect).
selected = []

# The single curve_id under the cursor ("" = nothing hovered).
hover = ""

# curve_ids to render highlighted in addition to hover -- e.g. the geometry a
# hovered constraint acts on. Cleared by the preselection gizmo.
highlight_curve_ids = []

# The constraint under the cursor, so its gizmo/icon draws highlighted.
highlight_constraint = None

# Legacy entity-based highlight list (old entity model); kept for compatibility.
highlight_entities = []

# curve_ids to skip while picking (e.g. the geometry currently being drawn).
ignore_list = []


def clear():
    """Reset all interactive state (e.g. on file load)."""
    selected.clear()
    highlight_curve_ids.clear()
    highlight_entities.clear()
    ignore_list.clear()
    global hover, highlight_constraint
    hover = ""
    highlight_constraint = None
