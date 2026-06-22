"""
shared_state.py
---------------
Holds the single latest_state that the brain writes and the web server reads.
Living in its own module avoids circular imports between main.py and web_server.py.
"""

import threading

latest_state = {}
state_lock = threading.Lock()


def publish(payload):
    """Brain calls this to update the shared state (thread-safe)."""
    with state_lock:
        latest_state.clear()
        latest_state.update(payload)


def snapshot():
    """Web server calls this to read the current state (thread-safe)."""
    with state_lock:
        return dict(latest_state)