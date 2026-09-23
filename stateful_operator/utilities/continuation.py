"""Where a drawing chain hands its last point to the tool that comes next.

A tool shortcut pressed mid-chain ends the running operator and starts another
one through the keymap (see ``switch``), so the point the chain had reached
cannot be handed over in memory: the operator that held it is gone by the time
its successor invokes. It is published here instead.

The offer is for the run the switch started, nothing later: it is consumed by
the next run whether or not that run can use it, and dropped again once the
keypress that caused the switch is done with (see ``invoke_op``).
"""

from typing import Any, Optional

# (implicit pointer values, pointer type, scope) or None. The scope is whatever
# the operator calls its context (a sketch, for the CAD Sketcher operators), so
# a point is never carried into a place it doesn't belong to.
_offer: Optional[tuple] = None


def publish(values: list, kind: Any, scope: str) -> None:
    """Offer a pointer state's value to the run that starts next."""
    global _offer
    _offer = (list(values), kind, scope)


def take(scope: str) -> Optional[tuple]:
    """Consume the offer, returning ``(values, kind)`` if it is for ``scope``.

    Consumed either way: an offer not taken up straight away is stale.
    """
    global _offer
    offer = _offer
    _offer = None
    if offer is None or offer[2] != scope:
        return None
    return offer[0], offer[1]


def clear() -> None:
    """Drop any standing offer."""
    global _offer
    _offer = None


def pending() -> bool:
    """Whether an offer is standing (for tests and debugging)."""
    return _offer is not None
