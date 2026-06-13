import random
from grove_base import ON_PI, grovepi

LIGHT_PORT    = 0     # analog A0  -- Grove light sensor
PRESSURE_PORT = 1     # analog A1  -- RP-S40-ST FSR (force/pressure)
GAS_PORT      = 2     # analog A2  -- MQ135 

PIR_PORT      = 2     # digital D2 -- Grove PIR motion (separate socket from A2)
SOS_PORT      = 7     # digital D7 -- Grove button (SOS) 

PRESSURE_THRESHOLD = 400   # raw value above this = someone on the bed  # TUNE ON PI


def read_light():
    """Raw light level, 0-1023 (higher = brighter)."""
    if ON_PI:
        return grovepi.analogRead(LIGHT_PORT)
    else:
        return random.randint(200, 800)


def read_gas():
    """Raw MQ135 gas level, 0-1023 (higher = more gas)."""
    if ON_PI:
        return grovepi.analogRead(GAS_PORT)
    else:
        return random.randint(50, 600)


def read_motion():
    """True if the PIR currently sees movement."""
    if ON_PI:
        return grovepi.digitalRead(PIR_PORT) == 1
    else:
        return random.choice([True, False])              # fake: random motion


def read_sos():
    """True if the SOS button is pressed."""
    if ON_PI:
        return grovepi.digitalRead(SOS_PORT) == 1
    else:
        return random.choice([False, False, False, True])  # fake: rarely pressed


def read_pressure():
    """Returns (raw_value, on_bed) -- on_bed is True if someone is on the bed."""
    if ON_PI:
        raw = grovepi.analogRead(PRESSURE_PORT)
    else:
        raw = random.randint(200, 650)
    on_bed = raw > PRESSURE_THRESHOLD
    return (raw, on_bed)


if __name__ == "__main__":
    where = "Raspberry Pi" if ON_PI else "laptop (simulation)"
    print(f"Testing Grove sensor drivers on {where}...\n")
    print(f"  light  = {read_light()}")
    print(f"  gas    = {read_gas()}")
    print(f"  motion = {read_motion()}")
    print(f"  sos    = {read_sos()}")
    p_raw, p_on_bed = read_pressure()
    print(f"  pressure = {p_raw}  (on bed: {p_on_bed})")