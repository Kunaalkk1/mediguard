"""
NON-BLOCKING blink: the main loop has to keep running (reading sensors,
driving other actuators), so we must NEVER sleep. Instead you call
set_from_sos(pressed, now) every loop pass; while SOS is pressed the LED
flips itself each time BLINK_INTERVAL has elapsed, and when SOS is released
it goes off. The clock does the timing, not a sleep.
"""

import os, sys
try:
    from grove_base import ON_PI, grovepi
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sensors"))
    from grove_base import ON_PI, grovepi

RED_LED_PORT   = 3      # GrovePi digital port D3
BLINK_INTERVAL = 0.5     # seconds between flips (0.5s on, 0.5s off)

# memory: is the LED lit, and when did it last flip? 
_led_on = False
_last_toggle = None


def setup():
    """Call once at startup. Starts off."""
    if ON_PI:
        grovepi.pinMode(RED_LED_PORT, "OUTPUT")
    _write(False)


def _write(state):
    global _led_on
    _led_on = state
    if ON_PI:
        grovepi.digitalWrite(RED_LED_PORT, 1 if state else 0)
    else:
        print(f"[SIM] red LED {'ON ' if state else 'off'}")


def set_from_sos(sos_pressed, now):
    """
    Blink while SOS is pressed; off when it isn't. Call every loop pass with the current time (time.time() in real use). 
    Returns True if lit right now.
    """
    global _last_toggle

    if not sos_pressed:
        if _led_on or _last_toggle is not None:
            _write(False)
        _last_toggle = None
        return False

    # SOS is pressed -> blink
    if _last_toggle is None:                     # just started: light it now
        _last_toggle = now
        _write(True)
    elif now - _last_toggle >= BLINK_INTERVAL:    # interval elapsed: flip
        _write(not _led_on)
        _last_toggle = now
    return _led_on


if __name__ == "__main__":
    print("Testing red_led.py (Grove port D3)\n")
    setup()
    print("SOS pressed from t=0.3s to t=1.5s -- watch it blink:\n")
    # (time, sos_pressed) -- a loop sampling every 0.3s
    timeline = [(0.0, False), (0.3, True), (0.6, True), (0.9, True),
                (1.2, True), (1.5, True), (1.8, False)]
    for now, pressed in timeline:
        lit = set_from_sos(pressed, now)
        print(f"  t={now:.1f}s  SOS={pressed!s:5}  ->  LED {'lit' if lit else 'dark'}")
    print("\nDone.")