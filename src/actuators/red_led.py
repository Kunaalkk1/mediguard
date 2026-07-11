"""
NON-BLOCKING driver: the main loop keeps running (reading sensors, driving
other actuators), so we must NEVER sleep. Call apply(mode, now) every loop pass
with the current time; the clock does the timing, not a sleep.

Modes:
  "off"   -> dark
  "on"    -> solid on   (critical states: hazardous / emergency / distress)
  "blink" -> pulsing    (patient out of bed)
"""

from sensors.grove_base import ON_PI, grovepi

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
    if state == _led_on:
        return
    _led_on = state
    if ON_PI:
        grovepi.digitalWrite(RED_LED_PORT, 1 if state else 0)
    else:
        print(f"[SIM] red LED {'ON ' if state else 'off'}")


def apply(mode, now):
    """Drive the LED for one loop pass. Returns True if lit right now."""
    global _last_toggle

    if mode == "off":
        _write(False)
        _last_toggle = None
        return False

    if mode == "on":                              # solid, no blinking
        _write(True)
        _last_toggle = None
        return True

    # "blink"
    if _last_toggle is None:                       # just started: light it now
        _last_toggle = now
        _write(True)
    elif now - _last_toggle >= BLINK_INTERVAL:     # interval elapsed: flip
        _write(not _led_on)
        _last_toggle = now
    return _led_on


if __name__ == "__main__":
    print("Testing red_led.py (Grove port D3)\n")
    setup()
    print("blink from t=0.3s to t=1.5s, then solid on, then off:\n")
    timeline = [(0.0, "off"), (0.3, "blink"), (0.6, "blink"), (0.9, "blink"),
                (1.2, "blink"), (1.5, "on"), (1.8, "off")]
    for now, mode in timeline:
        lit = apply(mode, now)
        print(f"  t={now:.1f}s  mode={mode:5}  ->  LED {'lit' if lit else 'dark'}")
    print("\nDone.")