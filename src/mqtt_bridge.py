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

from utils.i2c_semaphore import i2c_lock
import runtime_flags
import shared_state
import actuators.light as light
import actuators.fan as fan
import actuators.lock as door_lock
import actuators.buzzer as buzzer
import actuators.red_led as red_led

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
        self._red_led_mode = "off"      # off / on / blink

        # Last light/fan level and door state actually driven to hardware, for
        # change detection so re-asserting the same value is a cheap no-op.
        self._light_percent = None
        self._fan_percent = None
        self._door_state = "locked"
        # True when the door's current unlocked state came from a manual command
        # (dashboard), as opposed to the AI planner or a safety profile.
        self._door_manual_unlock = False
        # Latest light/fan the planner asked for, re-applied when leaving manual.
        self._auto_light = 0
        self._auto_fan = 0

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

        # Publish the initial believed actuator state so the dashboard has
        # something to show before the first plan arrives.
        self._publish_actuator_state()

        # connect_async + loop_start so a missing broker never crashes startup;
        # paho keeps retrying and (re)subscribes via _on_connect once it's up.
        print(f"[mqtt] connecting to {self.broker_host}:{self.broker_port}")
        self.client.connect_async(self.broker_host, self.broker_port, keepalive=60)
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

        # Critical states (hazardous / emergency / distress): max light.
        # Lock toggle is disabled on dashboard, but we no longer force unlock.
        self._apply_light(100)
        self._set_buzzer_mode("high")
        self._set_red_led_mode("on")

    # ------------------------------------------------------------------
    # Manual / auto light + fan control (precedence: safety > manual > auto)
    # ------------------------------------------------------------------
    @property
    def auto_light(self) -> int:
        return self._auto_light

    @property
    def auto_fan(self) -> int:
        return self._auto_fan

    def set_light_fan(self, light_percent: int, fan_percent: int):
        """Drive light+fan to the given 0-100 levels (change-detected, so it is
        safe to call every cycle). Ignored while a safety profile is active."""
        if self.safety_override_active:
            return
        self._apply_light(light_percent)
        self._apply_fan(fan_percent)

    # ------------------------------------------------------------------
    # MQTT callbacks and command decoding: AI planner -> hardware
    # ------------------------------------------------------------------
    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code != 0:
            print(f"[mqtt] connection rejected: {reason_code}")
            return

        # cmd/# carries actuator commands; plan carries the AI plan we forward
        # to the dashboard so the visualisation can show the latest plan.
        client.subscribe(f"hospital/{self.room_id}/cmd/#", qos=1)
        client.subscribe(f"hospital/{self.room_id}/plan", qos=1)
        print(f"[mqtt] subscribed to hospital/{self.room_id}/cmd/# and .../plan")

    def _on_message(self, client, userdata, msg):
        # The AI plan is forwarded verbatim to the dashboard state.
        if msg.topic.endswith("/plan"):
            self._handle_plan_message(msg.payload)
            return

        command = msg.topic.rsplit("/", 1)[-1]
        value = msg.payload.decode("utf-8").strip().lower()
        print(f"[mqtt] command received: {command}={value}")

        # A critical local profile blocks stale normal planner commands.
        if self.safety_override_active:
            print("[mqtt] ignored command because a local safety profile is active")
            return

        try:
            # Light/fan follow the planner only in auto mode. In manual mode the
            # requested level is remembered (so it can be restored when auto
            # resumes) but not driven to hardware.
            if command == "light":
                self._auto_light = self._parse_percent(value, {0, 25, 50, 100}, "light")
                if not runtime_flags.manual_mode.get():
                    self._apply_light(self._auto_light)
            elif command == "fan":
                self._auto_fan = self._parse_percent(value, {0, 25, 50, 100}, "fan")
                if not runtime_flags.manual_mode.get():
                    self._apply_fan(self._auto_fan)
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
        # Accept any 0-100 level (planner uses 0/50/100; manual any value).
        percent = max(0, min(100, int(percent)))
        if percent == self._light_percent:
            return
        self._light_percent = percent

        if percent == 0:
            label, closed_state = "off", "OFF = light-not-on + light-not-dim"
        elif percent <= 50:
            label, closed_state = "dim", "DIM = light-on + light-dim"
        else:
            label, closed_state = "bright", "BRIGHT = light-on + light-not-dim"

        light.set_brightness(percent)
        with self._command_lock:
            self._actuator_state["light"] = label
        print(f"[ACTUATOR STATE] light={percent}% -> {closed_state}")
        self._publish_actuator_state()

    def _apply_fan(self, percent: int):
        percent = max(0, min(100, int(percent)))
        if percent == self._fan_percent:
            return
        self._fan_percent = percent

        if percent == 0:
            label, closed_state = "off", "OFF = fan-not-on + fan-not-medium + fan-not-high"
        elif percent <= 33:
            label, closed_state = "low", "LOW = fan-on + fan-not-medium + fan-not-high"
        elif percent <= 66:
            label, closed_state = "medium", "MEDIUM = fan-on + fan-medium + fan-not-high"
        else:
            label, closed_state = "high", "HIGH = fan-on + fan-not-medium + fan-high"

        fan.set_speed(percent)
        with self._command_lock:
            self._actuator_state["fan"] = label
        print(f"[ACTUATOR STATE] fan={percent}% -> {closed_state}")
        self._publish_actuator_state()

    def _apply_door(self, value: str, manual: bool = False):
        # 0 = locked; 1 = unlocked. Relay polarity is hidden in lock.py.
        if value in {"0", "lock", "locked"}:
            target = "locked"
        elif value in {"1", "unlock", "unlocked"}:
            target = "unlocked"
        else:
            raise ValueError("door must be 0/locked or 1/unlocked")

        # Record who owns the current unlock (manual person vs AI/safety), so
        # the auto-lock timer only applies to a door a person opened. Updated
        # even on a no-op so the latest command's source always wins.
        self._door_manual_unlock = manual and target == "unlocked"

        if target == self._door_state:
            return
        self._door_state = target

        with i2c_lock:
            door_lock.lock() if target == "locked" else door_lock.unlock()
        with self._command_lock:
            self._actuator_state["door"] = target
        print(f"[ACTUATOR STATE] door -> {target.upper()} = door-{target}"
              f"{' (manual)' if manual else ''}")
        self._publish_actuator_state()

    @property
    def door_unlocked_by_manual(self) -> bool:
        return self._door_manual_unlock

    def set_door(self, value: str):
        """Public MANUAL door control (dashboard lock/unlock, auto-lock). Blocked
        while a safety profile holds the door unlocked for emergency access."""
        if self.safety_override_active:
            return
        self._apply_door(value, manual=True)

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
        self._publish_actuator_state()

    def _set_red_led_mode(self, value: str):
        aliases = {
            "0": "off", "off": "off",
            "on": "on", "solid": "on",
            "1": "blink", "blink": "blink",
        }
        if value not in aliases:
            raise ValueError("red_led must be off, on, or blink")

        mode = aliases[value]
        state_text = {
            "off": "OFF = red-led-not-on + red-led-not-blinking",
            "on": "ON = red-led-on + red-led-not-blinking",
            "blink": "BLINK = red-led-on + red-led-blinking",
        }[mode]

        with self._command_lock:
            self._red_led_mode = mode
            self._actuator_state["red_led"] = mode
        print(f"[ACTUATOR STATE] red_led={mode} -> {state_text}")
        self._publish_actuator_state()

    def get_actuator_state(self) -> dict:
        """Return the last command interpretation held by this bridge."""
        with self._command_lock:
            return dict(self._actuator_state)

    def _publish_actuator_state(self):
        """Mirror the believed closed actuator state to the dashboard."""
        shared_state.merge({"actuator_state": self.get_actuator_state()})

    def _handle_plan_message(self, payload: bytes):
        """Forward the AI planner's latest plan to the dashboard state."""
        try:
            plan = json.loads(payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            print(f"[mqtt] ignored malformed plan message: {exc}")
            return
        shared_state.merge({"plan": plan})
        print(f"[mqtt] plan forwarded to dashboard: {plan.get('goal', '?')}")

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
            red_led.apply(red_led_mode, now)     # off / on (solid) / blink
