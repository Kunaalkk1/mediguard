"""MQTT bridge used inside the MediGuard hardware process.

This module:
1. Publishes the symbolic room/patient state to the PDDL planner.
2. Receives MQTT actuator commands from the planner.
3. Maps those commands to the existing light, fan, door, buzzer, and red-LED drivers.
4. Prints the interpreted closed actuator state in the hardware terminal.

Do not run this file as a separate program. It is imported and started by src/main.py.
"""

import json
import os
import threading
import time
from datetime import datetime

from dotenv import load_dotenv
from paho.mqtt import client as mqtt

from i2c_semaphore import i2c_lock
import light
import fan
import lock as door_lock
import buzzer
import red_led

load_dotenv()


class MediGuardMqttBridge:
    """Translate MQTT planner commands to the existing hardware drivers."""

    def __init__(self):
        self.broker_host = os.getenv("BROKER_HOST", "localhost")
        self.broker_port = int(os.getenv("BROKER_PORT", "1883"))
        self.room_id = os.getenv("ROOM_ID", "room101")

        self._command_lock = threading.Lock()
        self._safety_profile = None
        self._buzzer_mode = "off"       # off / low / high
        self._buzzer_is_on = False
        self._red_led_mode = "off"      # off / blink
        self._reset_sos_requested = threading.Event()

        # Bridge belief after it has received and applied a command.
        # This confirms command reception and interpretation. It is not sensor
        # feedback from the physical actuator.
        self._actuator_state = {
            "light": "off",
            "fan": "off",
            "door": "locked",
            "buzzer": "off",
            "red_led": "off",
        }

        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"mediguard-hardware-{self.room_id}",
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self):
        """Initialise drivers and connect to the MQTT broker."""
        light.setup()
        fan.setup()
        with i2c_lock:
            door_lock.setup()
            buzzer.setup()
            red_led.setup()

        print(f"[mqtt] connecting to {self.broker_host}:{self.broker_port}")
        self.client.connect(self.broker_host, self.broker_port, keepalive=60)
        self.client.loop_start()

    def stop(self):
        """Put indicators in a quiet state and close MQTT cleanly."""
        self._set_buzzer_mode("off")
        self._set_red_led_mode("off")
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # MQTT state publication: hardware -> AI planner
    # ------------------------------------------------------------------
    def publish_state(self, state: dict):
        topic = f"hospital/{self.room_id}/state"
        payload = json.dumps(state)
        result = self.client.publish(topic, payload, qos=1, retain=False)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            print(f"[mqtt] state publication failed with rc={result.rc}")

    # ------------------------------------------------------------------
    # Local safety override
    # ------------------------------------------------------------------
    @property
    def safety_override_active(self) -> bool:
        return self._safety_profile is not None

    def apply_safety_profile(self, profile: str | None):
        """Apply local safety outputs without waiting for online planning."""
        if profile == self._safety_profile:
            return

        self._safety_profile = profile
        print(f"[safety] local profile -> {profile or 'none'}")

        if profile is None:
            self._set_buzzer_mode("off")
            self._set_red_led_mode("off")
            return

        fan_value = 100 if profile == "hazardous" else 50

        self._apply_light(100)
        self._apply_fan(fan_value)
        self._apply_door("1")
        self._set_buzzer_mode("high")
        self._set_red_led_mode("blink")

    def consume_sos_reset_request(self) -> bool:
        """Return True once when staff sends hospital/<room>/cmd/reset_sos = 1."""
        if self._reset_sos_requested.is_set():
            self._reset_sos_requested.clear()
            return True
        return False

    # ------------------------------------------------------------------
    # MQTT callbacks and command decoding: AI planner -> hardware
    # ------------------------------------------------------------------
    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code != 0:
            print(f"[mqtt] connection rejected: {reason_code}")
            return

        topic = f"hospital/{self.room_id}/cmd/#"
        client.subscribe(topic, qos=1)
        print(f"[mqtt] subscribed to {topic}")

    def _on_message(self, client, userdata, msg):
        command = msg.topic.rsplit("/", 1)[-1]
        value = msg.payload.decode("utf-8").strip().lower()
        print(f"[mqtt] command received: {command}={value}")

        if command == "reset_sos":
            if value in {"1", "true", "reset"}:
                self._reset_sos_requested.set()
                print("[ACTUATOR STATE] SOS reset request received")
            return

        # A critical local profile blocks stale normal planner commands.
        if self.safety_override_active:
            print("[mqtt] ignored command because a local safety profile is active")
            return

        try:
            if command == "light":
                self._apply_light(self._parse_percent(value, {0, 25, 50, 100}, "light"))
            elif command == "fan":
                self._apply_fan(self._parse_percent(value, {0, 25, 50, 100}, "fan"))
            elif command == "door":
                self._apply_door(value)
            elif command == "buzzer":
                self._set_buzzer_mode(value)
            elif command == "red_led":
                self._set_red_led_mode(value)
            else:
                print(f"[mqtt] unsupported actuator command: {command}")
        except ValueError as exc:
            print(f"[mqtt] rejected invalid command: {exc}")

    @staticmethod
    def _parse_percent(value: str, allowed: set[int], name: str) -> int:
        try:
            parsed = int(value)
        except ValueError as exc:
            raise ValueError(f"{name} must be one of {sorted(allowed)}, got {value!r}") from exc

        if parsed not in allowed:
            raise ValueError(f"{name} must be one of {sorted(allowed)}, got {parsed}")
        return parsed

    # ------------------------------------------------------------------
    # Existing driver calls + closed-state logging
    # ------------------------------------------------------------------
    def _apply_light(self, percent: int):
        if percent == 0:
            closed_state = "OFF = light-not-on + light-not-dim"
            label = "off"
        elif percent in {25, 50}:
            closed_state = "DIM = light-on + light-dim"
            label = "dim"
        else:
            closed_state = "BRIGHT = light-on + light-not-dim"
            label = "bright"

        light.set_brightness(percent)
        with self._command_lock:
            self._actuator_state["light"] = label
        print(f"[ACTUATOR STATE] light={percent}% -> {closed_state}")

    def _apply_fan(self, percent: int):
        fan_states = {
            0: ("off", "OFF = fan-not-on + fan-not-medium + fan-not-high"),
            25: ("low", "LOW = fan-on + fan-not-medium + fan-not-high"),
            50: ("medium", "MEDIUM = fan-on + fan-medium + fan-not-high"),
            100: ("high", "HIGH = fan-on + fan-not-medium + fan-high"),
        }
        label, closed_state = fan_states[percent]

        fan.set_speed(percent)
        with self._command_lock:
            self._actuator_state["fan"] = label
        print(f"[ACTUATOR STATE] fan={percent}% -> {closed_state}")

    def _apply_door(self, value: str):
        # 0 = locked; 1 = unlocked. Relay polarity is hidden in lock.py.
        if value in {"0", "lock", "locked"}:
            with i2c_lock:
                door_lock.lock()
            with self._command_lock:
                self._actuator_state["door"] = "locked"
            print("[ACTUATOR STATE] door=0 -> LOCKED = door-locked")
        elif value in {"1", "unlock", "unlocked"}:
            with i2c_lock:
                door_lock.unlock()
            with self._command_lock:
                self._actuator_state["door"] = "unlocked"
            print("[ACTUATOR STATE] door=1 -> UNLOCKED = door-unlocked")
        else:
            raise ValueError("door must be 0/locked or 1/unlocked")

    def _set_buzzer_mode(self, value: str):
        aliases = {
            "0": "off", "off": "off",
            "low": "low", "l": "low",
            "high": "high", "h": "high", "1": "high",
        }
        if value not in aliases:
            raise ValueError("buzzer must be 0/off, low, or high")

        mode = aliases[value]
        state_text = {
            "off": "OFF = buzzer-not-on + buzzer-not-high",
            "low": "LOW ALERT = buzzer-on + buzzer-not-high",
            "high": "HIGH ALERT = buzzer-on + buzzer-high",
        }[mode]

        with self._command_lock:
            self._buzzer_mode = mode
            self._actuator_state["buzzer"] = mode
        print(f"[ACTUATOR STATE] buzzer={mode} -> {state_text}")

    def _set_red_led_mode(self, value: str):
        aliases = {
            "0": "off", "off": "off",
            "1": "blink", "blink": "blink", "on": "blink",
        }
        if value not in aliases:
            raise ValueError("red_led must be 0/off or 1/blink")

        mode = aliases[value]
        state_text = {
            "off": "OFF = red-led-not-on + red-led-not-blinking",
            "blink": "BLINK = red-led-on + red-led-blinking",
        }[mode]

        with self._command_lock:
            self._red_led_mode = mode
            self._actuator_state["red_led"] = mode
        print(f"[ACTUATOR STATE] red_led={mode} -> {state_text}")

    def get_actuator_state(self) -> dict:
        """Return the last command interpretation held by this bridge."""
        with self._command_lock:
            return dict(self._actuator_state)

    def tick(self):
        """Run every ~50 ms from main.py for buzzer pulse / LED blink output."""
        now = time.monotonic()
        with self._command_lock:
            buzzer_mode = self._buzzer_mode
            red_led_mode = self._red_led_mode

        # Active buzzer has no physical volume control:
        # low = intermittent sound; high = continuous sound.
        if buzzer_mode == "high":
            should_sound = True
        elif buzzer_mode == "low":
            should_sound = int(now / 0.8) % 2 == 0
        else:
            should_sound = False

        if should_sound != self._buzzer_is_on:
            with i2c_lock:
                buzzer.on() if should_sound else buzzer.off()
            self._buzzer_is_on = should_sound

        with i2c_lock:
            red_led.set_from_sos(red_led_mode == "blink", now)
