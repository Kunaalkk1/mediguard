import json
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
import requests
from dotenv import load_dotenv
from paho.mqtt import client as mqtt


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

BROKER_HOST = os.getenv("BROKER_HOST", "localhost")
BROKER_PORT = int(os.getenv("BROKER_PORT", "1883"))
ROOM_ID = os.getenv("ROOM_ID", "room101")

# "online" uses Planning.Domains. "local" uses Fast Downward if you install it later.
PLANNER_MODE = os.getenv("PLANNER_MODE", "online").lower()

# Planning.Domains endpoint. If this service changes, test your PDDL in the browser first.
PLANNING_SERVICE_URL = os.getenv(
    "PLANNING_SERVICE_URL",
    "https://solver.planning.domains/solve"
)

# Local Fast Downward command example:
# FAST_DOWNWARD_CMD=python C:\path\to\downward\fast-downward.py
FAST_DOWNWARD_CMD = os.getenv("FAST_DOWNWARD_CMD", "")

PROJECT_DIR = Path(__file__).resolve().parent
DOMAIN_FILE = PROJECT_DIR / "domain.pddl"
PROBLEM_FILE = PROJECT_DIR / "problem_latest.pddl"
PLAN_FILE = PROJECT_DIR / "plan_latest.txt"


# ============================================================
# CURRENT ACTUATOR STATE
# This is the planner service's belief about the current actuator state.
# After executing PDDL actions, we update this state.
# ============================================================

current_actuator_state = {
    # Semantic closed states used by the PDDL model.
    "light": "dim",          # off / dim / bright
    "fan": "medium",         # off / low / medium / high
    "door": "locked",        # locked / unlocked
    "buzzer": "off",         # off / low / high
    "red_led": "off",        # off / blink
}

previous_goal_signature = None


# ============================================================
# PDDL PROBLEM GENERATION
# ============================================================


def mode_predicates(modes: dict[str, str]) -> list[str]:
    """Return the closed PDDL facts for one complete actuator configuration.

    Each actuator is represented by valid combinations of Boolean facts.
    For example:
      light off    = light-not-on + light-not-dim
      light dim    = light-on + light-dim
      light bright = light-on + light-not-dim
    """

    light = {
        "off": ["(light-not-on light1)", "(light-not-dim light1)"],
        "dim": ["(light-on light1)", "(light-dim light1)"],
        "bright": ["(light-on light1)", "(light-not-dim light1)"],
    }[modes["light"]]

    fan = {
        "off": ["(fan-not-on fan1)", "(fan-not-medium fan1)", "(fan-not-high fan1)"],
        # "on" with neither medium nor high means low speed.
        "low": ["(fan-on fan1)", "(fan-not-medium fan1)", "(fan-not-high fan1)"],
        "medium": ["(fan-on fan1)", "(fan-medium fan1)", "(fan-not-high fan1)"],
        "high": ["(fan-on fan1)", "(fan-not-medium fan1)", "(fan-high fan1)"],
    }[modes["fan"]]

    door = {
        "locked": ["(door-locked door1)"],
        "unlocked": ["(door-unlocked door1)"],
    }[modes["door"]]

    buzzer = {
        "off": ["(buzzer-not-on buzzer1)", "(buzzer-not-high buzzer1)"],
        "low": ["(buzzer-on buzzer1)", "(buzzer-not-high buzzer1)"],
        "high": ["(buzzer-on buzzer1)", "(buzzer-high buzzer1)"],
    }[modes["buzzer"]]

    red_led = {
        "off": ["(red-led-not-on redled1)", "(red-led-not-blinking redled1)"],
        "blink": ["(red-led-on redled1)", "(red-led-blinking redled1)"],
    }[modes["red_led"]]

    return light + fan + door + buzzer + red_led


def actuator_init_predicates() -> str:
    """Convert the confirmed/believed actuator configuration into PDDL facts."""
    static_facts = [
        "(light-in light1 room101)",
        "(fan-in fan1 room101)",
        "(door-in door1 room101)",
        "(buzzer-in buzzer1 room101)",
        "(red-led-in redled1 room101)",
        "(patient-in patient1 room101)",
    ]
    return "\n    ".join(static_facts + mode_predicates(current_actuator_state))


def observation_predicates(state: dict) -> str:
    """Build complete observed room/patient facts for this planning cycle.

    These facts describe the sensed state.  The current policy still selects
    the target actuator configuration in goal_from_state(); keeping the facts
    in :init makes the PDDL problem explicit and auditable.
    """

    summary = state.get("sensor_summary", {})
    room_state = state.get("room_state", "normal")
    patient_state = state.get("patient_state", "awake")
    out_of_bed_due = int(state.get("out_of_bed_minutes", 0)) >= 15

    def pair(positive: str, negative: str, value: bool, obj: str) -> list[str]:
        return [f"({positive} {obj})"] if value else [f"({negative} {obj})"]

    facts: list[str] = []

    # Multi-valued high-level states: exactly one fact from each group.
    facts.append(f"(room-{room_state} room101)")
    facts.append(f"(patient-{patient_state.replace('_', '-')} patient1)")

    # True binary observations are represented as a positive/negative pair.
    facts += pair("sos-pressed", "sos-not-pressed", bool(summary.get("sos_pressed")), "room101")
    facts += pair(
        "air-hazardous",
        "air-not-hazardous",
        summary.get("air_quality_status") == "unsafe",
        "room101",
    )
    facts += pair(
        "temperature-unsafe",
        "temperature-not-unsafe",
        summary.get("temperature_status") == "unsafe",
        "room101",
    )
    facts += pair(
        "temperature-hot",
        "temperature-not-hot",
        summary.get("temperature_status") == "hot",
        "room101",
    )
    facts += pair(
        "humidity-high",
        "humidity-not-high",
        summary.get("humidity_status") == "high",
        "room101",
    )
    facts += pair(
        "room-dark",
        "room-not-dark",
        summary.get("light_level") == "dark",
        "room101",
    )
    facts += pair(
        "patient-on-bed",
        "patient-not-on-bed",
        bool(summary.get("pressure_on_bed")),
        "patient1",
    )
    facts += pair(
        "motion-recent",
        "motion-not-recent",
        bool(summary.get("pir_motion_last_15_min")),
        "patient1",
    )
    facts += pair(
        "spo2-low",
        "spo2-not-low",
        summary.get("spo2_status") == "low",
        "patient1",
    )
    facts += pair(
        "pulse-abnormal",
        "pulse-not-abnormal",
        summary.get("pulse_status") == "abnormal",
        "patient1",
    )
    facts += pair(
        "out-of-bed-alert-due",
        "out-of-bed-alert-not-due",
        out_of_bed_due,
        "patient1",
    )

    return "\n    ".join(facts)


def goal_from_state(state: dict) -> tuple[str, str, str]:
    """Select one target actuator configuration from the observed state.

    Priority is deliberately preserved:
      emergency/SOS > hazardous room > patient distress > other conditions.
    The returned PDDL goal contains complete closed actuator facts.
    """

    room_state = state.get("room_state", "normal")
    patient_state = state.get("patient_state", "awake")
    out_of_bed_minutes = int(state.get("out_of_bed_minutes", 0))
    summary = state.get("sensor_summary", {})

    if room_state == "hazardous":
        goal_name, priority, modes = (
            "Handle hazardous room condition",
            "critical",
            {"light": "bright", "fan": "high", "door": "unlocked", "buzzer": "high", "red_led": "blink"},
        )
    elif room_state == "emergency":
        goal_name, priority, modes = (
            "Handle emergency / SOS condition",
            "critical",
            {"light": "bright", "fan": "medium", "door": "unlocked", "buzzer": "high", "red_led": "blink"},
        )
    elif patient_state == "distress":
        goal_name, priority, modes = (
            "Handle patient distress",
            "critical",
            {"light": "bright", "fan": "medium", "door": "unlocked", "buzzer": "high", "red_led": "blink"},
        )
    elif patient_state == "out_of_bed" and out_of_bed_minutes >= 15:
        goal_name, priority, modes = (
            "Alert staff because patient is out of bed",
            "warning",
            {"light": "dim", "fan": "medium", "door": "locked", "buzzer": "low", "red_led": "off"},
        )
    elif patient_state == "resting":
        fan_mode = "medium" if (
            summary.get("temperature_status") == "hot"
            or summary.get("humidity_status") == "high"
        ) else "low"
        goal_name, priority, modes = (
            "Support patient rest and save power",
            "normal",
            {"light": "off", "fan": fan_mode, "door": "locked", "buzzer": "off", "red_led": "off"},
        )
    elif patient_state == "awake":
        light_mode = "bright" if summary.get("light_level") == "dark" else "dim"
        fan_mode = "high" if (
            summary.get("temperature_status") == "hot"
            or summary.get("humidity_status") == "high"
        ) else "medium"
        goal_name, priority, modes = (
            "Maintain patient comfort while awake",
            "normal",
            {"light": light_mode, "fan": fan_mode, "door": "locked", "buzzer": "off", "red_led": "off"},
        )
    else:
        goal_name, priority, modes = (
            "Maintain safe default room state",
            "normal",
            {"light": "dim", "fan": "medium", "door": "locked", "buzzer": "off", "red_led": "off"},
        )

    goal_pddl = "(and\n              " + "\n              ".join(mode_predicates(modes)) + "\n            )"
    return goal_name, priority, goal_pddl


def generate_problem_pddl(state: dict) -> tuple[str, str, str]:
    """Build problem_latest.pddl from observations and the actuator state."""

    goal_name, priority, goal_pddl = goal_from_state(state)

    problem_text = f"""(define (problem room101-current-cycle)
  (:domain smart-hospital-room)

  (:objects
    room101 - room
    patient1 - patient
    light1 - light
    fan1 - fan
    door1 - door
    buzzer1 - buzzer
    redled1 - red-led
  )

  (:init
    {actuator_init_predicates()}
    {observation_predicates(state)}
  )

  (:goal
    {goal_pddl}
  )
)
"""

    return problem_text, goal_name, priority


def make_goal_signature(state: dict) -> tuple[Any, ...]:
    """
    Replan only when the symbolic goal-relevant state changes.
    This prevents replanning for tiny raw sensor fluctuations.
    """

    sensor_summary = state.get("sensor_summary", {})

    return (
        state.get("room_state"),
        state.get("patient_state"),
        int(state.get("out_of_bed_minutes", 0)) >= 15,
        sensor_summary.get("temperature_status"),
        sensor_summary.get("humidity_status"),
        sensor_summary.get("light_level"),
    )


# ============================================================
# PLANNER CALLS
# ============================================================

def run_online_planner(domain_text: str, problem_text: str) -> list[str]:
    """
    Call the new Planning-as-a-Service online solver.

    This uses the new package endpoint:
    https://solver.planning.domains:5001/package/lama-first/solve

    The new API is asynchronous:
    1. First POST submits the planning job.
    2. Server returns a result URL.
    3. We poll that result URL until the plan is ready.
    """

    payload = {
        "domain": domain_text,
        "problem": problem_text
    }

    print("\n==============================")
    print("SUBMITTING TO ONLINE PDDL SOLVER")
    print("==============================")
    print("URL:", PLANNING_SERVICE_URL)

    submit_response = requests.post(
        PLANNING_SERVICE_URL,
        json=payload,
        timeout=30
    )

    print("Submit status code:", submit_response.status_code)
    print("Submit response:")
    print(submit_response.text[:2000])

    if not submit_response.ok:
        raise RuntimeError(
            f"Online planner submit failed with status "
            f"{submit_response.status_code}. "
            f"Response: {submit_response.text[:1000]}"
        )

    submit_data = submit_response.json()

    # Sometimes a service may return the plan directly.
    direct_plan = extract_plan_lines(submit_data)
    if direct_plan:
        return direct_plan

    if "result" not in submit_data:
        raise RuntimeError(
            "Online planner did not return a result URL. "
            f"Response: {json.dumps(submit_data, indent=2)[:2000]}"
        )

    # Example returned path:
    # /result/.... or /celery-result/....
    result_path = submit_data["result"]

    # Base URL should become:
    # https://solver.planning.domains:5001
    base_url = PLANNING_SERVICE_URL.split("/package/")[0]

    result_url = urljoin(base_url, result_path)

    print("\nPolling result URL:")
    print(result_url)

    for attempt in range(60):
        time.sleep(0.5)

        result_response = requests.post(
            result_url,
            json={"adaptor": "planning_editor_adaptor"},
            timeout=30
        )

        print(f"Poll attempt {attempt + 1}, status:", result_response.status_code)

        if not result_response.ok:
            print("Poll response failed:")
            print(result_response.text[:1000])
            continue

        result_data = result_response.json()

        status = result_data.get("status", "")

        if status == "PENDING":
            print("Planner still running...")
            continue

        print("\n==============================")
        print("ONLINE PDDL SOLVER FINAL RESPONSE")
        print("==============================")
        print(json.dumps(result_data, indent=2)[:3000])

        plan_lines = extract_plan_lines(result_data)

        if plan_lines:
            return plan_lines

        raise RuntimeError(
            "Planner finished, but no plan actions were found. "
            f"Final response: {json.dumps(result_data, indent=2)[:3000]}"
        )

    raise RuntimeError("Online planner timed out after polling for 30 seconds.")


def run_local_fast_downward(domain_file: Path, problem_file: Path) -> list[str]:
    """
    Run a local Fast Downward installation.

    Example .env:
      PLANNER_MODE=local
      FAST_DOWNWARD_CMD=python C:\\path\\to\\fast-downward.py
    """

    if not FAST_DOWNWARD_CMD:
        raise RuntimeError(
            "FAST_DOWNWARD_CMD is empty. Set it in .env or use PLANNER_MODE=online."
        )

    if PLAN_FILE.exists():
        PLAN_FILE.unlink()

    command = FAST_DOWNWARD_CMD.split() + [
        str(domain_file),
        str(problem_file),
        "--alias",
        "lama-first"
    ]

    completed = subprocess.run(
        command,
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=60
    )

    if completed.returncode != 0:
        raise RuntimeError(
            "Fast Downward failed.\n"
            f"STDOUT:\n{completed.stdout}\n\n"
            f"STDERR:\n{completed.stderr}"
        )

    # Fast Downward usually writes sas_plan in the working directory.
    sas_plan = PROJECT_DIR / "sas_plan"
    if not sas_plan.exists():
        raise RuntimeError("Fast Downward finished, but sas_plan was not created.")

    plan_lines = [
        line.strip()
        for line in sas_plan.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith(";")
    ]

    return plan_lines


def extract_plan_lines(data: Any) -> list[str]:
    """
    Return actions from one valid planner solution only.
    Do not combine actions from multiple returned plans.
    """

    for plan_wrapper in data.get("plans", []):
        result = plan_wrapper.get("result", {})
        raw_plan = result.get("plan", [])

        if not isinstance(raw_plan, list) or not raw_plan:
            continue

        actions = []

        for action_item in raw_plan:
            if isinstance(action_item, dict):
                raw_action = action_item.get("name", "")
            else:
                raw_action = str(action_item)

            if raw_action == "Raw Result":
                continue

            cleaned = clean_plan_action(raw_action)

            if cleaned:
                actions.append(cleaned)

        if actions:
            return actions

    return []


KNOWN_PDDL_ACTIONS = {
    "set-light-off",
    "set-light-medium",
    "set-light-max",
    "set-fan-off",
    "set-fan-low",
    "set-fan-medium",
    "set-fan-high",
    "lock-door",
    "unlock-door",
    "set-buzzer-off",
    "set-buzzer-low",
    "set-buzzer-high",
    "set-red-led-off",
    "set-red-led-blink",
}


def clean_plan_action(line: str) -> str:
    """
    Normalize one planner output line.

    Accepts:
      0: (set-light-max light1 room101)
      (set-light-max light1 room101)
      set-light-max light1 room101
      set-light-max(light1, room101)

    Rejects invalid non-actions:
      (buzzer1 room101)
      (fan1 room101)
      (light1 room101)
      (1)
    """

    if not line:
        return ""

    line = line.strip().lower()

    # Remove comments.
    line = line.split(";", 1)[0].strip()

    # Convert "0: (action ...)" to "(action ...)".
    if ":" in line:
        possible_action = line.split(":", 1)[1].strip()
        if possible_action:
            line = possible_action

    # Convert "set-light-max(light1, room101)"
    # to "(set-light-max light1 room101)".
    function_style = re.match(r"^([a-z0-9_-]+)\(([^)]*)\)$", line)
    if function_style:
        action_name = function_style.group(1)
        args = function_style.group(2).replace(",", " ").split()

        if action_name in KNOWN_PDDL_ACTIONS and len(args) >= 2:
            return f"({action_name} {' '.join(args)})"

        return ""

    # Convert "set-light-max light1 room101"
    # to "(set-light-max light1 room101)".
    if not line.startswith("("):
        tokens = line.split()

        if len(tokens) >= 3 and tokens[0] in KNOWN_PDDL_ACTIONS:
            return f"({' '.join(tokens)})"

        return ""

    # Extract "(...)" if the line contains a PDDL-style action.
    match = re.search(r"\(([a-z0-9_-]+)(?:\s+[^()]*)?\)", line)

    if not match:
        return ""

    action_text = match.group(0)
    tokens = action_text.strip("()").split()

    if len(tokens) < 3:
        return ""

    action_name = tokens[0]

    if action_name not in KNOWN_PDDL_ACTIONS:
        return ""

    return f"({' '.join(tokens)})"

def run_planner(problem_text: str) -> list[str]:
    """Run selected PDDL planner and return plan lines."""

    domain_text = DOMAIN_FILE.read_text(encoding="utf-8")

    PROBLEM_FILE.write_text(problem_text, encoding="utf-8")

    if PLANNER_MODE == "online":
        return run_online_planner(domain_text, problem_text)

    if PLANNER_MODE == "local":
        return run_local_fast_downward(DOMAIN_FILE, PROBLEM_FILE)

    raise RuntimeError(f"Unknown PLANNER_MODE={PLANNER_MODE}. Use online or local.")


# ============================================================
# ACTION EXECUTION: PDDL ACTION → MQTT COMMAND
# ============================================================

def execute_pddl_action(client: mqtt.Client, room_id: str, action_line: str):
    """Translate one grounded PDDL action to one MQTT actuator command."""

    action = clean_plan_action(action_line)
    base_topic = f"hospital/{room_id}"

    print(f"Executing PDDL action: {action}")

    if action.startswith("(set-light-off"):
        client.publish(f"{base_topic}/cmd/light", "0")
        current_actuator_state["light"] = "off"

    elif action.startswith("(set-light-medium"):
        client.publish(f"{base_topic}/cmd/light", "50")
        current_actuator_state["light"] = "dim"

    elif action.startswith("(set-light-max"):
        client.publish(f"{base_topic}/cmd/light", "100")
        current_actuator_state["light"] = "bright"

    elif action.startswith("(set-fan-off"):
        client.publish(f"{base_topic}/cmd/fan", "0")
        current_actuator_state["fan"] = "off"

    elif action.startswith("(set-fan-low"):
        client.publish(f"{base_topic}/cmd/fan", "25")
        current_actuator_state["fan"] = "low"

    elif action.startswith("(set-fan-medium"):
        client.publish(f"{base_topic}/cmd/fan", "50")
        current_actuator_state["fan"] = "medium"

    elif action.startswith("(set-fan-high"):
        client.publish(f"{base_topic}/cmd/fan", "100")
        current_actuator_state["fan"] = "high"

    elif action.startswith("(lock-door"):
        client.publish(f"{base_topic}/cmd/door", "0")
        current_actuator_state["door"] = "locked"

    elif action.startswith("(unlock-door"):
        client.publish(f"{base_topic}/cmd/door", "1")
        current_actuator_state["door"] = "unlocked"

    elif action.startswith("(set-buzzer-off"):
        client.publish(f"{base_topic}/cmd/buzzer", "0")
        current_actuator_state["buzzer"] = "off"

    elif action.startswith("(set-buzzer-low"):
        client.publish(f"{base_topic}/cmd/buzzer", "low")
        current_actuator_state["buzzer"] = "low"

    elif action.startswith("(set-buzzer-high"):
        client.publish(f"{base_topic}/cmd/buzzer", "high")
        current_actuator_state["buzzer"] = "high"

    elif action.startswith("(set-red-led-off"):
        client.publish(f"{base_topic}/cmd/red_led", "0")
        current_actuator_state["red_led"] = "off"

    elif action.startswith("(set-red-led-blink"):
        client.publish(f"{base_topic}/cmd/red_led", "1")
        current_actuator_state["red_led"] = "blink"

    else:
        print(f"Warning: no MQTT mapping for PDDL action: {action}")


def execute_pddl_plan(client: mqtt.Client, room_id: str, plan_lines: list[str], priority: str):
    """Execute the complete PDDL plan.

    The red LED is now an explicit PDDL state/action instead of a hidden
    priority-based command after the plan.
    """

    for line in plan_lines:
        execute_pddl_action(client, room_id, line)


def publish_plan_to_dashboard(
    client: mqtt.Client,
    room_id: str,
    goal_name: str,
    priority: str,
    plan_lines: list[str],
    status: str,
    reason: str = ""
):
    """Publish full PDDL plan and final actuator state for dashboard."""

    base_topic = f"hospital/{room_id}"

    dashboard_plan = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "planner_type": "pddl",
        "planner_mode": PLANNER_MODE,
        "planner_name": "Planning.Domains" if PLANNER_MODE == "online" else "Fast Downward",
        "status": status,
        "priority": priority,
        "goal": goal_name,
        "plan": plan_lines,
        "actuator_state_after_plan": current_actuator_state,
        "reason": reason,
    }

    client.publish(f"{base_topic}/plan", json.dumps(dashboard_plan))

    PLAN_FILE.write_text(
        "\n".join(plan_lines) if plan_lines else f"No plan. Status: {status}. {reason}",
        encoding="utf-8"
    )

    print("\n==============================")
    print("PDDL PLAN PUBLISHED TO DASHBOARD")
    print("==============================")
    print(json.dumps(dashboard_plan, indent=2))


# ============================================================
# MQTT CALLBACK
# ============================================================

def on_message(client: mqtt.Client, userdata, msg):
    global previous_goal_signature

    try:
        state = json.loads(msg.payload.decode("utf-8"))
    except json.JSONDecodeError:
        print("Received invalid JSON; ignoring message.")
        return

    print("\n==============================")
    print("STATE RECEIVED BY PDDL PLANNER")
    print("==============================")
    print(json.dumps(state, indent=2))

    room_id = state.get("room_id", ROOM_ID)
    current_signature = make_goal_signature(state)

    if current_signature == previous_goal_signature:
        print("No goal-relevant symbolic state change. No replanning needed.")
        return

    previous_goal_signature = current_signature
    print("State/goal changed. Generating new PDDL problem and replanning.")

    problem_text, goal_name, priority = generate_problem_pddl(state)

    try:
        plan_lines = run_planner(problem_text)
        print("\nPDDL plan found:")
        for line in plan_lines:
            print(line)

        execute_pddl_plan(client, room_id, plan_lines, priority)
        publish_plan_to_dashboard(
            client=client,
            room_id=room_id,
            goal_name=goal_name,
            priority=priority,
            plan_lines=plan_lines,
            status="plan_found"
        )

    except Exception as e:
        error_msg = str(e)
        print("\nPlanner failed:")
        print(error_msg)

        publish_plan_to_dashboard(
            client=client,
            room_id=room_id,
            goal_name=goal_name,
            priority=priority,
            plan_lines=[],
            status="planner_failed",
            reason=error_msg
        )


# ============================================================
# MAIN
# ============================================================

def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_message = on_message

    print(f"Connecting to MQTT broker at {BROKER_HOST}:{BROKER_PORT}...")
    client.connect(BROKER_HOST, BROKER_PORT, 60)

    topic = "hospital/+/state"
    client.subscribe(topic)

    print(f"PDDL planner service is listening on: {topic}")
    print(f"Planner mode: {PLANNER_MODE}")
    client.loop_forever()


if __name__ == "__main__":
    main()
