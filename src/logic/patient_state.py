"""
Works out the PATIENT STATE from snapshots:

    Awake  /  Resting  /  Out of bed  /  Distressed

Per the spec:
  - Distress   : irregular heart rhythm OR low oxygen (bad vitals).   <-- VITALS
  - Out-of-bed : pressure sensor detects no one on the bed.
  - Resting    : on the bed, no movement for over 15 minutes.
  - Awake      : on the bed, movement seen within the last 15 minutes.
"""

import time

AWAKE      = "Awake"
RESTING    = "Resting"
OUT_OF_BED = "Out of bed"
DISTRESS   = "Distressed"

STATES = [AWAKE, RESTING, OUT_OF_BED, DISTRESS]


class PatientStateTracker:
    def __init__(
        self,
        rest_seconds=15 * 60,   # no movement this long -> Resting (15 min)
        pulse_low=50,           # bpm: below this = irregular / unsafe
        pulse_high=120,         # bpm: above this = irregular / unsafe
        spo2_min=90,            # %:   below this = low oxygen
    ):
        self.rest_seconds = rest_seconds
        self.pulse_low    = pulse_low
        self.pulse_high   = pulse_high
        self.spo2_min     = spo2_min
        self._last_motion_time = None      # the only memory we keep

    def _vitals_bad(self, pulse, spo2):
        """True only if a VALID reading is outside the safe range. None means no trustworthy reading, which is NOT distress."""
        
        if pulse is not None and (pulse < self.pulse_low or pulse > self.pulse_high):
            return True
        if spo2 is not None and spo2 < self.spo2_min:
            return True
        return False

    def update(self, snapshot, now=None):
        """Feed one snapshot, get back the patient-state label."""
        
        if now is None:
            now = time.time()

        on_bed = snapshot["on_bed"]
        motion = snapshot["motion"]
        pulse  = snapshot.get("pulse")
        spo2   = snapshot.get("spo2")

        # 1) Distress: bad vitals beat everything else.
        if self._vitals_bad(pulse, spo2):
            return DISTRESS

        # 2) Out of bed: nobody on the pad. Reset the stillness clock so a returning patient starts fresh.
        if not on_bed:
            self._last_motion_time = now
            return OUT_OF_BED

        # On the bed: start the stillness clock on the first reading, and reset it whenever movement is seen.
        if self._last_motion_time is None:
            self._last_motion_time = now
        if motion:
            self._last_motion_time = now

        still_for = now - self._last_motion_time

        # 3) Resting if still long enough, else 4) Awake.
        if still_for >= self.rest_seconds:
            return RESTING
        
        # 4) Awake if none of the situations satisfy.
        return AWAKE


if __name__ == "__main__":
    # Feed a short TIMELINE of live snapshots through one tracker, advancing a fake clock, so you can see real sensor values AND the time-based states 
    # (Resting needs sustained stillness, so a single snapshot can't show it).
    # Uses the simulator so it runs on a laptop; on the Pi, swap this import for:  from reader import read_all
    import os, sys
    try:
        from simulator import read_all
    except ImportError:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sensors"))
        from simulator import read_all

    print("state.py -- live readings -> Patient State")
    print("(simulator data; on the Pi import read_all from reader instead)\n")

    tracker = PatientStateTracker(rest_seconds=3)   # short rest window for the demo

    # (scenario, fake_time_seconds)
    timeline = [
        ("out_of_bed", 0),
        ("awake",      1),
        ("resting",    2),    # still, but not still long enough yet -> Awake
        ("resting",    5),    # now still >= 3s -> Resting
        ("distressed", 6),    # bad vitals -> Distressed (even while on bed)
        ("out_of_bed", 7),
    ]

    for scenario, t in timeline:
        snap = read_all(scenario)
        result = tracker.update(snap, now=t)
        print(f"t={t}s  [{scenario}]")
        print(f"  readings: on_bed={snap['on_bed']}  motion={snap['motion']}  "
              f"pulse={snap['pulse']}  spo2={snap['spo2']}")
        print(f"  -> Patient State: {result}")
        print()

    print("Done.")