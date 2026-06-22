"""
Shared hardware-detection helper for all sensor drivers.

grovepi_driver decides whether a real I2C bus exists: it sets SIMULATION
True on a laptop (no bus) and False on the Pi (bus present). We just read
that here. ON_PI is the friendlier inverse, so drivers can say "if ON_PI".
"""

import grovepi_driver as grovepi

ON_PI = not grovepi.SIMULATION    # True only when grovepi_driver found a real bus