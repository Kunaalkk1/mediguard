"""

It's an ACTIVE buzzer (makes its own tone), so control is just on/off:
a HIGH sounds it, a LOW silences it. No PWM.

"""

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sensors"))
from grove_base import ON_PI, grovepi

BUZZER_PORT = 5      # GrovePi digital port D5


def setup():
    """Call once at startup. Starts silent."""
    if ON_PI:
        grovepi.pinMode(BUZZER_PORT, "OUTPUT")
    off()


def _write(state):
    if ON_PI:
        grovepi.digitalWrite(BUZZER_PORT, 1 if state else 0)
    else:
        print(f"[SIM] buzzer {'ON ' if state else 'off'}  (D{BUZZER_PORT})")


def on():
    """Sound the buzzer."""
    _write(True)
    return "ON"


def off():
    """Silence the buzzer."""
    _write(False)
    return "OFF"


def set_from_sos(sos_pressed):
    """Buzzer ON while the SOS button is pressed, OFF otherwise."""
    return on() if sos_pressed else off()


if __name__ == "__main__":
    print("Testing buzzer.py (Grove port D5)\n")
    setup()
    print("Buzzer follows the SOS button:")
    for pressed in [False, True, True, False]:
        state = set_from_sos(pressed)
        print(f"  SOS pressed = {pressed!s:5}  ->  buzzer {state}")
    print("\nDone.")