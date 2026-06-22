"""
web_server.py -- Flask routes only. Reads shared state; no brain here.
Started as a thread by main.py.
"""

from flask import Flask, jsonify, render_template
from shared_state import snapshot

app = Flask(__name__)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/data")
def data():
    return jsonify(snapshot())          # read the brain's published state


def run_server():
    """Start the Flask server. Called in a thread by main.py."""
    # use_reloader=False is essential when running inside a thread.
    app.run(host="0.0.0.0", port=7801, debug=False, use_reloader=False)