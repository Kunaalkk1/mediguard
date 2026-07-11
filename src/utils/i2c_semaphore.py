"""
i2c_lock.py
-----------
A single shared lock guarding the I2C bus.

Only ONE I2C conversation can happen at a time, so any thread that reads over I2C must acquire this lock first and release it after.
This prevents two reads from overlapping and corrupting each other.

Import THIS lock everywhere I2C is used, so all users share one guard.
"""

import threading

i2c_lock = threading.Semaphore(1)  # a semaphore with a single permit is a Lock()