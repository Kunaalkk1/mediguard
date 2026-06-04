"""
Turns raw sensor numbers into the human-readable BUCKETS shown on the
dashboard's three input rows:

    Temperature : Frosty / Cold / Neutral / Warm / Hot
    Sunlight    : Dark / Dull / Bright
    Air Quality : Normal / Humid / Hazardous

"""

FROSTY  = "Frosty"
COLD    = "Cold"
NEUTRAL = "Neutral"
WARM    = "Warm"
HOT     = "Hot"

DARK   = "Dark"
DULL   = "Dull"
BRIGHT = "Bright"

AIR_NORMAL = "Normal"
HUMID      = "Humid"
HAZARDOUS  = "Hazardous"


def classify_temperature(celsius,
                         frosty_max=12,    # below this -> Frosty
                         cold_max=18,      # below this -> Cold
                         neutral_max=24,   # below this -> Neutral
                         warm_max=28):     # below this -> Warm, else Hot
    
    if celsius < frosty_max:
        return FROSTY
    if celsius < cold_max:
        return COLD
    if celsius < neutral_max:
        return NEUTRAL
    if celsius < warm_max:
        return WARM
    return HOT


def classify_sunlight(light,
                      dark_max=300,    # below this -> Dark
                      dull_max=650):   # below this -> Dull, else Bright
    
    if light < dark_max:
        return DARK
    if light < dull_max:
        return DULL
    return BRIGHT


def classify_air_quality(gas, humidity,
                        gas_threshold=400,    # at/above this -> Hazardous
                        humid_threshold=65):  # at/above this -> Humid
    
    if gas >= gas_threshold:
        return HAZARDOUS
    if humidity >= humid_threshold:
        return HUMID
    return AIR_NORMAL


def classify_all(snapshot):

    return {
        "temperature": classify_temperature(snapshot["temperature"]),
        "sunlight":     classify_sunlight(snapshot["light"]),
        "air_quality":  classify_air_quality(snapshot["gas"], snapshot["humidity"]),
    }


if __name__ == "__main__":
    print("Testing classify.py\n")

    print("Temperature bands:")
    for t in [5, 15, 21, 26, 31]:
        print(f"  {t:3}C  -> {classify_temperature(t)}")
    print()

    print("Sunlight bands (LDR 0..1023):")
    for L in [100, 450, 800]:
        print(f"  {L:4}  -> {classify_sunlight(L)}")
    print()

    print("Air quality (gas, humidity):")
    for g, h in [(100, 50), (100, 75), (720, 50), (720, 75)]:
        print(f"  gas={g:3} humidity={h:2}%  -> {classify_air_quality(g, h)}")
    print("  (last two: gas is hazardous regardless of humidity)")
    print()

    print("classify_all on a full snapshot:")
    sample = {"temperature": 26.5, "light": 700, "gas": 100, "humidity": 72}
    print(f"  {sample}")
    print(f"  -> {classify_all(sample)}")

    print("\nDone.")