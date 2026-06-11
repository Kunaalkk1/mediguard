import smbus2
import struct
import time
import max30102
import hrcalc

GROVEPI_ADDR = 0x04
bus = smbus2.SMBus(1)

# Pin modes
INPUT  = 0
OUTPUT = 1

# Digital levels
LOW  = 0
HIGH = 1

# DHT sensor module types
DHT11 = 0   # Blue module
DHT22 = 1   # White module (also AM2302)

# Pin assignments — analog
PIN_GAS      = 0   # A0 — MQ135 gas sensor
PIN_LIGHT    = 1   # A1 — Grove light sensor
PIN_PRESSURE = 2   # A2 — RP-S40-T FSR pressure sensor

# Pin assignments — digital
PIN_PIR      = 5   # D5 — Grove PIR motion sensor
PIN_DHT      = 6   # D6 — Grove DHT temperature/humidity sensor

# Sensor read intervals (seconds)
INTERVAL_FAST   = 0.1   # PIR, light, gas, pressure
INTERVAL_MEDIUM = 2.0   # DHT (slow sensor, 0.6s blocking read internally)
INTERVAL_SLOW   = 5.0   # MAX30102 (needs buffer accumulation)

# MAX30102 instance (I2C-1, address 0x57)
max_sensor = max30102.MAX30102()


def pin_mode(bus, pin, mode):
    """
    Set a pin as INPUT or OUTPUT.
    Must be called before digital_write or digital_read on a pin.
    Command 5: pinMode(pin, mode)
    """
    bus.write_i2c_block_data(GROVEPI_ADDR, 0, [5, pin, mode, 0])


def digital_write(bus, pin, value):
    """
    Write a HIGH or LOW value to a digital output pin.
    Pin must be set to OUTPUT mode first via pin_mode().
    Command 2: digitalWrite(pin, value)
    """
    bus.write_i2c_block_data(GROVEPI_ADDR, 0, [2, pin, value, 0])


def digital_read(bus, pin):
    """
    Read HIGH or LOW from a digital input pin.
    Pin must be set to INPUT mode first via pin_mode().
    Command 1: digitalRead(pin)
    """
    bus.write_i2c_block_data(GROVEPI_ADDR, 0, [1, pin, 0, 0])
    time.sleep(0.1)
    data = bus.read_i2c_block_data(GROVEPI_ADDR, 1, 4)
    return data[1]


def analog_read(bus, pin):
    """
    Read a 10-bit analog value (0-1023) from an analog input pin.
    Command 3: analogRead(pin)
    The firmware returns 4 bytes; the result is packed across bytes 1 and 2.
    """
    bus.write_i2c_block_data(GROVEPI_ADDR, 0, [3, pin, 0, 0])
    time.sleep(0.1)
    data = bus.read_i2c_block_data(GROVEPI_ADDR, 1, 4)
    return (data[1] << 8) | data[2]


def dht(bus, pin, module_type=DHT11):
    """
    Read temperature and humidity from a Grove DHT sensor.

    module_type: DHT11 (0) for the blue module,
                 DHT22 (1) for the white module / AM2302.

    Command 40: dht(pin, module_type)
    The firmware responds with:
      byte 0    — echo of command byte (40)
      bytes 1-4 — temperature as IEEE 754 float
      bytes 5-8 — humidity as IEEE 754 float

    Returns (temperature_celsius, humidity_percent), or (None, None) on error.
    A 0.6 s delay is required because the DHT protocol is slow and the
    GrovePi firmware must complete the full sensor read before responding.
    """
    bus.write_i2c_block_data(GROVEPI_ADDR, 0, [40, pin, module_type, 0])
    time.sleep(0.6)
    data = bus.read_i2c_block_data(GROVEPI_ADDR, 1, 9)

    if data[0] != 40:
        return None, None

    temperature = struct.unpack('f', bytes(data[1:5]))[0]
    humidity    = struct.unpack('f', bytes(data[5:9]))[0]

    if temperature == -1 and humidity == -1:
        return None, None

    return round(temperature, 2), round(humidity, 2)


def mq135_read(bus, pin=PIN_GAS):
    """
    Read raw analog value from MQ135 air quality / gas sensor.
    Returns a raw value (0-1023); higher = more gas concentration.

    The MQ135 requires a 24-48 hour burn-in period before readings
    are reliable. Allow ~3 minutes warm-up after each power-on.

    For calibrated PPM readings, the raw value must be converted using
    the sensor's Rs/R0 curve — this returns the raw ADC value only.
    """
    return analog_read(bus, pin)


def light_sensor_read(bus, pin=PIN_LIGHT):
    """
    Read light intensity from a Grove Light Sensor (v1.x).
    Returns a raw analog value (0-1023); higher values indicate more light.

    The Grove Light Sensor is a pure analog device (LDR + resistor divider),
    so no special command is needed — this is a thin wrapper around analog_read().
    """
    return analog_read(bus, pin)


def pressure_sensor_read(bus, pin=PIN_PRESSURE):
    """
    Read force from a RP-S40-T FSR (Force Sensitive Resistor) via voltage divider.
    Returns a raw analog value (0-1023); higher = more force applied.

    Wiring (voltage divider):
      3.3V ── FSR ──┬── 27kΩ ── GND
                    │
                   A2 (analog read)

    A 27kΩ resistor is chosen to place the ADC in the sensitive mid-range
    across the 20-25 g target force window (~484-533 ADC counts).
    """
    return analog_read(bus, pin)


def pir_read(bus, pin=PIN_PIR):
    """
    Read motion detection state from a Grove PIR sensor.
    Returns HIGH (1) if motion is detected, LOW (0) otherwise.

    PIR outputs a digital HIGH/LOW signal only — must be on a digital pin.
    Pin must be set to INPUT mode first via pin_mode().
    """
    return digital_read(bus, pin)


def max30102_read():
    """
    Read heart rate (BPM) and SpO2 (%) from the MAX30102 sensor on I2C-1.

    The MAX30102 continuously fills an internal FIFO buffer with red and
    IR LED samples. hrcalc.calc_hr_and_spo2() requires at least 100 samples
    to compute reliable results — this function drains the FIFO until enough
    samples are accumulated before calculating.

    Returns (heart_rate_bpm, spo2_percent) as floats,
            or (None, None) if the finger is not detected or signal is too weak.

    Note: valid_hr and valid_spo2 flags from hrcalc are checked before
    returning — invalid results are suppressed to None to avoid misleading data.
    """
    red_buffer = []
    ir_buffer  = []

    # Accumulate 100 samples from the FIFO (~1 second at 100 Hz sample rate)
    while len(red_buffer) < 100:
        num_samples = max_sensor.get_data_present()
        if num_samples > 0:
            for _ in range(num_samples):
                red, ir = max_sensor.read_fifo()
                red_buffer.append(red)
                ir_buffer.append(ir)
        else:
            time.sleep(0.01)  # Wait briefly for FIFO to fill

    hr, valid_hr, spo2, valid_spo2 = hrcalc.calc_hr_and_spo2(
        ir_buffer[:100], red_buffer[:100]
    )

    heart_rate = round(hr, 1)  if valid_hr   else None
    spo2_value = round(spo2, 1) if valid_spo2 else None

    return heart_rate, spo2_value


def setup():
    """
    Initialise all pin modes. Call once at startup before the main loop.
    Analog pins (A0-A2) do not require pin_mode; only digital pins do.
    """
    pin_mode(bus, PIN_PIR, INPUT)
    pin_mode(bus, PIN_DHT, INPUT)
    max_sensor.setup()
    max_sensor.set_wire_speed(400000)   # 400 kHz fast-mode I2C
    max_sensor.set_sample_rate(100)     # 100 samples/sec
    max_sensor.set_led_current(6.4)     # LED drive current in mA


def read_all_sensors():
    """
    Non-blocking polling loop that reads all sensors at their own intervals.
    Each sensor tracks its own last_read timestamp so slower sensors (DHT,
    MAX30102) are not read every iteration, while faster sensors (PIR, light,
    gas, pressure) are read more frequently.

    Call setup() once before entering this loop.

    Sensor read frequencies:
      INTERVAL_FAST   (0.1 s)  — PIR, light, gas, pressure
      INTERVAL_MEDIUM (2.0 s)  — DHT temperature/humidity
      INTERVAL_SLOW   (5.0 s)  — MAX30102 heart rate / SpO2
    """

    last_read = {
        'fast': 0,
        'dht':  0,
        'max':  0,
    }

    while True:
        now = time.monotonic()

        # --- Fast sensors: PIR, light, gas, pressure (every 0.1 s) ----------
        if now - last_read['fast'] >= INTERVAL_FAST:
            last_read['fast'] = now

            motion   = pir_read(bus)
            light    = light_sensor_read(bus)
            gas      = mq135_read(bus)
            pressure = pressure_sensor_read(bus)

            print(f"[FAST]     PIR={motion}  Light={light}  Gas={gas}  Pressure={pressure}")

        # --- Medium sensor: DHT temperature/humidity (every 2.0 s) ----------
        if now - last_read['dht'] >= INTERVAL_MEDIUM:
            last_read['dht'] = now

            temp, humidity = dht(bus, PIN_DHT, DHT11)
            if temp is not None:
                print(f"[DHT]      Temp={temp}°C  Humidity={humidity}%")
            else:
                print("[DHT]      Read failed")

        # --- Slow sensor: MAX30102 heart rate / SpO2 (every 5.0 s) ----------
        if now - last_read['max'] >= INTERVAL_SLOW:
            last_read['max'] = now

            hr, spo2 = max30102_read()
            if hr is not None:
                print(f"[MAX30102] HR={hr} BPM  SpO2={spo2}%")
            else:
                print("[MAX30102] No finger detected or signal too weak")

        # Small sleep to yield CPU — does not affect timing accuracy since
        # all scheduling is done via time.monotonic() comparisons above
        time.sleep(0.01)


if __name__ == "__main__":
    setup()
    read_all_sensors()