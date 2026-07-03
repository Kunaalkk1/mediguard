import os
import time

# ---- BCM GPIO -> sysfs PWM channel, per the overlay above -------------------
PIN_TO_CHANNEL = {
    12: 0,   # GPIO12 -> pwm0
    13: 1,   # GPIO13 -> pwm1
}

PWM_CHIP = 0                     # /sys/class/pwm/pwmchip0
PWM_FREQ_HZ = 1000               # both channels share one clock => same freq
_CHIP_PATH = f"/sys/class/pwm/pwmchip{PWM_CHIP}"

# Simulation when the sysfs PWM chip isn't present (e.g. running on a laptop).
SIMULATION = not os.path.isdir(_CHIP_PATH)

_pwm = {}                        # channel -> _HardwarePWM, created on first use

# RPi.GPIO is used ONLY for optional digital direction pins (plain output,
# no PWM => no thread). Imported lazily so the PWM path has zero dependency.
_GPIO = None
_gpio_ready = False


# ============================================================================
#  Hardware PWM channel (sysfs)
# ============================================================================
class _HardwarePWM:
    """One sysfs PWM channel. Exports, sets period, enables at 0% duty."""

    def __init__(self, chip: int, channel: int, freq_hz: float):
        self.channel = channel
        self.chip_path = f"/sys/class/pwm/pwmchip{chip}"
        self.pwm_path = f"{self.chip_path}/pwm{channel}"
        self.period_ns = int(1_000_000_000 / freq_hz)
        self._enabled = False
        self._export()
        # Order matters: duty must be <= period at all times.
        self._attr("duty_cycle", 0)
        self._attr("period", self.period_ns)
        self._attr("enable", 1)
        self._enabled = True

    def _attr(self, name: str, value) -> None:
        try:
            with open(f"{self.pwm_path}/{name}", "w") as f:
                f.write(str(value))
        except PermissionError as e:
            raise PermissionError(
                f"Permission denied writing {self.pwm_path}/{name}. "
                f"Run with sudo, or add a udev rule for /sys/class/pwm."
            ) from e

    def _export(self) -> None:
        if not os.path.isdir(self.chip_path):
            raise FileNotFoundError(
                f"{self.chip_path} missing. Add the pwm-2chan overlay under "
                f"[all] in /boot/firmware/config.txt and reboot."
            )
        if not os.path.isdir(self.pwm_path):
            with open(f"{self.chip_path}/export", "w") as f:
                f.write(str(self.channel))
            # Wait for the sysfs files to appear and settle.
            for _ in range(20):
                if os.path.exists(f"{self.pwm_path}/period"):
                    break
                time.sleep(0.05)
            time.sleep(0.1)      # let udev fix ownership/permissions

    def set_duty_percent(self, pct: float) -> None:
        duty_ns = int(self.period_ns * max(0.0, min(100.0, pct)) / 100)
        self._attr("duty_cycle", duty_ns)

    def close(self) -> None:
        if self._enabled:
            self._attr("enable", 0)
            self._enabled = False
        if os.path.isdir(self.pwm_path):
            try:
                with open(f"{self.chip_path}/unexport", "w") as f:
                    f.write(str(self.channel))
            except OSError:
                pass


def _channel_for(pin: int) -> int:
    if pin not in PIN_TO_CHANNEL:
        raise ValueError(
            f"GPIO{pin} is not a hardware-PWM pin in this config. "
            f"Use one of {sorted(PIN_TO_CHANNEL)} (GPIO12=light, GPIO13=fan)."
        )
    return PIN_TO_CHANNEL[pin]


# ============================================================================
#  Public API  (same signatures as the old GrovePi / RPi.GPIO version)
# ============================================================================
def setup_output(pin):
    """Prepare a pin. For PWM pins this exports+enables the sysfs channel."""
    if SIMULATION:
        print(f"[SIM] setup   GPIO{pin} as OUTPUT")
        return
    ch = _channel_for(pin)
    if ch not in _pwm:
        _pwm[ch] = _HardwarePWM(PWM_CHIP, ch, PWM_FREQ_HZ)


def write_pwm(pin, value):
    """
    Write an 8-bit PWM level (0-255) to a hardware-PWM pin. The 0-255 interface
    is kept so fan.py / light.py are unchanged; internally it maps to a duty %.
    """
    value = max(0, min(255, int(value)))
    duty = value / 255 * 100
    if SIMULATION:
        print(f"[SIM] PWM     GPIO{pin} <- {value:3d}/255  ({duty:.0f}% duty)")
        return value
    ch = _channel_for(pin)
    if ch not in _pwm:                       # lazy setup on first write
        _pwm[ch] = _HardwarePWM(PWM_CHIP, ch, PWM_FREQ_HZ)
    _pwm[ch].set_duty_percent(duty)
    return value


def write_digital(pin, on):
    """
    Drive a PLAIN digital pin HIGH/LOW (e.g. an L298N direction pin, if you
    wired it to the Pi). Uses RPi.GPIO -- a level set, not PWM, so no thread.
    """
    global _GPIO, _gpio_ready
    state = 1 if on else 0
    if SIMULATION:
        print(f"[SIM] DIGITAL GPIO{pin} <- {state}")
        return state
    if _GPIO is None:
        import RPi.GPIO as GPIO           # imported only if actually needed
        _GPIO = GPIO
        _GPIO.setmode(_GPIO.BCM)
        _GPIO.setwarnings(False)
        _gpio_ready = True
    _GPIO.setup(pin, _GPIO.OUT)
    _GPIO.output(pin, state)
    return state


def cleanup():
    """Release all PWM channels (and any digital pins). Call once on shutdown."""
    if SIMULATION:
        print("[SIM] cleanup")
        return
    for ch in list(_pwm):
        _pwm[ch].close()
        del _pwm[ch]
    if _gpio_ready and _GPIO is not None:
        _GPIO.cleanup()


if __name__ == "__main__":
    mode = "SIMULATION (laptop)" if SIMULATION else "REAL Pi hardware PWM"
    print(f"actuator_base loaded in {mode} mode.\n")
    try:
        setup_output(12)            # light channel
        write_pwm(13, 200)          # fan channel ~78%
        write_pwm(12, 64)           # light ~25%
        time.sleep(1)
    finally:
        cleanup()
    print("\nDone.")