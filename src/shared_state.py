"""
shared_state.py
---------------
Single latest dashboard state, written by several producers and read by the
Flask web server. Living in its own module avoids circular imports.

Producers (all in the src/main.py process):
  * brain_worker      -> sensor readings, room/patient state, emergency.
  * MediGuardMqttBridge -> the believed closed actuator state and the latest
                           AI plan received back from the planner service.

Everything is merged into one dict, so each producer only writes its own keys.
"""

import threading

_latest_state = {}
_lock = threading.Lock()


def merge(payload: dict):
    """Update the shared state with the given keys (thread-safe)."""
    with _lock:
        _latest_state.update(payload)


def snapshot() -> dict:
    """Return a copy of the current shared state (thread-safe)."""
    with _lock:
        return dict(_latest_state)
