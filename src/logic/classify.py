"""
Display buckets:
    Temperature : Frosty / Cold / Neutral / Warm / Hot
    Sunlight    : Dark / Dull / Bright
    Air Quality : Normal / Humid / Hazardous

This module is the single place where raw sensor snapshots and room/patient
states get turned into classified values -- display buckets, PDDL-facing
status strings, label maps, and the active safety profile. main.py should
only call into these functions, never re-derive thresholds itself.
"""

from .room_state import NORMAL, HAZARDOUS as ROOM_HAZARDOUS, EMERGENCY
from .patient_state import AWAKE, RESTING, OUT_OF_BED, DISTRESS
from .thresholds import is_air_hazardous, is_temperature_hazardous

FROSTY, COLD, NEUTRAL, WARM, HOT = "Frosty", "Cold", "Neutral", "Warm", "Hot"
DARK, DULL, BRIGHT               = "Dark", "Dull", "Bright"
AIR_NORMAL, HUMID, HAZARDOUS     = "Normal", "Humid", "Hazardous"

# Lowercase label maps for the PDDL/planner service and dashboard.
ROOM_MAP = {NORMAL: "normal", ROOM_HAZARDOUS: "hazardous", EMERGENCY: "emergency"}
PATIENT_MAP = {AWAKE: "awake", RESTING: "resting", OUT_OF_BED: "out_of_bed", DISTRESS: "distress"}


def classify_temperature(celsius, frosty_max=12, cold_max=18, neutral_max=24, warm_max=28):
    """Drop a temperature into one of five comfort bands (for display)."""
    if celsius < frosty_max:  return FROSTY
    if celsius < cold_max:    return COLD
    if celsius < neutral_max: return NEUTRAL
    if celsius < warm_max:    return WARM
    return HOT


def classify_sunlight(light, dark_max=300, dull_max=650):
    """Drop the light reading into Dark / Dull / Bright (higher = brighter)."""
    if light < dark_max: return DARK
    if light < dull_max: return DULL
    return BRIGHT


def classify_air_quality(gas, humidity, humid_threshold=65):
    """Combine gas + humidity into one air-quality label. Gas danger wins."""
    if is_air_hazardous(gas):
        return HAZARDOUS
    if humidity >= humid_threshold:
        return HUMID
    return AIR_NORMAL


def classify_all(snapshot):
    """Read the relevant fields from a snapshot and return all three display
    buckets in a dict -- what the dashboard will call."""
    return {
        "temperature": classify_temperature(snapshot["temperature"]),
        "sunlight":    classify_sunlight(snapshot["light"]),
        "air_quality": classify_air_quality(snapshot["gas"], snapshot["humidity"]),
    }


def safe_bucket_values(snapshot, buckets, room):
    """Convert hardware readings to the exact lowercase vocabulary of the PDDL service."""
    temp = snapshot.get("temperature")
    humidity = snapshot.get("humidity")
    light = snapshot.get("light", 0)
    pulse = snapshot.get("pulse")
    spo2 = snapshot.get("spo2")

    if room["temp_hazard"]:
        temperature_status = "unsafe"
    elif temp is not None and temp >= 28:
        temperature_status = "hot"
    else:
        temperature_status = "comfortable"

    return {
        "temperature_status": temperature_status,
        "humidity_status": "high" if humidity is not None and humidity >= 65 else "comfortable",
        "air_quality_status": "unsafe" if room["gas_hazard"] else "safe",
        "light_level": "dark" if light < 300 else "normal",
        "pressure_on_bed": bool(snapshot.get("on_bed")),
        "pir_motion_last_15_min": bool(snapshot.get("motion")),
        "spo2_status": "low" if spo2 is not None and spo2 < 90 else "normal",
        "pulse_status": "abnormal" if pulse is not None and not (50 <= pulse <= 120) else "normal",
        "sos_pressed": bool(snapshot.get("sos")),
        "display_temperature_bucket": buckets["temperature"],
        "display_air_quality_bucket": buckets["air_quality"],
        "display_sunlight_bucket": buckets["sunlight"],
    }

def active_safety_profile(room, patient_state):
    """Classify the current room/patient combination into a safety profile name."""
    if room["label"] == EMERGENCY:
        return "emergency"
    if room["label"] == ROOM_HAZARDOUS:
        return "hazardous"
    if patient_state == DISTRESS:
        return "distress"
    return None


def build_planner_state(room_id, snapshot, room, patient_state, out_of_bed_minutes):
    """Assemble the full PDDL-facing state dict from raw snapshot + room/patient state.
    This is the one entry point main.py needs for a fully classified snapshot."""
    from datetime import datetime

    buckets = classify_all(snapshot)
    return {
        "schema_version": 1,
        "room_id": room_id,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "room_state": ROOM_MAP[room["label"]],
        "patient_state": PATIENT_MAP[patient_state],
        "out_of_bed_minutes": out_of_bed_minutes,
        "sensor_summary": safe_bucket_values(snapshot, buckets, room),
        # These raw values are optional for logs/dashboard; the PDDL service
        # uses only the symbolic fields above.
        "raw_snapshot": snapshot,
    }, buckets


if __name__ == "__main__":
    # Pull live snapshots and show the display buckets they produce.
    # Uses the simulator so it runs on a laptop; on the Pi, swap this import for:  from reader import read_all
    import os, sys
    try:
        from simulator import read_all
    except ImportError:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sensors"))
        from simulator import read_all

    print("classify.py -- live readings -> display buckets")
    print("(simulator data; on the Pi import read_all from reader instead)\n")

    # two everyday readings, then a forced gas leak to show "Hazardous"
    for tag in [None, None, "gas_leak"]:
        snap = read_all(tag)
        b = classify_all(snap)
        print(f"[{tag or 'random'}]")
        print(f"  readings: temp={snap['temperature']}C  humidity={snap['humidity']}%  "
              f"light={snap['light']}  gas={snap['gas']}")
        print(f"  buckets : Temperature={b['temperature']}  "
              f"Sunlight={b['sunlight']}  Air Quality={b['air_quality']}")
        print()

    print("Done.")