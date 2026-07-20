import json
import os
import time
from datetime import datetime

from dotenv import load_dotenv
from paho.mqtt import client as mqtt


load_dotenv()

BROKER_HOST = os.getenv("BROKER_HOST", "localhost")
BROKER_PORT = int(os.getenv("BROKER_PORT", "1883"))
ROOM_ID = os.getenv("ROOM_ID", "room101")


# These are symbolic states that your real Raspberry Pi sensor node will publish later.
# The PDDL planner will replan whenever these states/goals change.
test_states = [
    {
        "room_id": ROOM_ID,
        "room_state": "normal",
        "patient_state": "awake",
        "out_of_bed_minutes": 0,
        "sensor_summary": {
            "temperature_status": "comfortable",
            "humidity_status": "comfortable",
            "air_quality_status": "safe",
            "light_level": "dark",
            "pressure_on_bed": True,
            "pir_motion_last_15_min": True,
            "spo2_status": "normal",
            "pulse_status": "normal",
            "sos_pressed": False
        }
    },
    {
        "room_id": ROOM_ID,
        "room_state": "normal",
        "patient_state": "resting",
        "out_of_bed_minutes": 0,
        "sensor_summary": {
            "temperature_status": "comfortable",
            "humidity_status": "comfortable",
            "air_quality_status": "safe",
            "light_level": "normal",
            "pressure_on_bed": True,
            "pir_motion_last_15_min": False,
            "spo2_status": "normal",
            "pulse_status": "normal",
            "sos_pressed": False
        }
    },
    {
        "room_id": ROOM_ID,
        "room_state": "normal",
        "patient_state": "out_of_bed",
        "out_of_bed_minutes": 16,
        "sensor_summary": {
            "temperature_status": "comfortable",
            "humidity_status": "comfortable",
            "air_quality_status": "safe",
            "light_level": "normal",
            "pressure_on_bed": False,
            "pir_motion_last_15_min": True,
            "spo2_status": "normal",
            "pulse_status": "normal",
            "sos_pressed": False
        }
    },
    {
        "room_id": ROOM_ID,
        "room_state": "normal",
        "patient_state": "distress",
        "out_of_bed_minutes": 0,
        "sensor_summary": {
            "temperature_status": "comfortable",
            "humidity_status": "comfortable",
            "air_quality_status": "safe",
            "light_level": "normal",
            "pressure_on_bed": True,
            "pir_motion_last_15_min": True,
            "spo2_status": "low",
            "pulse_status": "abnormal",
            "sos_pressed": False
        }
    },
    {
        "room_id": ROOM_ID,
        "room_state": "hazardous",
        "patient_state": "resting",
        "out_of_bed_minutes": 0,
        "sensor_summary": {
            "temperature_status": "unsafe",
            "humidity_status": "comfortable",
            "air_quality_status": "unsafe",
            "light_level": "normal",
            "pressure_on_bed": True,
            "pir_motion_last_15_min": False,
            "spo2_status": "normal",
            "pulse_status": "normal",
            "sos_pressed": False
        }
    },
    {
        "room_id": ROOM_ID,
        "room_state": "emergency",
        "patient_state": "awake",
        "out_of_bed_minutes": 0,
        "sensor_summary": {
            "temperature_status": "comfortable",
            "humidity_status": "comfortable",
            "air_quality_status": "safe",
            "light_level": "normal",
            "pressure_on_bed": True,
            "pir_motion_last_15_min": True,
            "spo2_status": "normal",
            "pulse_status": "normal",
            "sos_pressed": True
        }
    }
]


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(BROKER_HOST, BROKER_PORT, 60)

    topic = f"hospital/{ROOM_ID}/state"

    while True:
        for state in test_states:
            state["timestamp"] = datetime.now().isoformat(timespec="seconds")

            print("\n==============================")
            print("PUBLISHING SENSOR STATE")
            print("==============================")
            print(json.dumps(state, indent=2))

            client.publish(topic, json.dumps(state))
            print(f"Published to topic: {topic}")

            time.sleep(12)


if __name__ == "__main__":
    main()
