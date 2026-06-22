"""
Controls the room light, wired to ONE channel of the L298N (output pins OUT3/OUT4). 
Brightness is set by PWM on that channel's ENABLE pin, ENB:more duty cycle = brighter.

WIRING ASSUMPTION: the L298N direction pins IN3/IN4 are tied to fixed levels
in hardware (one HIGH, one LOW), so the light always gets one polarity and we
only ever drive ENB. If instead you wire IN3/IN4 to Pi pins, set them once in
setup() with write_digital() -- see the note there.
"""

from actuator_base import setup_output, write_pwm

LIGHT_PWM_PIN = 17    # BCM GPIO17 (physical pin 11) -> L298N ENB (light)


def setup():
    """Call once at startup."""
    setup_output(LIGHT_PWM_PIN)
    # If IN3/IN4 are wired to the Pi instead of tied in hardware, do e.g.:
    #   from actuator_base import write_digital
    #   setup_output(IN3_PIN); setup_output(IN4_PIN)
    #   write_digital(IN3_PIN, 1); write_digital(IN4_PIN, 0)   # fix one polarity


def set_brightness(percent):
    """Set light brightness from 0 to 100 percent."""
    percent = max(0, min(100, percent))         
    pwm = round(percent / 100 * 255)              # 0-100%  ->  0-255 PWM
    write_pwm(LIGHT_PWM_PIN, pwm)
    return pwm


if __name__ == "__main__":
    print("Testing light.py (L298N ENB on GPIO17)\n")
    setup()
    for pct in [0, 25, 50, 75, 100]:
        pwm = set_brightness(pct)
        print(f"  set_brightness({pct:3}%) -> PWM {pwm}")
    print("\nDone.")