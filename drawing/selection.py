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

# curve_ids of every element under the cursor, nearest first, so overlapping
# entities can be cycled. Rebuilt on each hover update; ``hover`` is one of these.
hover_candidates = []

# True once the hover has been explicitly positioned within the stack (Alt+wheel).
# While locked, an Alt+click commits the current hover instead of advancing again,
# so wheel-to-preview then click (with Alt still held) does not overshoot. Reset
# when the cursor moves to a different element.
hover_locked = False

# curve_ids to render highlighted in addition to hover -- e.g. the geometry a
# hovered constraint acts on. Cleared by the preselection gizmo.
highlight_curve_ids = []

# The constraint under the cursor, so its gizmo/icon draws highlighted.
highlight_constraint = None

# Legacy entity-based highlight list (old entity model); kept for compatibility.
highlight_entities = []

# curve_ids to skip while picking (e.g. the geometry currently being drawn).
ignore_list = []


def cycle_hover(direction=1, lock=False):
    """Advance ``hover`` to the next overlapping candidate under the cursor.

    Steps through ``hover_candidates`` (nearest first). Returns True if the hover
    moved, False when fewer than two entities are stacked. Shared by the select
    tool's cycle operator and the stateful draw modal so both behave the same.

    ``lock`` marks the hover as explicitly positioned (used by the Alt+wheel
    preview), so a following Alt+click commits it rather than advancing past it.
    """
    global hover, hover_locked
    if len(hover_candidates) < 2:
        return False
    try:
        index = hover_candidates.index(hover)
    except ValueError:
        index = 0
    step = 1 if direction >= 0 else -1
    hover = hover_candidates[(index + step) % len(hover_candidates)]
    if lock:
        hover_locked = True
    return True


def take_hover_lock():
    """Consume the hover lock. Returns True if it was set (hover positioned by
    Alt+wheel), so the caller commits the current hover instead of advancing."""
    global hover_locked
    was_locked = hover_locked
    hover_locked = False
    return was_locked


def clear():
    """Reset all interactive state (e.g. on file load)."""
    selected.clear()
    highlight_curve_ids.clear()
    highlight_entities.clear()
    ignore_list.clear()
    hover_candidates.clear()
    global hover, highlight_constraint, hover_locked
    hover = ""
    hover_locked = False
    highlight_constraint = None
