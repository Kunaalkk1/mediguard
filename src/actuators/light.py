"""
Controls the room light, wired to ONE channel of the L298N (output pins OUT3/OUT4).
Brightness is set by hardware PWM on that channel's ENABLE pin, ENB:
more duty cycle = brighter.

WIRING ASSUMPTION: the L298N direction pins IN3/IN4 are tied to fixed levels
in hardware (one HIGH, one LOW), so the light always gets one polarity and we
only ever drive ENB. If instead you wire IN3/IN4 to Pi pins, set them once in
setup() with write_digital() -- see the note there.

NOTE: moved from GPIO17 -> GPIO12 because hardware PWM lives on GPIO12/13.
GPIO12 = sysfs pwm0 (physical pin 32). (GPIO17 has no hardware PWM at all.)
"""

from .actuator_base import setup_output, write_pwm

LIGHT_PWM_PIN = 12    # GPIO12 -> L298N ENB (light)   [hardware pwm0]

# The system talks in a 0-100 brightness scale everywhere (GUI, PDDL, MQTT),
# but the hardware is calibrated so 100 brightness = 40% PWM duty. So the
# semantic 0-100 is mapped into a 0-HW_MAX_DUTY duty range before driving PWM.
HW_MAX_DUTY = 40      # percent duty at brightness 100


def setup():
    """Call once at startup."""
    setup_output(LIGHT_PWM_PIN)
    # If IN3/IN4 are wired to the Pi instead of tied in hardware, do e.g.:
    #   from .actuator_base import write_digital, setup_output
    #   setup_output(IN3_PIN); setup_output(IN4_PIN)
    #   write_digital(IN3_PIN, 1); write_digital(IN4_PIN, 0)   # fix one polarity


def set_brightness(percent):
    """Set light brightness on the 0-100 scale (mapped to 0-HW_MAX_DUTY% duty)."""
    percent = max(0, min(100, percent))
    duty_percent = percent * HW_MAX_DUTY / 100    # 0-100 brightness -> 0-40% duty
    pwm = round(duty_percent / 100 * 255)         # 0-40% duty       -> 0-255 PWM
    write_pwm(LIGHT_PWM_PIN, pwm)
    return pwm


if __name__ == "__main__":
    print("Testing light.py (L298N ENB on GPIO12, hardware PWM)\n")
    setup()
    while True:
        pwm = set_brightness(70)
        print(f"  set_brightness -> PWM {pwm}")
    print("\nDone.")