import time

AWAKE = "Awake"
RESTING = "Resting"
OUT_OF_BED = "Out of bed"
DISTRESSED = "Distressed"

STATES = [AWAKE, RESTING, OUT_OF_BED, DISTRESSED]

class PatientStateTracker:
    
    def __init__(
        self,
        rest_seconds=15 * 60,     # stillness this long (sec) -> Resting  (15 min)
        distress_window=60,       # judge "too much movement" over this many sec
        distress_fraction=0.7,    # if this fraction of recent readings show motion -> Distressed
        distress_min_samples=5,   # need at least this many readings before deciding Distressed
    ):
        self.rest_seconds = rest_seconds
        self.distress_window = distress_window
        self.distress_fraction = distress_fraction
        self.distress_min_samples = distress_min_samples

        self._last_motion_time = None
        self._motion_window = []

    def update(self, snapshot, now=None):
    
        if now is None:
            now = time.time()

        on_bed = snapshot["on_bed"]
        motion = snapshot["motion"]

        if not on_bed:
            self._last_motion_time = now
            self._motion_window = []
            return OUT_OF_BED

        if self._last_motion_time is None:
            self._last_motion_time = now

        self._motion_window.append((now, motion))
        cutoff = now - self.distress_window
        self._motion_window = [(t, m) for (t, m) in self._motion_window if t >= cutoff]

        if motion:
            self._last_motion_time = now

        if len(self._motion_window) >= self.distress_min_samples:
            moving = sum(m for (_t, m) in self._motion_window)
            fraction = moving / len(self._motion_window)
            if fraction >= self.distress_fraction:
                return DISTRESSED
            
        still_for = now - self._last_motion_time
        if still_for >= self.rest_seconds:
            return RESTING

        return AWAKE


if __name__ == "__main__":

    def snap(on_bed, motion):
        """Minimal snapshot with only the fields state.py reads."""
        return {"on_bed": on_bed, "motion": motion}

    # rest after 2s of stillness; distress judged over a 3s window.
    tracker = PatientStateTracker(
        rest_seconds=2,
        distress_window=3,
        distress_fraction=0.7,
        distress_min_samples=3,
    )

    t = 0.0
    def step(on_bed, motion, label):
        global t
        result = tracker.update(snap(on_bed, motion), now=t)
        print(f"  t={t:4.1f}s  on_bed={on_bed!s:5}  motion={motion}  ->  {result:11}  ({label})")
        t += 1.0

    print("Testing state.py\n")

    print("Out of bed (no one on the pad):")
    step(False, 0, "expect Out of bed")
    print()

    print("Patient gets on the bed and moves normally (some motion):")
    step(True, 1, "expect Awake")
    step(True, 0, "expect Awake")
    step(True, 1, "expect Awake")
    step(True, 0, "expect Awake")
    print()

    print("Patient goes still and stays still -> should become Resting:")
    step(True, 0, "expect Resting (2s since last motion)")
    step(True, 0, "expect Resting")
    step(True, 0, "expect Resting")
    print()

    print("Patient starts thrashing (motion every reading) -> Distressed:")
    step(True, 1, "filling window")
    step(True, 1, "filling window")
    step(True, 1, "expect Distressed")
    step(True, 1, "expect Distressed")
    print()

    print("Patient leaves the bed again:")
    step(False, 0, "expect Out of bed")

    print("\nDone.")