import random
import math
import time
from collections import deque
from grove_base import ON_PI, grovepi

DHT_PORT = 4          # digital D4   # CONFIRM ON PI
DHT_TYPE = 0          # 0 = DHT11 (blue)
WINDOW = 50           # average over the last 50 readings
MIN_INTERVAL = 2.0    # seconds: DHT can't be read faster than this

_temp_buffer = deque(maxlen=WINDOW)
_humidity_buffer = deque(maxlen=WINDOW)
_last_read_time = 0.0


def _take_one_reading():
    if ON_PI:
        temperature, humidity = grovepi.dht(DHT_PORT, DHT_TYPE)   # CONFIRM ON PI
        if not math.isnan(temperature) and not math.isnan(humidity):
            _temp_buffer.append(temperature)
            _humidity_buffer.append(humidity)
    else:
        _temp_buffer.append(round(random.uniform(20.0, 28.0), 1))
        _humidity_buffer.append(round(random.uniform(40.0, 65.0), 1))


def read_temperature_humidity():
    global _last_read_time
    now = time.time()

    # Only hit the hardware if enough time has passed
    if now - _last_read_time >= MIN_INTERVAL:
        _take_one_reading()
        _last_read_time = now

    # Return the average of whatever we have so far
    if len(_temp_buffer) == 0:
        return (None, None)
    avg_temp = round(sum(_temp_buffer) / len(_temp_buffer), 1)
    avg_humidity = round(sum(_humidity_buffer) / len(_humidity_buffer), 1)
    return (avg_temp, avg_humidity)


if __name__ == "__main__":
    print("Testing non-blocking DHT reader...\n")
    for i in range(8):
        t, h = read_temperature_humidity()
        print(f"  Call {i+1}: avg temp = {t} C, avg humidity = {h} %  (buffer size {len(_temp_buffer)})")
        time.sleep(0.5)
    print("Done.")