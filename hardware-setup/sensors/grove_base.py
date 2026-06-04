"""
Shared hardware-detection helper for all sensor drivers.

It tries to load the real GrovePi library. On the Raspberry Pi this
succeeds, so ON_PI becomes True and drivers use real hardware. On your
laptop the library doesn't exist, so ON_PI becomes False and drivers
return fake values instead of crashing.

"""

try:
    import grovepi                # the real hardware library (Pi only)
    ON_PI = True                  # import worked -> we're on the Pi
except ImportError:
    grovepi = None                # no library on the laptop
    ON_PI = False                 # import failed -> we're on the laptop