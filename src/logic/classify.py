"""
Display buckets:
    Temperature : Frosty / Cold / Neutral / Warm / Hot
    Sunlight    : Dark / Dull / Bright
    Air Quality : Normal / Humid / Hazardous
"""


GAS_HAZARD_THRESHOLD = 400    # raw 0-1023; at/above this = gas leak        
TEMP_FIRE_THRESHOLD  = 45     # deg C; at/above this = fire / unsafe heat 

FROSTY, COLD, NEUTRAL, WARM, HOT = "Frosty", "Cold", "Neutral", "Warm", "Hot"
DARK, DULL, BRIGHT               = "Dark", "Dull", "Bright"
AIR_NORMAL, HUMID, HAZARDOUS     = "Normal", "Humid", "Hazardous"


def is_air_hazardous(gas, threshold=GAS_HAZARD_THRESHOLD):
    """True if the gas reading indicates a hazardous leak."""
    return gas >= threshold


def is_temperature_hazardous(celsius, fire_threshold=TEMP_FIRE_THRESHOLD):
    """True if the temperature is high enough to indicate a fire / unsafe heat.
    (Easily extended to flag dangerous COLD too, if your spec needs it.)"""
    return celsius >= fire_threshold


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