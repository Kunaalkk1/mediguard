"""
Works out the ROOM STATE from one snapshot:

    Normal  /  Hazardous  /  Emergency

Per the spec:
  - Emergency : the patient pressed the SOS button (manual emergency).
  - Hazardous : air quality OR temperature outside safe levels (gas leak or fire).
  - Normal    : neither -- the room itself is fine.
"""

from classify import is_air_hazardous, is_temperature_hazardous

NORMAL    = "Normal"
HAZARDOUS = "Hazardous"
EMERGENCY = "Emergency"

ROOM_STATES = [NORMAL, HAZARDOUS, EMERGENCY]


def assess(snapshot):
    """Return the room state plus the individual danger flags."""
    sos         = bool(snapshot["sos"])                       # button pressed?
    gas_hazard  = is_air_hazardous(snapshot["gas"])           # gas leak?
    temp_hazard = is_temperature_hazardous(snapshot["temperature"])  # fire?
    hazard      = gas_hazard or temp_hazard

    # Single label. SOS (an explicit human call for help) outranks an
    # environmental hazard; both outrank Normal. Same actuator goals either way.
    if sos:
        label = EMERGENCY
    elif hazard:
        label = HAZARDOUS
    else:
        label = NORMAL

    return {
        "label":       label,
        "sos":         sos,
        "gas_hazard":  gas_hazard,
        "temp_hazard": temp_hazard,
        "hazard":      hazard,
        "unsafe":      label != NORMAL,
    }


if __name__ == "__main__":
    # Pull live snapshots and show the Room State they produce.
    # Uses the simulator so it runs on a laptop; on the Pi, swap this import for:  from reader import read_all
    import os, sys
    try:
        from simulator import read_all
    except ImportError:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sensors"))
        from simulator import read_all

    print("room_state.py -- live readings -> Room State")
    print("(simulator data; on the Pi import read_all from reader instead)\n")

    # an everyday reading, then a gas leak, then an SOS press
    for tag in [None, "gas_leak", "sos"]:
        snap = read_all(tag)
        r = assess(snap)
        print(f"[{tag or 'random'}]")
        print(f"  readings: sos={snap['sos']}  gas={snap['gas']}  "
              f"temperature={snap['temperature']}C")
        print(f"  -> Room State: {r['label']}   "
              f"(gas_hazard={r['gas_hazard']}, temp_hazard={r['temp_hazard']}, sos={r['sos']})")
        print()

    print("Done.")