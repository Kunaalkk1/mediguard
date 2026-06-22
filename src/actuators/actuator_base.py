"""
The Grove digital ports (D2-D8) are pins on the GrovePi's onboard ATmega chip.
Every grovepi.digitalWrite / analogWrite is actually an I2C message to that
chip, which then moves its pin -- so the (flaky) GrovePi firmware sits in the
path. The Pi's GPIO pins are driven by the Pi itself: no firmware, no I2C hop.

"""

try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)        # refer to pins by their GPIOxx number
    GPIO.setwarnings(False)
    SIMULATION = False
except (ImportError, RuntimeError):
    # ImportError -> not on a Pi (your laptop). RuntimeError -> lib present but no GPIO hardware access.
    GPIO = None
    SIMULATION = True

PWM_FREQ_HZ = 1000               # 1 kHz: smooth for both the fan and the LED light
_pwm = {}                        # pin -> RPi.GPIO PWM object, created on first use


def setup_output(pin):
    """Set a BCM GPIO pin as a digital output."""
    if SIMULATION:
        print(f"[SIM] setup   GPIO{pin} as OUTPUT")
        return
    GPIO.setup(pin, GPIO.OUT)


def write_pwm(pin, value):
    """
    Write an 8-bit PWM level (0-255) to a pin. We keep the 0-255 interface so
    callers (light.py, fan.py) are unchanged from the GrovePi days; internally
    it maps to RPi.GPIO's 0-100% duty cycle.
    """
    value = max(0, min(255, int(value)))
    duty = value / 255 * 100
    if SIMULATION:
        print(f"[SIM] PWM     GPIO{pin} <- {value:3d}/255  ({duty:.0f}% duty)")
        return value
    if pin not in _pwm:                     # first use: set up the pin + PWM
        GPIO.setup(pin, GPIO.OUT)
        _pwm[pin] = GPIO.PWM(pin, PWM_FREQ_HZ)
        _pwm[pin].start(0)
    _pwm[pin].ChangeDutyCycle(duty)
    return value


def write_digital(pin, on):
    """Drive a digital pin fully HIGH (1) or LOW (0)."""
    state = 1 if on else 0
    if SIMULATION:
        print(f"[SIM] DIGITAL GPIO{pin} <- {state}")
        return state
    GPIO.output(pin, state)
    return state


def cleanup():
    """Release the pins. Call once on shutdown."""
    if SIMULATION:
        print("[SIM] cleanup")
        return
    for p in _pwm.values():
        p.stop()
    GPIO.cleanup()


if __name__ == "__main__":
    mode = "SIMULATION (laptop)" if SIMULATION else "REAL Pi GPIO"
    print(f"actuator_base loaded in {mode} mode.\n")
    setup_output(17)
    write_pwm(18, 200)
    write_digital(17, True)
    write_digital(17, False)
    print("\nDone.")