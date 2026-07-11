"""MediGuard Raspberry Pi entry point with live MQTT/PDDL integration.

Threads started here:
  * SensorThread  -- reads a raw snapshot ~2x/second into a small queue.
  * BrainThread   -- classifies each snapshot, drives local safety outputs,
                     publishes the symbolic state to the PDDL planner, and
                     mirrors everything to the dashboard.
  * SOSThread     -- fast poll of the physical SOS button; a 2 s hold toggles
                     the emergency state.
  * ActuatorTickThread -- buzzer pulse / LED blink timing.
  * WebThread     -- Flask dashboard on localhost (see web_server.py).
"""

import os
import queue
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
for _sub in ("sensors", "logic", "utils", "actuators"):
    sys.path.insert(0, os.path.join(HERE, _sub))

# Load .env before importing modules that read config at import time
# (web_server reads the dashboard host/port).
from dotenv import load_dotenv
load_dotenv()

import netinfo

USE_SIMULATOR = False

if USE_SIMULATOR:
    from sensors.simulator import read_all
else:
    from sensors.reader import read_all

from logic.classify import build_planner_state, active_safety_profile
from sensors.grove_sensors import ADC_BITS, ADC_MAX, ADC_VREF, counts_to_volts
from logic.room_state import assess, EMERGENCY, HAZARDOUS
from logic.patient_state import PatientStateTracker, DISTRESS
from utils.i2c_semaphore import i2c_lock
import runtime_flags
import shared_state
import web_server
from web_server import run_server
import mqtt_bridge

# Vital-sign values injected when the dashboard's medical-emergency toggle is
# on. They sit outside the safe pulse/SpO2 ranges so the patient tracker
# classifies the patient as Distressed (see logic/patient_state.py).
DISTRESS_PULSE = 145
DISTRESS_SPO2 = 84

# Auto-lock the door if a MANUAL unlock is left this long (never auto-locks a
# door the AI/safety unlocked, e.g. during an emergency).
DOOR_AUTOLOCK_SECONDS = 15

snapshot_queue = queue.Queue(maxsize=5)
stop_flag = threading.Event()
bridge = mqtt_bridge.MediGuardMqttBridge()


class OutOfBedTimer:
    def __init__(self):
        self._started_at = None

    def minutes(self, on_bed: bool, now: float) -> int:
        if on_bed:
            self._started_at = None
            return 0
        if self._started_at is None:
            self._started_at = now
        return int((now - self._started_at) // 60)


class DoorAutoLock:
    """Lock the door after it has been MANUALLY unlocked for DOOR_AUTOLOCK_SECONDS.
    A door the AI/safety unlocked (e.g. during an emergency) is never auto-locked
    by this timer -- only a person's manual unlock is."""

    def __init__(self):
        self._unlocked_since = None

    def check(self, emergency_active: bool, now: float):
        door = bridge.get_actuator_state().get("door")
        manual = bridge.door_unlocked_by_manual
        if emergency_active or door != "unlocked" or not manual:
            self._unlocked_since = None
            return
        if self._unlocked_since is None:
            self._unlocked_since = now
        elif now - self._unlocked_since >= DOOR_AUTOLOCK_SECONDS:
            print(f"[auto-lock] manual unlock idle > {DOOR_AUTOLOCK_SECONDS}s; locking")
            bridge.set_door("locked")
            self._unlocked_since = None


def sos_watcher():
    """Highest-priority polling loop for the physical SOS button.

    Holding the button for HOLD_SECONDS toggles the emergency state once; the
    button must then be released before it can toggle again. A short release
    (button bounce or a single starved I2C read) is debounced so it does not
    reset the hold timer -- without this the 2 s hold rarely completed because
    the shared I2C bus is busy with the other sensors.
    """
    from sensors.grove_sensors import setup_sos, read_sos

    HOLD_SECONDS = 2.0
    RELEASE_DEBOUNCE = 0.4      # ignore releases shorter than this during a hold

    with i2c_lock:
        setup_sos()

    press_started = None
    released_at = None
    toggled_this_hold = False

    while not stop_flag.is_set():
        try:
            with i2c_lock:
                pressed = read_sos()
        except Exception as exc:
            # A flaky button/I2C read must never kill the safety-critical loop.
            print(f"[SOS] read failed, retrying: {exc}")
            time.sleep(0.2)
            continue
        now = time.monotonic()

        if pressed:
            released_at = None
            if press_started is None:
                press_started = now
                toggled_this_hold = False
            elif not toggled_this_hold and now - press_started >= HOLD_SECONDS:
                state = runtime_flags.sos_emergency.toggle()
                toggled_this_hold = True
                print(f"[SOS] *** 2s HOLD: EMERGENCY {'ON' if state else 'OFF'} ***")
        else:
            # Only treat the button as released after the debounce window, so a
            # momentary dropout mid-hold doesn't restart the 2 s timer.
            if released_at is None:
                released_at = now
            elif now - released_at >= RELEASE_DEBOUNCE:
                press_started = None
                toggled_this_hold = False

        time.sleep(0.05)


def sensor_worker():
    while not stop_flag.is_set():
        try:
            with i2c_lock:
                snap = read_all()
        except Exception as exc:
            # A failed hardware read shouldn't stop the sensor thread; skip the
            # cycle and try again on the next tick.
            print(f"[sensor] read failed, skipping cycle: {exc}")
            time.sleep(0.5)
            continue
        try:
            snapshot_queue.put(snap, timeout=1)
        except queue.Full:
            # Drop the oldest snapshot so the brain always sees fresh data.
            try:
                snapshot_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                snapshot_queue.put_nowait(snap)
            except queue.Full:
                pass
        time.sleep(0.5)


def actuator_tick_worker():
    while not stop_flag.is_set():
        try:
            bridge.tick()
        except Exception as exc:
            print(f"[actuator] tick failed: {exc}")
        time.sleep(0.05)


def apply_manual_overrides(snap: dict) -> dict:
    """Fold the dashboard/hardware emergency toggles into a raw snapshot.

    SOS is a room-level emergency; the vitals toggle stands in for the removed
    SpO2 sensor and forces distress-range vitals.
    """
    snap = dict(snap)
    snap["sos"] = bool(snap.get("sos")) or runtime_flags.sos_emergency.get()
    if runtime_flags.vitals_emergency.get():
        snap["pulse"] = DISTRESS_PULSE
        snap["spo2"] = DISTRESS_SPO2
    return snap


def build_raw_sensors(snap: dict) -> dict:
    """Structured raw sensor view for the dashboard's RAW SENSOR DATA card.

    The three analog sensors are GrovePi ADC channels, so we surface both the
    raw 10-bit count and the derived voltage. The rest are digital pins (PIR,
    SOS button) or I2C/DHT/virtual sensors that don't go through the ADC.
    """
    light = snap.get("light")
    pressure = snap.get("pressure_raw")
    gas = snap.get("gas")
    return {
        "adc_ref": {"bits": ADC_BITS, "max": ADC_MAX, "vref": ADC_VREF},
        "adc": [
            {"channel": "A0", "sensor": "Light (Grove)",  "counts": light,
             "volts": counts_to_volts(light)},
            {"channel": "A1", "sensor": "Pressure (FSR)", "counts": pressure,
             "volts": counts_to_volts(pressure)},
            {"channel": "A2", "sensor": "Gas (MQ135)",    "counts": gas,
             "volts": counts_to_volts(gas)},
        ],
        "digital": [
            {"pin": "D2", "sensor": "PIR motion", "value": bool(snap.get("motion"))},
            {"pin": "D7", "sensor": "SOS button", "value": bool(snap.get("sos"))},
        ],
        "other": [
            {"sensor": "Temperature (DHT)", "value": snap.get("temperature"), "unit": "°C"},
            {"sensor": "Humidity (DHT)",    "value": snap.get("humidity"),    "unit": "%"},
            {"sensor": "Pulse (virtual)",   "value": snap.get("pulse"),       "unit": "BPM"},
            {"sensor": "SpO₂ (virtual)", "value": snap.get("spo2"),      "unit": "%"},
        ],
    }


def describe_emergency(room: dict, patient_state: str) -> dict:
    """Single emergency descriptor for the dashboard banner/overlay."""
    if room["label"] == EMERGENCY:
        return {"active": True, "type": "sos", "label": "SOS"}
    if room["label"] == HAZARDOUS:
        return {"active": True, "type": "hazard", "label": "Hazard"}
    if patient_state == DISTRESS:
        return {"active": True, "type": "medical", "label": "Medical Emergency"}
    return {"active": False, "type": "none", "label": "None"}


def brain_worker():
    tracker = PatientStateTracker()
    out_of_bed_timer = OutOfBedTimer()
    door_auto_lock = DoorAutoLock()

    while not stop_flag.is_set():
        try:
            snap = snapshot_queue.get(timeout=1)
        except queue.Empty:
            continue

        try:
            snap = apply_manual_overrides(snap)

            # A failed DHT read should not crash classification. Keep running
            # and publish the next valid reading instead.
            if snap.get("temperature") is None or snap.get("humidity") is None:
                print("[brain] DHT reading unavailable; skipping this snapshot")
                continue

            room = assess(snap)
            patient_state = tracker.update(snap)
            out_of_bed_minutes = out_of_bed_timer.minutes(bool(snap.get("on_bed")), time.time())

            # All bucket/status/safety-profile classification lives in
            # classify.py; main.py only orchestrates and publishes the results.
            planner_state, buckets = build_planner_state(
                bridge.room_id, snap, room, patient_state, out_of_bed_minutes
            )
            safety_profile = active_safety_profile(room, patient_state)

            # Immediate safety behaviour is local. PDDL still receives the same
            # state and publishes its auditable plan, but no person waits on it.
            bridge.apply_safety_profile(safety_profile)
            bridge.publish_state(planner_state)

            # Light + fan precedence: safety > manual > auto. During a safety
            # profile the bridge ignores this (safety already drives them).
            if runtime_flags.manual_mode.get():
                bridge.set_light_fan(runtime_flags.manual_light.get(),
                                     runtime_flags.manual_fan.get())
            else:
                bridge.set_light_fan(bridge.auto_light, bridge.auto_fan)

            emergency = describe_emergency(room, patient_state)
            door_auto_lock.check(emergency["active"], time.time())

            shared_state.merge({
                # Raw, unprocessed sensor snapshot for the dashboard's
                # "RAW SENSOR DATA" card: ADC counts + volts per channel,
                # digital pins, and the non-ADC sensors.
                "raw_sensors": build_raw_sensors(snap),
                "heart_rate": snap.get("pulse"),
                "spo2": snap.get("spo2"),
                "temperature": snap.get("temperature"),
                "humidity": snap.get("humidity"),
                "temp_bucket": buckets["temperature"],
                "air_bucket": buckets["air_quality"],
                "sunlight": buckets["sunlight"],
                "patient_state": patient_state,
                "room_state": room["label"],
                "out_of_bed_minutes": out_of_bed_minutes,
                # Boolean observation facts exactly as the PDDL problem sees
                # them (see AI_pddl_planner_service.observation_predicates).
                "sensor_summary": planner_state["sensor_summary"],
                "emergency": emergency,
                "updated_at": time.time(),
            })

            print(
                f"[brain] patient={patient_state:11} room={room['label']:9} "
                f"out_of_bed={out_of_bed_minutes:2} min "
                f"safety={safety_profile or 'none'}"
            )
        except Exception as exc:
            # Never let a single malformed snapshot terminate the brain thread.
            print(f"[brain] error processing snapshot, skipping: {exc}")
            continue


if __name__ == "__main__":
    print(f"Starting MediGuard with MQTT/PDDL integration (USE_SIMULATOR={USE_SIMULATOR})")

    # The Pi joins whatever network you put it on; the dashboard binds 0.0.0.0
    # (see web_server.py) so it's reachable from any device on that network.
    # scripts/pi_setup.sh sets the hostname so mediguard.local resolves via mDNS.
    netinfo.print_access_banner(int(os.getenv("MEDIGUARD_PORT", "7801")))
    print("Running... press Ctrl+C to stop.\n")

    try:
        bridge.start()
    except Exception as exc:
        # Hardware driver / broker init failing must not stop the dashboard or
        # the local safety pipeline from coming up.
        print(f"[startup] MQTT bridge init failed (running degraded): {exc}")

    # Let the dashboard's manual-control endpoints drive this bridge directly.
    web_server.attach_bridge(bridge)

    workers = {
        "SensorThread": sensor_worker,
        "BrainThread": brain_worker,
        "SOSThread": sos_watcher,
        "ActuatorTickThread": actuator_tick_worker,
    }
    threads = [threading.Thread(target=fn, name=name) for name, fn in workers.items()]
    web_thread = threading.Thread(target=run_server, name="WebThread", daemon=True)

    for thread in threads:
        thread.start()
    web_thread.start()

    try:
        while not stop_flag.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nCtrl+C received -- shutting down...")
    finally:
        stop_flag.set()
        for thread in threads:
            thread.join(timeout=3)
        bridge.stop()
        print("Stopped cleanly.")
