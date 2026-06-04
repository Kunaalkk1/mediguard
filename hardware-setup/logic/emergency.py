"""
Works out the EMERGENCY status from a single sensor snapshot:

    None  /  SOS  /  Hazard  /  Medical

"""

# Dashboard labels.
NONE    = "None"
SOS     = "SOS"
HAZARD  = "Hazard"
MEDICAL = "Medical"

EMERGENCIES = [NONE, SOS, HAZARD, MEDICAL]


def assess(
    snapshot,
    pulse_low=50,       # bpm: below this is too slow
    pulse_high=120,     # bpm: above this is too fast
    spo2_min=90,        # %: below this is too little blood oxygen
    gas_threshold=400,  # analog 0..1023: at/above this the gas is hazardous
):
    
    pulse = snapshot["pulse"]
    spo2  = snapshot["spo2"]
    gas   = snapshot["gas"]
    sos   = snapshot["sos"]

    medical = (pulse < pulse_low) or (pulse > pulse_high) or (spo2 < spo2_min)
    hazard  = gas >= gas_threshold
    sos_pressed = (sos == 1)

    if medical:
        label = MEDICAL
    elif hazard:
        label = HAZARD
    elif sos_pressed:
        label = SOS
    else:
        label = NONE

    return {
        "label":   label,
        "medical": medical,
        "hazard":  hazard,
        "sos":     sos_pressed,
        "active":  label != NONE,
    }


if __name__ == "__main__":

    def snap(pulse=80, spo2=98, gas=100, sos=0):
        """Minimal snapshot with only the fields emergency.py reads.
        Defaults are all-normal; override one field to create a situation."""
        return {"pulse": pulse, "spo2": spo2, "gas": gas, "sos": sos}

    cases = [
        ("all normal",            snap(),                       "None"),
        ("SOS button pressed",    snap(sos=1),                  "SOS"),
        ("hazardous gas",         snap(gas=720),                "Hazard"),
        ("pulse too high",        snap(pulse=145),              "Medical"),
        ("SpO2 too low",          snap(spo2=84),                "Medical"),
        ("pulse too low",         snap(pulse=38),               "Medical"),
        ("gas + bad vitals",      snap(pulse=145, gas=720),     "Medical"),
        ("gas + SOS together",    snap(gas=720, sos=1),         "Hazard"),
    ]

    print("Testing emergency.py\n")
    for name, s, expected in cases:
        r = assess(s)
        flags = f"medical={r['medical']} hazard={r['hazard']} sos={r['sos']}"
        ok = "OK" if r["label"] == expected else "!! MISMATCH"
        print(f"  {name:22} -> label={r['label']:8} [{flags}]  (expect {expected})  {ok}")

    print("\nNote the last two rows: the dashboard label shows only the top")
    print("priority, but the individual flags still reveal the gas hazard")
    print("underneath -- that's what the planner reads.")
    print("\nDone.")