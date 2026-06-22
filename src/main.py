"""
main.py
"""

import threading
import queue
import time
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "sensors"))
sys.path.insert(0, os.path.join(HERE, "logic"))
sys.path.insert(0, os.path.join(HERE, "utils"))
#sys.path.insert(0, HERE)                       

USE_SIMULATOR = True     # True = laptop testing; False = real sensors on the Pi

if USE_SIMULATOR:
    from simulator import read_all
else:
    from reader import read_all

from classify import classify_all
from room_state import assess
from patient_state import PatientStateTracker
from i2c_semaphore import i2c_lock
from shared_state import publish
from web_server import run_server


# shared between threads
snapshot_queue = queue.Queue(maxsize=5)
stop_flag = threading.Event()
sos_flag = threading.Event()      # raised when the SOS button is pressed

def sos_watcher():
    """SOS WATCH THREAD: poll the SOS button very fast and raise the flag
    the instant it's pressed. Stays tiny so response is near-instant."""
    from grove_sensors import read_sos      # the real button reader

    while not stop_flag.is_set():
        with i2c_lock:
            pressed = read_sos()
        if pressed:                          
            if not sos_flag.is_set():        # only act on a fresh press
                sos_flag.set()               # raise the flag — brain will see it
                print("[SOS] *** BUTTON PRESSED ***")
        time.sleep(0.02)                     # poll every 20ms = 50x/second

def sensor_worker():
    """SENSOR THREAD: read a snapshot, put it in the queue, repeat."""
    while not stop_flag.is_set():
        with i2c_lock:
            snap = read_all()                      # acquire the bus; auto-released after the block
        try:
            snapshot_queue.put(snap, timeout=1)
        except queue.Full:
            # Queue is full: make room by discarding the oldest, then add new.
            try:
                snapshot_queue.get_nowait()        # remove oldest
            except queue.Empty:
                pass                               # (race: someone emptied it; fine)
            try:
                snapshot_queue.put_nowait(snap)    # add the fresh one
            except queue.Full:
                pass                               # (race: refilled; just skip)
        time.sleep(0.5)                       # 2 readings/second


def brain_worker():
    """BRAIN THREAD: owns the tracker, processes snapshots from the queue."""
    tracker = PatientStateTracker()           # created ONCE, owned by this thread

    while not stop_flag.is_set():
        # highest priority: check the SOS flag first
        if sos_flag.is_set():
            print("[brain] >>> SOS EMERGENCY — patient pressed the button! <<<")
            # (later: trigger buzzer, max light, alert dashboard, etc.)
            sos_flag.clear()                 # lower the flag now that we've handled it

        try:
            snap = snapshot_queue.get(timeout=1)
        except queue.Empty:
            continue

        # Run the three pieces of brain logic on this snapshot.
        buckets       = classify_all(snap)
        room          = assess(snap)
        patient_state = tracker.update(snap)

         # publish display-ready values for the web dashboard
        publish({
            "heart_rate":    snap.get("pulse"),
            "spo2":          snap.get("spo2"),
            "temperature":   snap.get("temperature"),
            "humidity":      snap.get("humidity"),
            "temp_bucket":   buckets["temperature"],
            "air_bucket":    buckets["air_quality"],
            "sunlight":      buckets["sunlight"],
            "patient_state": patient_state,
            "room_state":    room["label"],
            "sos":           room["sos"],
        })

        # For now, just print what the brain decided.
        print(f"[brain] patient={patient_state:11} room={room['label']:9} gas_hazard={room['gas_hazard']:2} temperature_hazard={room['temp_hazard']:2} "
              f"temp={buckets['temperature']:7} air={buckets['air_quality']:7} sunlight={buckets['sunlight']}")

        snapshot_queue.task_done()


if __name__ == "__main__":
    print(f"Starting MediGuard  (USE_SIMULATOR={USE_SIMULATOR})")
    print("Running... press Ctrl+C to stop.\n")

    sensor_thread = threading.Thread(target=sensor_worker, name="SensorThread")
    brain_thread  = threading.Thread(target=brain_worker,  name="BrainThread")
    sos_thread    = threading.Thread(target=sos_watcher,   name="SOSThread")
    web_thread = threading.Thread(target=run_server, name="WebThread", daemon=True)

    sensor_thread.start()
    brain_thread.start()
    sos_thread.start()   
    web_thread.start() 

    try:
        while not stop_flag.is_set():
            time.sleep(0.5)

    except KeyboardInterrupt:
        # This runs when YOU press Ctrl+C.
        print("\nCtrl+C received -- shutting down...")

    finally:
        stop_flag.set()                
        sensor_thread.join()            
        brain_thread.join()
        sos_thread.join()
        # TODO (later): turn actuators to a safe state here --
        
        print("Stopped cleanly. All threads joined. Done.")