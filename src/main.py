"""MediGuard Raspberry Pi entry point with live MQTT/PDDL integration."""

import os
import queue
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "sensors"))
sys.path.insert(0, os.path.join(HERE, "logic"))
sys.path.insert(0, os.path.join(HERE, "utils"))
sys.path.insert(0, os.path.join(HERE, "actuators"))

USE_SIMULATOR = True

if USE_SIMULATOR:
    from sensors.simulator import read_all
else:
    from sensors.reader import read_all

from logic.classify import build_planner_state, active_safety_profile
from logic.room_state import assess
from logic.patient_state import PatientStateTracker
from utils.i2c_semaphore import i2c_lock
from shared_state import publish
from web_server import run_server
import mqtt_bridge

snapshot_queue = queue.Queue(maxsize=5)
stop_flag = threading.Event()
sos_latched = threading.Event()
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


def sos_watcher():
    """Highest-priority polling loop. A press latches until a staff reset command."""
    from sensors.grove_sensors import read_sos

    while not stop_flag.is_set():
        with i2c_lock:
            pressed = read_sos()
        if pressed and not sos_latched.is_set():
            sos_latched.set()
            print("[SOS] *** BUTTON PRESSED: EMERGENCY LATCHED ***")
        time.sleep(0.02)


def sensor_worker():
    while not stop_flag.is_set():
        with i2c_lock:
            snap = read_all()
        try:
            snapshot_queue.put(snap, timeout=1)
        except queue.Full:
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
        bridge.tick()
        time.sleep(0.05)


def brain_worker():
    tracker = PatientStateTracker()
    out_of_bed_timer = OutOfBedTimer()

    while not stop_flag.is_set():
        if bridge.consume_sos_reset_request():
            sos_latched.clear()
            print("[SOS] latch reset by staff command")

        try:
            snap = snapshot_queue.get(timeout=1)
        except queue.Empty:
            continue

        # The physical SOS press may be brief. Preserve it in this snapshot
        # after the fast watcher detects it, so both the dashboard and PDDL
        # service receive the emergency state.
        snap = dict(snap)
        snap["sos"] = bool(snap.get("sos")) or sos_latched.is_set()

        # A failed DHT read should not crash classification. Keep running and
        # publish the next valid reading instead.
        if snap.get("temperature") is None or snap.get("humidity") is None:
            print("[brain] DHT reading unavailable; skipping this snapshot")
            snapshot_queue.task_done()
            continue

        room = assess(snap)
        patient_state = tracker.update(snap)
        out_of_bed_minutes = out_of_bed_timer.minutes(bool(snap.get("on_bed")), time.time())

        # All bucket/status/safety-profile classification lives in classify.py;
        # main.py only orchestrates the pipeline and publishes the results.
        planner_state, buckets = build_planner_state(
            bridge.room_id, snap, room, patient_state, out_of_bed_minutes
        )
        safety_profile = active_safety_profile(room, patient_state)

        # Immediate safety behavior is local. PDDL still receives the same
        # state and publishes its auditable plan, but no person waits on it.
        bridge.apply_safety_profile(safety_profile)
        bridge.publish_state(planner_state)

        publish({
            "heart_rate": snap.get("pulse"),
            "spo2": snap.get("spo2"),
            "temperature": snap.get("temperature"),
            "humidity": snap.get("humidity"),
            "temp_bucket": buckets["temperature"],
            "air_bucket": buckets["air_quality"],
            "sunlight": buckets["sunlight"],
            "patient_state": patient_state,
            "room_state": room["label"],
            "sos": room["sos"],
            "out_of_bed_minutes": out_of_bed_minutes,
            "planner_state": planner_state,
        })

        print(
            f"[brain] patient={patient_state:11} room={room['label']:9} "
            f"out_of_bed={out_of_bed_minutes:2} min "
            f"safety={safety_profile or 'none'}"
        )
        snapshot_queue.task_done()


if __name__ == "__main__":
    print(f"Starting MediGuard with MQTT/PDDL integration (USE_SIMULATOR={USE_SIMULATOR})")
    print("Running... press Ctrl+C to stop.\n")

    bridge.start()

    sensor_thread = threading.Thread(target=sensor_worker, name="SensorThread")
    brain_thread = threading.Thread(target=brain_worker, name="BrainThread")
    sos_thread = threading.Thread(target=sos_watcher, name="SOSThread")
    actuator_thread = threading.Thread(target=actuator_tick_worker, name="ActuatorTickThread")
    web_thread = threading.Thread(target=run_server, name="WebThread", daemon=True)

    sensor_thread.start()
    brain_thread.start()
    sos_thread.start()
    actuator_thread.start()
    web_thread.start()

    try:
        while not stop_flag.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nCtrl+C received -- shutting down...")
    finally:
        stop_flag.set()
        for thread in (sensor_thread, brain_thread, sos_thread, actuator_thread):
            thread.join(timeout=3)
        bridge.stop()
        print("Stopped cleanly.")