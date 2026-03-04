from typing import Optional

from .keymap import is_unit_input, get_unit_value, get_value_from_event


class NumericInput:
    """Manages the text input buffer for numeric entry in a stateful operator.

    Handles per-substate string buffers (e.g. X, Y, Z components of a vector),
    substate cycling via TAB, and validation of entered characters.
    """

    def __init__(self):
        self._buffer: dict = {}
        self.substate_index: int = 0
        self.substate_count: Optional[int] = None
        self.prop = None
        self.is_active: bool = False

    def reset(self):
        self._buffer = {}
        self.substate_index = 0
        self.substate_count = None
        self.prop = None
        self.is_active = False

    def init_substate(self, prop):
        self.substate_count = prop.array_length if prop else None
        self.prop = prop

    def iterate(self):
        count = self.substate_count or 1
        self.substate_index = (self.substate_index + 1) % count

    @property
    def current(self) -> str:
        return self._buffer.get(self.substate_index, "")

    @current.setter
    def current(self, value: str):
        self._buffer[self.substate_index] = value

    def get(self, sub_index: int) -> str:
        return self._buffer.get(sub_index, "")

    def evaluate_event(self, event):
        event_type = event.type
        if event_type == "BACK_SPACE":
            if self.current:
                self.current = self.current[:-1]
            return

        if event_type in ("MINUS", "NUMPAD_MINUS"):
            self.current = self.current[1:] if self.current.startswith("-") else "-" + self.current
            return

        if is_unit_input(event):
            self.current += get_unit_value(event)
            return

        value = get_value_from_event(event)
        self.current += self._validate(value)

    def _validate(self, value: str) -> str:
        """Check if value can be appended to the current input string."""
        separators = (".", ",")
        if value in separators:
            if any(c in self.current for c in separators):
                return ""
            if not self.current or not self.current[-1].isdigit():
                return "0."
        return value
