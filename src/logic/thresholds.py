GAS_HAZARD_THRESHOLD = 400    # raw 0-1023; at/above this = gas leak
TEMP_FIRE_THRESHOLD  = 45     # deg C; at/above this = fire / unsafe heat

def is_air_hazardous(gas, threshold=GAS_HAZARD_THRESHOLD):
    """True if the gas reading indicates a hazardous leak."""
    return gas >= threshold


def is_temperature_hazardous(celsius, fire_threshold=TEMP_FIRE_THRESHOLD):
    """True if the temperature is high enough to indicate a fire / unsafe heat.
    (Easily extended to flag dangerous COLD too, if your spec needs it.)"""
    return celsius >= fire_threshold