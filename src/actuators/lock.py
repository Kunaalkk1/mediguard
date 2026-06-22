"""
TWO HARDWARE FACTS (the flags below):
1) RELAY_ACTIVE_HIGH -- a Grove relay energizes on a HIGH signal, so True is
   correct here. (Only flip it if the lock behaves backwards.)
2) ENERGIZE_TO_UNLOCK -- which way your solenoid works:
     fail-secure (the usual cheap one): power = UNLOCKED -> True
     fail-safe:                         power = LOCKED   -> False
   Setting this one flag makes lock()/unlock() correct either way.

WIRING: the Grove cable controls the relay; the solenoid's power runs through
the relay's screw terminals (12V+ -> COM, NO -> solenoid+, solenoid- -> 12V-).
Keep a flyback diode across the solenoid coil.
"""

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sensors"))
from grove_base import ON_PI, grovepi

RELAY_PORT         = 6      # GrovePi digital port D6
RELAY_ACTIVE_HIGH  = True    # Grove relays are active-HIGH
ENERGIZE_TO_UNLOCK = True    # typical fail-secure solenoid: power = unlocked

LOCKED   = "LOCKED"
UNLOCKED = "UNLOCKED"


def _energize_solenoid(energized):
    """Drive the relay so the solenoid is powered (True) or not (False),
    accounting for the relay being active-HIGH or active-LOW."""
    if RELAY_ACTIVE_HIGH:
        level = 1 if energized else 0
    else:
        level = 0 if energized else 1

    if ON_PI:
        grovepi.digitalWrite(RELAY_PORT, level)
    else:
        print(f"[SIM] relay D{RELAY_PORT} <- {level}  "
              f"({'energized' if energized else 'off'})")


def setup():
    """Call once at startup. Leaves the door LOCKED as a safe default."""
    if ON_PI:
        grovepi.pinMode(RELAY_PORT, "OUTPUT")
    lock()


def lock():
    """Lock the door."""
    _energize_solenoid(not ENERGIZE_TO_UNLOCK)   # locked = the de-energized state
    return LOCKED


def unlock():
    """Unlock the door (emergency / hazard / distress, per the spec)."""
    _energize_solenoid(ENERGIZE_TO_UNLOCK)
    return UNLOCKED


if __name__ == "__main__":
    print("Testing lock.py (Grove relay on D6)\n")
    print(f"  config: RELAY_ACTIVE_HIGH={RELAY_ACTIVE_HIGH}, "
          f"ENERGIZE_TO_UNLOCK={ENERGIZE_TO_UNLOCK}\n")
    print("setup() -> safe default:")
    setup()
    print(f"  state = {LOCKED}\n")
    print("unlock():")
    print(f"  state = {unlock()}\n")
    print("lock():")
    print(f"  state = {lock()}")
    print("\nDone.")