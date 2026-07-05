"""
web_server.py -- Flask routes only. Reads the shared dashboard state and
exposes a couple of control endpoints for dashboard-driven emergencies.

Started as a thread by main.py. No brain logic lives here.
"""

import os

from flask import Flask, jsonify, render_template, send_from_directory

import runtime_flags
from shared_state import snapshot

app = Flask(__name__)

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
    """Latest environment + plan state, plus the manual toggle states."""
    state = snapshot()
    state["toggles"] = {
        "sos_emergency": runtime_flags.sos_emergency.get(),
        "vitals_emergency": runtime_flags.vitals_emergency.get(),
    }
    return jsonify(state)


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
