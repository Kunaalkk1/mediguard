"""
Why this file exists guys?
  reader.py calls the real drivers and gives you whatever values they
  happen to produce, so you can't *control* what comes out. simulator.py
  lets YOU decide the snapshot, so you can force a specific situation
  (e.g. a gas leak) on demand and check the brain reacts correctly.

Two modes:
  - random  (default): believable random values. Good for "does it run?"
  - scenario:          forces a specific situation so you can test one
                       brain behaviour at a time.
"""

import random

SCENARIOS = [
    "awake", "resting", "out_of_bed", "distressed",   # patient states
    "medical", "gas_leak", "sos",                      # emergencies
]


def _base_random():

    on_bed = random.random() < 0.8  # usually someone is in bed

    return {
        "pulse":        random.randint(62, 95),        # bpm, normal resting range
        "spo2":         random.randint(96, 100),       # %, healthy blood oxygen
        "motion":       random.choice([0, 1]),         # PIR: 0 = still, 1 = movement
        "pressure_raw": random.randint(600, 900) if on_bed else random.randint(0, 120),
        "on_bed":       on_bed,                         # derived from pressure
        "light":        random.randint(150, 850),      # LDR analog
        "temperature":  round(random.uniform(20.0, 26.0), 1),  # deg C, comfortable
        "humidity":     round(random.uniform(40.0, 60.0), 1),  # %, comfortable
        "gas":          random.randint(40, 200),       # MQ135
        "sos":          0,                              # button: 0 = not pressed
    }

_SCENARIO_OVERRIDES = {
    
    "awake":      {"on_bed": True,  "pressure_raw": 770},
    "resting":    {"on_bed": True,  "pressure_raw": 780, "motion": 0},
    "out_of_bed": {"on_bed": False, "pressure_raw": 35,  "motion": 0},
    "distressed": {"on_bed": True,  "pressure_raw": 760, "motion": 1},

    "medical":    {"pulse": 145, "spo2": 84},
    "gas_leak":   {"gas": 720},

    "sos":        {"sos": 1},
}


def read_all(scenario=None):
    
    snapshot = _base_random()

    if scenario is not None:
        if scenario not in _SCENARIO_OVERRIDES:
            raise ValueError(
                f"Unknown scenario {scenario!r}. "
                f"Choose one of: {', '.join(SCENARIOS)}"
            )
        snapshot.update(_SCENARIO_OVERRIDES[scenario])

    return snapshot


if __name__ == "__main__":
    def _show(label, snap):
        print(f"--- {label} ---")
        for key, value in snap.items():
            print(f"  {key:14} = {value}")
        print()

    print("Testing simulator.py\n")

    print("RANDOM MODE (3 snapshots, all should look normal-ish):\n")
    for i in range(3):
        _show(f"random {i + 1}", read_all())

    print("SCENARIO MODE (one snapshot per scenario):\n")
    for name in SCENARIOS:
        _show(name, read_all(name))

    print("Done.")