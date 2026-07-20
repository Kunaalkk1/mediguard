import json
import os
from dotenv import load_dotenv
from paho.mqtt import client as mqtt


load_dotenv()

BROKER_HOST = os.getenv("BROKER_HOST", "localhost")
ROOM_ID = os.getenv("ROOM_ID", "room101")


def create_plan(state):
    room_state = state.get("room_state")
    patient_state = state.get("patient_state")
    out_of_bed_minutes = state.get("out_of_bed_minutes", 0)

    sensor_summary = state.get("sensor_summary", {})
    temperature_status = sensor_summary.get("temperature_status", "comfortable")
    humidity_status = sensor_summary.get("humidity_status", "comfortable")
    light_level = sensor_summary.get("light_level", "normal")

    manual_mode = state.get("manual_mode", {})
    manual_values = state.get("manual_values", {})

    # 1. Highest priority: hazardous room
    if room_state == "hazardous":
        return {
            "priority": "critical",
            "goal": "Handle hazardous room condition",
            "light_brightness": 100,
            "fan_speed": 100,
            "door_state": "unlock",
            "buzzer_state": "high",
            "reason": "Hazardous room detected. Safety overrides comfort and manual control."
        }

    # 2. Emergency / SOS
    if room_state == "emergency":
        return {
            "priority": "critical",
            "goal": "Handle emergency condition",
            "light_brightness": 100,
            "fan_speed": 70,
            "door_state": "unlock",
            "buzzer_state": "high",
            "reason": "Emergency detected. Door is unlocked and alarm is activated."
        }

    # 3. Patient distress
    if patient_state == "distress":
        return {
            "priority": "critical",
            "goal": "Handle patient distress",
            "light_brightness": 100,
            "fan_speed": 70,
            "door_state": "unlock",
            "buzzer_state": "high",
            "reason": "Patient distress detected. Staff must be alerted immediately."
        }

    # 4. Patient out of bed for more than 15 minutes
    if patient_state == "out_of_bed" and out_of_bed_minutes >= 15:
        return {
            "priority": "warning",
            "goal": "Alert staff because patient is out of bed",
            "light_brightness": 70,
            "fan_speed": 40,
            "door_state": "lock",
            "buzzer_state": "low",
            "reason": "Patient has been out of bed for more than 15 minutes."
        }

    # 5. Patient resting
    if patient_state == "resting":
        fan_speed = 30

        if temperature_status == "hot" or humidity_status == "high":
            fan_speed = 60

        return {
            "priority": "normal",
            "goal": "Support patient rest and save power",
            "light_brightness": 0,
            "fan_speed": fan_speed,
            "door_state": "lock",
            "buzzer_state": "off",
            "reason": "Patient is resting. Light is off, buzzer is off, and fan is kept comfortable."
        }

    # 6. Patient awake
    if patient_state == "awake":
        light_brightness = 60
        fan_speed = 40

        if light_level == "dark":
            light_brightness = 80

        if temperature_status == "hot" or humidity_status == "high":
            fan_speed = 70

        # Manual control is allowed only in normal non-emergency states
        if manual_mode.get("light") is True:
            light_brightness = manual_values.get("light_brightness", light_brightness)

        if manual_mode.get("fan") is True:
            fan_speed = manual_values.get("fan_speed", fan_speed)

        return {
            "priority": "normal",
            "goal": "Maintain patient comfort",
            "light_brightness": light_brightness,
            "fan_speed": fan_speed,
            "door_state": "lock",
            "buzzer_state": "off",
            "reason": "Patient is awake. Comfort settings are applied."
        }

    # 7. Safe default
    return {
        "priority": "normal",
        "goal": "Maintain safe default room state",
        "light_brightness": 50,
        "fan_speed": 40,
        "door_state": "lock",
        "buzzer_state": "off",
        "reason": "No special condition detected."
    }


def validate_plan(state, plan):
    room_state = state.get("room_state")
    patient_state = state.get("patient_state")

    emergency = (
        room_state in ["hazardous", "emergency"]
        or patient_state == "distress"
    )

    if emergency:
        plan["priority"] = "critical"
        plan["light_brightness"] = 100
        plan["door_state"] = "unlock"
        plan["buzzer_state"] = "high"

    plan["light_brightness"] = max(0, min(100, int(plan["light_brightness"])))
    plan["fan_speed"] = max(0, min(100, int(plan["fan_speed"])))

    if plan["door_state"] not in ["lock", "unlock"]:
        plan["door_state"] = "lock"

    if plan["buzzer_state"] not in ["off", "low", "high"]:
        plan["buzzer_state"] = "off"

    return plan


def publish_plan(client, room_id, plan):
    base_topic = f"hospital/{room_id}"

    client.publish(f"{base_topic}/cmd/light", str(plan["light_brightness"]))
    client.publish(f"{base_topic}/cmd/fan", str(plan["fan_speed"]))
    client.publish(f"{base_topic}/cmd/door", plan["door_state"])
    client.publish(f"{base_topic}/cmd/buzzer", plan["buzzer_state"])
    client.publish(f"{base_topic}/plan", json.dumps(plan))

    print("\n==============================")
    print("FINAL RULE-BASED PLAN")
    print("==============================")
    print(json.dumps(plan, indent=2))


def on_message(client, userdata, msg):
    try:
        state = json.loads(msg.payload.decode("utf-8"))

        print("\n==============================")
        print("STATE RECEIVED BY RULE-BASED PLANNER")
        print("==============================")
        print(json.dumps(state, indent=2))

        plan = create_plan(state)
        safe_plan = validate_plan(state, plan)

        room_id = state.get("room_id", ROOM_ID)
        publish_plan(client, room_id, safe_plan)

    except Exception as e:
        print("Error in planner:")
        print(e)


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_message = on_message

    print(f"Connecting to MQTT broker at {BROKER_HOST}...")
    client.connect(BROKER_HOST, 1883, 60)

    topic = "hospital/+/state"
    client.subscribe(topic)

    print(f"Rule-based AI planner is listening on topic: {topic}")
    client.loop_forever()


if __name__ == "__main__":
    main()