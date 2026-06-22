"""
grovepi_driver.py
-----------------
A custom, DROP-IN replacement for the official `grovepi` library.

"""

import time
import struct
import random

GROVEPI_ADDR = 0x04

# Pin-mode and level constants
INPUT,  OUTPUT = 0, 1
LOW,    HIGH   = 0, 1

DHT11, DHT22 = 0, 1

# GrovePi firmware command bytes
_CMD_DIGITAL_READ  = 1
_CMD_DIGITAL_WRITE = 2
_CMD_ANALOG_READ   = 3
_CMD_ANALOG_WRITE  = 4    # PWM -- works ONLY on PWM ports D3, D5, D6
_CMD_PIN_MODE      = 5
_CMD_DHT           = 40

# Safe init: real bus on the Pi, simulation on a laptop
try:
    import smbus2
    bus = smbus2.SMBus(1)          # Raspberry Pi I2C-1
    SIMULATION = False
except (ImportError, FileNotFoundError, OSError):
    bus = None
    SIMULATION = True


# Private helpers: the only two functions that touch the bus
def _send(data):
    """Send a 4-byte command frame to the firmware (no-op in simulation)."""
    if SIMULATION:
        return
    bus.write_i2c_block_data(GROVEPI_ADDR, 0, data)


def _receive(n):
    """Read n bytes back from the firmware's register 1."""
    if SIMULATION:
        return [0] * n
    return bus.read_i2c_block_data(GROVEPI_ADDR, 1, n)


# the real grovepi library
def pinMode(pin, mode):
    """
    Set a pin as INPUT or OUTPUT. Must be done before reading/writing it.
    Firmware Command 5.
    """
    if isinstance(mode, str):
        mode = OUTPUT if mode.strip().upper() == "OUTPUT" else INPUT
    _send([_CMD_PIN_MODE, pin, mode, 0])


def digitalRead(pin):
    """
    Read 0 or 1 from a digital pin (set it INPUT first). 
    Firmware Command 1.
    """
    if SIMULATION:
        return random.choice([LOW, HIGH])
    _send([_CMD_DIGITAL_READ, pin, 0, 0])
    time.sleep(0.1)
    return _receive(4)[1]


def digitalWrite(pin, value):
    """
    Drive a digital pin HIGH or LOW (set it OUTPUT first). 
    Firmware Command 2.
    """
    _send([_CMD_DIGITAL_WRITE, pin, HIGH if value else LOW, 0])


def analogRead(pin):
    """
    Read a 10-bit value (0-1023) from an analog pin (A0/A1/A2). 
    Firmware Command 3.
    The firmware returns the result packed across two bytes.
    """
    if SIMULATION:
        return random.randint(0, 1023)
    _send([_CMD_ANALOG_READ, pin, 0, 0])
    time.sleep(0.1)
    data = _receive(4)
    return (data[1] << 8) | data[2]


def analogWrite(pin, value):
    """
    Write an 8-bit PWM value (0-255) to a PWM pin -- D3, D5 or D6 ONLY.
    Command 4. This is what the actuator drivers use to dim the light and
    vary fan speed. The value is clamped so a bad input can't go out of range.
    """
    value = max(0, min(255, int(value)))
    _send([_CMD_ANALOG_WRITE, pin, value, 0])
    return value


def dht(pin, module_type=DHT11):
    """
    Read (temperature_C, humidity_%) from a Grove DHT sensor. Command 40.
    Returns (None, None) on a failed read. The 0.6 s pause is required
    because the DHT protocol is slow and the firmware must finish the full
    read before it can answer.
    """
    if SIMULATION:
        return round(random.uniform(20.0, 26.0), 2), round(random.uniform(40.0, 60.0), 2)

    _send([_CMD_DHT, pin, module_type, 0])
    time.sleep(0.6)
    data = _receive(9)
    if data[0] != _CMD_DHT:                       # firmware should echo the command
        return None, None
    temperature = struct.unpack('f', bytes(data[1:5]))[0]
    humidity    = struct.unpack('f', bytes(data[5:9]))[0]
    if temperature == -1 and humidity == -1:      # firmware's error signal
        return None, None
    return round(temperature, 2), round(humidity, 2)


if __name__ == "__main__":
    mode = "SIMULATION (laptop)" if SIMULATION else "REAL GrovePi over I2C (Pi)"
    print(f"grovepi_driver loaded in {mode} mode.\n")

    pinMode(5, "INPUT")
    pinMode(3, "OUTPUT")

    print("Reads:")
    print(f"  digitalRead(5) = {digitalRead(5)}")
    print(f"  analogRead(0)  = {analogRead(0)}")
    t, h = dht(6, DHT11)
    print(f"  dht(6)         = {t} C, {h} %")

    print("\nWrites:")
    print(f"  analogWrite(3, 128) -> {analogWrite(3, 128)}  (PWM 0-255)")
    digitalWrite(4, HIGH)
    print("  digitalWrite(4, HIGH)  sent")