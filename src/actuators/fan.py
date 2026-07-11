"""
Controls the fan, wired to ONE channel of the L298N (output pins OUT1/OUT2).
Speed is set by hardware PWM on that channel's ENABLE pin, ENA:
more duty cycle = faster.

WIRING ASSUMPTION: the direction pins IN1/IN2 are tied to fixed levels in
hardware so the fan always spins one way, and we only drive ENA.

NOTE: moved from GPIO18 -> GPIO13 because hardware PWM lives on GPIO12/13.
GPIO13 = sysfs pwm1 (physical pin 33).
"""

from .actuator_base import setup_output, write_pwm

FAN_PWM_PIN = 13      # GPIO13 -> L298N ENA (fan)   [hardware pwm1]
MIN_START   = 30      # below this PWM a small fan may stall; tune on the bench

# The system talks in a 0-100 speed scale everywhere (GUI, PDDL, MQTT), but the
# hardware is calibrated so 100 speed = 40% PWM duty. So the semantic 0-100 is
# mapped into a 0-HW_MAX_DUTY duty range before driving PWM.
HW_MAX_DUTY = 40      # percent duty at speed 100


def setup():
    """Call once at startup."""
    setup_output(FAN_PWM_PIN)


def set_speed(percent):
    """Set fan speed on the 0-100 scale (mapped to 0-HW_MAX_DUTY% duty)."""
    percent = max(0, min(100, percent))
    if percent == 0:
        pwm = 0
    else:
        duty_percent = percent * HW_MAX_DUTY / 100   # 0-100 speed -> 0-40% duty
        pwm = round(duty_percent / 100 * 255)        # 0-40% duty  -> 0-255 PWM
        pwm = max(pwm, MIN_START)                    # don't let it stall
    write_pwm(FAN_PWM_PIN, pwm)
    return pwm


if __name__ == "__main__":
    print("Testing fan.py (L298N ENA on GPIO13, hardware PWM)\n")
    setup()
    while True:
        # pct = int(input("Enter fan speed (0-100%): "))
        pwm = set_speed(50)
        print(f"  set_speed -> PWM {pwm}")
    print("\n(Note 5% was nudged up to the stall floor so the fan still spins.)")
    print("Done.")  