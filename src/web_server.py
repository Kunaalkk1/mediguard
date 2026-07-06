"""
web_server.py -- Flask routes only. Reads the shared dashboard state and
exposes a couple of control endpoints for dashboard-driven emergencies.

Started as a thread by main.py. No brain logic lives here.
"""

import os

from flask import Flask, jsonify, render_template, request, send_from_directory

import runtime_flags
from shared_state import snapshot

app = Flask(__name__)

# Set by main.py so the manual-control endpoints can drive the actuators
# immediately (the brain loop also re-asserts the same state every cycle).
_bridge = None


def attach_bridge(bridge):
    global _bridge
    _bridge = bridge


def _apply_light_fan():
    """Push the current manual setpoints to hardware if manual mode is active."""
    if _bridge is not None and runtime_flags.manual_mode.get():
        _bridge.set_light_fan(runtime_flags.manual_light.get(),
                              runtime_flags.manual_fan.get())

# Bind to all interfaces so the dashboard is reachable both locally on the Pi
# (http://localhost:7801) and from a phone joined to the Pi's hotspot
# (http://<pi-ip>:7801). Set MEDIGUARD_HOST=127.0.0.1 to restrict to localhost.
HOST = os.getenv("MEDIGUARD_HOST", "0.0.0.0")
PORT = int(os.getenv("MEDIGUARD_PORT", "7801"))


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/sw.js")
def service_worker():
    """Serve the service worker from the root so it can control the whole app."""
    return send_from_directory(app.static_folder, "sw.js", mimetype="application/javascript")


@app.route("/data")
def data():
    """Latest environment + plan state, plus toggle and manual-mode states."""
    state = snapshot()
    state["toggles"] = {
        "sos_emergency": runtime_flags.sos_emergency.get(),
        "vitals_emergency": runtime_flags.vitals_emergency.get(),
    }
    state["mode"] = {
        "manual": runtime_flags.manual_mode.get(),
        "light": runtime_flags.manual_light.get(),
        "fan": runtime_flags.manual_fan.get(),
    }
    return jsonify(state)


def _requested_level():
    """Read a 0-100 level from a JSON body {"value": n} (robust to bad input)."""
    body = request.get_json(silent=True) or {}
    return body.get("value", 0)


@app.route("/api/mode/toggle", methods=["POST"])
def toggle_mode():
    """Switch between AI (auto) and manual control of light + fan."""
    manual = runtime_flags.manual_mode.toggle()
    if _bridge is not None:
        if manual:
            _bridge.set_light_fan(runtime_flags.manual_light.get(),
                                  runtime_flags.manual_fan.get())
        else:
            # Restore the planner's last requested levels.
            _bridge.set_light_fan(_bridge.auto_light, _bridge.auto_fan)
    print(f"[web] control mode -> {'MANUAL' if manual else 'AUTO'}")
    return jsonify({"manual_mode": manual})


@app.route("/api/manual/light", methods=["POST"])
def manual_light():
    value = runtime_flags.manual_light.set(_requested_level())
    _apply_light_fan()
    return jsonify({"light": value})


@app.route("/api/manual/fan", methods=["POST"])
def manual_fan():
    value = runtime_flags.manual_fan.set(_requested_level())
    _apply_light_fan()
    return jsonify({"fan": value})


@app.route("/api/manual/door", methods=["POST"])
def manual_door():
    """Manual lock/unlock from the dashboard. Ignored during an emergency
    (the bridge keeps the door unlocked for access)."""
    body = request.get_json(silent=True) or {}
    value = str(body.get("value", "")).strip().lower()
    if value not in {"lock", "locked", "0", "unlock", "unlocked", "1"}:
        return jsonify({"error": "value must be locked or unlocked"}), 400
    if _bridge is not None:
        _bridge.set_door(value)
        return jsonify({"door": _bridge.get_actuator_state().get("door")})
    return jsonify({"door": None})


@app.route("/api/emergency/vitals/toggle", methods=["POST"])
def toggle_vitals_emergency():
    """Stand-in for the removed SpO2 sensor: flip the medical-emergency state."""
    active = runtime_flags.vitals_emergency.toggle()
    print(f"[web] medical (vitals) emergency toggled -> {'ON' if active else 'OFF'}")
    return jsonify({"vitals_emergency": active})


@app.route("/api/emergency/sos/toggle", methods=["POST"])
def toggle_sos_emergency():
    """Software fallback for the physical SOS button (handy for laptop demos)."""
    active = runtime_flags.sos_emergency.toggle()
    print(f"[web] SOS emergency toggled -> {'ON' if active else 'OFF'}")
    return jsonify({"sos_emergency": active})


def run_server():
    """Start the Flask server. Called in a thread by main.py."""
    # use_reloader=False is essential when running inside a thread.
    try:
        app.run(host=HOST, port=PORT, debug=False, use_reloader=False)
    except OSError as exc:
        print(f"[web] could not start dashboard on {HOST}:{PORT}: {exc}")
