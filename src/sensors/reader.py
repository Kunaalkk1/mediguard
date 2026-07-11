import time

from .grove_sensors import read_light, read_gas, read_motion, read_pressure
from .dht_reader import read_temperature_humidity
from .vitals import read_pulse_spo2


def read_all():

    # Sensors that return two values get unpacked first.
    pulse, spo2 = read_pulse_spo2()
    temperature, humidity = read_temperature_humidity()
    pressure_raw, on_bed = read_pressure()

    # SOS is intentionally NOT read here: the dedicated high-priority SOS watcher
    # thread polls the button directly, so reading it again in this batch would
    # only add I2C contention. The brain folds the latched SOS state back in.
    snapshot = {
        "pulse":        pulse,
        "spo2":         spo2,
        "motion":       read_motion(),
        "pressure_raw": pressure_raw,
        "on_bed":       on_bed,
        "light":        read_light(),
        "temperature":  temperature,
        "humidity":     humidity,
        "gas":          read_gas(),
        "sos":          0,
    }
    return snapshot


if __name__ == "__main__":
    print("Testing the full sensor snapshot\n")
    count = 0
    while True:
        count += 1
        snap = read_all()
        print(f"--- Snapshot {count} ---")
        for key, value in snap.items():
            print(f"  {key:14} = {value}")
        print()
        time.sleep(1)