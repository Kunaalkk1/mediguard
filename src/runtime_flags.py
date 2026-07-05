"""
runtime_flags.py
----------------
Process-wide, thread-safe toggle switches for manually-driven emergencies.

Two emergencies cannot be produced from a normal sensor reading on the bench,
so they are driven by explicit toggles instead:

  * sos_emergency    -- the physical SOS button (a 2 s hold flips it) OR, in a
                        pure-simulation demo, the dashboard. Maps to the room
                        "emergency" state.
  * vitals_emergency -- a dashboard button that stands in for the removed
                        SpO2/pulse hardware sensor. Maps to patient "distress"
                        (vitals out of the safe range).

Both are simple latching toggles: press once to turn on, again to turn off.
The sensor/brain pipeline reads them every cycle in src/main.py.
"""

import threading


class Toggle:
    """A thread-safe boolean that can be flipped or set explicitly."""

    def __init__(self, value: bool = False):
        self._value = bool(value)
        self._lock = threading.Lock()

    def toggle(self) -> bool:
        """Flip the value and return the new state."""
        with self._lock:
            self._value = not self._value
            return self._value

    def set(self, value: bool) -> bool:
        with self._lock:
            self._value = bool(value)
            return self._value

    def get(self) -> bool:
        with self._lock:
            return self._value


# The two shared switches used across the sensor, brain, and web threads.
sos_emergency = Toggle()
vitals_emergency = Toggle()
