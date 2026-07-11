"""
vitals.py -- software/virtual vital-signs sensor (pulse + SpO2).

The physical MAX30102 SpO2/pulse sensor was removed: a hospital-grade distress
reading cannot be produced safely on the bench, so a genuine "medical
emergency" can never be demonstrated from the hardware. Instead, vitals are a
simulated (software-based) sensor -- allowed by the project spec -- that
normally reports healthy values. A distress reading is injected on demand from
the dashboard via runtime_flags.vitals_emergency (see src/main.py).

Returning (pulse, spo2). Either may be None if no trustworthy reading exists;
None is explicitly NOT treated as distress downstream.
"""

import random

# Healthy resting ranges. Kept narrow so normal operation never trips the
# distress thresholds in logic/patient_state.py.
HEALTHY_PULSE = (62, 95)     # bpm
HEALTHY_SPO2 = (96, 100)     # %


def read_pulse_spo2():
    """Return one healthy (pulse, spo2) reading."""
    pulse = random.randint(*HEALTHY_PULSE)
    spo2 = random.randint(*HEALTHY_SPO2)
    return (pulse, spo2)


if __name__ == "__main__":
    print("Testing software vitals sensor\n")
    for i in range(5):
        pulse, spo2 = read_pulse_spo2()
        print(f"  Reading {i + 1}: pulse = {pulse} BPM, SpO2 = {spo2} %")
