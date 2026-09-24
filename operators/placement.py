"""How a point placed by a drawing tool relates to what is under the cursor.

A drawing state that places a point decides, from the hover, pick and snap
inputs, what the new point links to: nothing, an existing sketch element (a
coincidence), or a live projection of external geometry (a coincidence or a
midpoint constraint on the projected reference). That decision used to live in
loose ``state_data`` keys (``hovered``, ``snapped``, ``snap``, ``snap_projected``,
``snap_link_kind``, ``snap_anchored``, ``coincident``, ``skip_auto_constraints``)
set and cleared from several places, which is how stale flags leaked from one
mouse move into the next. ``PointPlacement`` holds them in one typed object, and
its ``link`` fields are what a preview can compare between mouse moves.
"""

from dataclasses import dataclass
from typing import Any, Optional, Tuple

COINCIDENT = "COINCIDENT"
MIDPOINT = "MIDPOINT"

_KEY = "placement"


@dataclass
class PointPlacement:
    """One drawing state's placement decision and the links it produced."""

    # Snap target under the cursor for this move (from get_blender_snap_info).
    snap: Optional[dict] = None
    # Whether the position came from a snap onto external geometry.
    snapped: bool = False
    # Existing sketch curve the point links to ("" when it links to nothing).
    hovered: str = ""
    # Which constraint links it to ``hovered``: COINCIDENT or MIDPOINT.
    link_kind: str = COINCIDENT
    # ``hovered`` is a live projection made for this placement; its link is part
    # of the snap itself, so it is added even with Auto Constraints off.
    projected: bool = False
    # The point is pinned (e.g. coincident to a fixed projected vertex), so an
    # inferred axis alignment on it would fight the fixed position.
    anchored: bool = False
    # Shift held at the confirming click: place raw, no inferred constraints.
    skip_auto_constraints: bool = False
    # The constraint that realised the link, if one was added.
    coincident: Any = None

    def reset_link(self) -> None:
        """Forget the previous move's link decision before deciding again."""
        self.link_kind = COINCIDENT
        self.projected = False
        self.anchored = False

    def link_existing(self, curve_id: str, fixed: bool, projected: bool) -> None:
        """Link to an existing sketch element with a plain coincidence."""
        self.hovered = curve_id
        self.link_kind = COINCIDENT
        self.projected = projected
        self.anchored = fixed


@dataclass(frozen=True)
class ProjectionRequest:
    """A live projection a snap calls for, decided before anything is created."""

    # VERTEX, EDGE or EDGE_MIDPOINT.
    snap_type: str
    source: Any
    # Original (not evaluated) vertex indices: one for a vertex, two for an edge.
    vertices: Tuple[int, ...]
    world_point: Any = None


def placement_of(state_data: dict) -> PointPlacement:
    """The ``PointPlacement`` of a state, created on first use."""
    placement = state_data.get(_KEY)
    if placement is None:
        placement = state_data[_KEY] = PointPlacement()
    return placement


class ChainDraw:
    """Chaining rules shared by the tools that draw a run of segments.

    The next segment starts where this one ended, so the chain only carries on
    while that end is a point of its own: landing on existing geometry (a pick,
    or a coincident placement) closes the run, which is how a loop is finished.
    Mixed into the line and arc tools; see ``StatefulOperatorLogic.accepts_chain``
    for the other half, picking a chain up from another tool.
    """

    accepts_chain = True

    def continue_draw(self) -> bool:
        last = self._state_data[self._last_pointer_index()]
        if last.get("is_existing_entity"):
            return False
        return not placement_of(last).coincident

    def _last_pointer_index(self) -> int:
        states = self.get_states()
        for i in reversed(range(len(states))):
            if states[i].pointer:
                return i
        return 0
