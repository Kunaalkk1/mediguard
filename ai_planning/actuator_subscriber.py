import os
from dotenv import load_dotenv
from paho.mqtt import client as mqtt

load_dotenv()

BROKER_HOST = os.getenv("BROKER_HOST", "localhost")
ROOM_ID = os.getenv("ROOM_ID", "room101")


def on_message(client, userdata, msg):
    topic = msg.topic
    value = msg.payload.decode("utf-8")

    print("\n==============================")
    print("ACTUATOR COMMAND RECEIVED")
    print("==============================")
    print(f"Topic: {topic}")
    print(f"Value: {value}")

    if topic.endswith("/cmd/light"):
        print(f"Room light brightness is now {value}%")

    elif topic.endswith("/cmd/fan"):
        print(f"Fan speed is now {value}%")

    elif topic.endswith("/cmd/door"):
        print(f"Door state is now {value}")

    elif topic.endswith("/cmd/buzzer"):
        print(f"Buzzer state is now {value}")


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_message = on_message

    client.connect(BROKER_HOST, 1883, 60)

    topic = f"hospital/{ROOM_ID}/cmd/#"
    client.subscribe(topic)

    print(f"Actuator is listening on topic: {topic}")
    client.loop_forever()


if __name__ == "__main__":
    main()
