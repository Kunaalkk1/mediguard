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
    "light": "medium",   # off / medium / max
    "fan": "medium",     # low / medium / high
    "door": "locked",    # locked / unlocked
    "buzzer": "off",     # off / low / high
}

previous_goal_signature = None


# ============================================================
# PDDL PROBLEM GENERATION
# ============================================================

def actuator_init_predicates() -> str:
    """Convert current actuator state into PDDL init predicates."""

    light_pred = {
        "off": "(light-off light1)",
        "medium": "(light-medium light1)",
        "max": "(light-max light1)",
    }[current_actuator_state["light"]]

    fan_pred = {
        "low": "(fan-low fan1)",
        "medium": "(fan-medium fan1)",
        "high": "(fan-high fan1)",
    }[current_actuator_state["fan"]]

    door_pred = {
        "locked": "(door-locked door1)",
        "unlocked": "(door-unlocked door1)",
    }[current_actuator_state["door"]]

    buzzer_pred = {
        "off": "(buzzer-off buzzer1)",
        "low": "(buzzer-low buzzer1)",
        "high": "(buzzer-high buzzer1)",
    }[current_actuator_state["buzzer"]]

    return f"""
    (light-in light1 room101)
    (fan-in fan1 room101)
    (door-in door1 room101)
    (buzzer-in buzzer1 room101)

    {light_pred}
    {fan_pred}
    {door_pred}
    {buzzer_pred}
    """


def goal_from_state(state: dict) -> tuple[str, str, str]:
    """
    Convert symbolic room/patient state into a PDDL goal.

    Returns:
      goal_name: short name for dashboard/logs
      priority: normal / warning / critical
      goal_pddl: PDDL goal content
    """

    room_state = state.get("room_state", "normal")
    patient_state = state.get("patient_state", "awake")
    out_of_bed_minutes = int(state.get("out_of_bed_minutes", 0))

    # 1. Highest priority: hazardous room
    if room_state == "hazardous":
        return (
            "Handle hazardous room condition",
            "critical",
            """
            (and
              (light-max light1)
              (fan-high fan1)
              (door-unlocked door1)
              (buzzer-high buzzer1)
            )
            """
        )

    # 2. Emergency / SOS
    if room_state == "emergency":
        return (
            "Handle emergency / SOS condition",
            "critical",
            """
            (and
              (light-max light1)
              (fan-medium fan1)
              (door-unlocked door1)
              (buzzer-high buzzer1)
            )
            """
        )

    # 3. Patient distress
    if patient_state == "distress":
        return (
            "Handle patient distress",
            "critical",
            """
            (and
              (light-max light1)
              (fan-medium fan1)
              (door-unlocked door1)
              (buzzer-high buzzer1)
            )
            """
        )

    # 4. Patient out of bed too long
    if patient_state == "out_of_bed" and out_of_bed_minutes >= 15:
        return (
            "Alert staff because patient is out of bed",
            "warning",
            """
            (and
              (light-medium light1)
              (fan-medium fan1)
              (door-locked door1)
              (buzzer-low buzzer1)
            )
            """
        )

    # 5. Patient resting
    if patient_state == "resting":
        sensor_summary = state.get("sensor_summary", {})
        temperature_status = sensor_summary.get("temperature_status", "comfortable")
        humidity_status = sensor_summary.get("humidity_status", "comfortable")

        if temperature_status == "hot" or humidity_status == "high":
            fan_goal = "(fan-medium fan1)"
        else:
            fan_goal = "(fan-low fan1)"

        return (
            "Support patient rest and save power",
            "normal",
            f"""
            (and
              (light-off light1)
              {fan_goal}
              (door-locked door1)
              (buzzer-off buzzer1)
            )
            """
        )

    # 6. Patient awake
    if patient_state == "awake":
        sensor_summary = state.get("sensor_summary", {})
        temperature_status = sensor_summary.get("temperature_status", "comfortable")
        humidity_status = sensor_summary.get("humidity_status", "comfortable")
        light_level = sensor_summary.get("light_level", "normal")

        if light_level == "dark":
            light_goal = "(light-max light1)"
        else:
            light_goal = "(light-medium light1)"

        if temperature_status == "hot" or humidity_status == "high":
            fan_goal = "(fan-high fan1)"
        else:
            fan_goal = "(fan-medium fan1)"

        return (
            "Maintain patient comfort while awake",
            "normal",
            f"""
            (and
              {light_goal}
              {fan_goal}
              (door-locked door1)
              (buzzer-off buzzer1)
            )
            """
        )

    # 7. Safe default
    return (
        "Maintain safe default room state",
        "normal",
        """
        (and
          (light-medium light1)
          (fan-medium fan1)
          (door-locked door1)
          (buzzer-off buzzer1)
        )
        """
    )


def generate_problem_pddl(state: dict) -> tuple[str, str, str]:
    """Build problem_latest.pddl from current symbolic state and current actuator state."""

    goal_name, priority, goal_pddl = goal_from_state(state)

    problem_text = f"""(define (problem room101-current-cycle)
  (:domain smart-hospital-room)

  (:objects
    room101 - room
    light1 - light
    fan1 - fan
    door1 - door
    buzzer1 - buzzer
  )

  (:init
    {actuator_init_predicates()}
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
    Read only the clean PDDL action names returned by the
    Planning.Domains Planning Editor adaptor.

    Expected response shape:
    {
        "plans": [
            {
                "result": {
                    "length": 2,
                    "plan": [
                        {"name": "(set-fan-low fan1 room101)", "action": "..."},
                        {"name": "(set-light-off light1 room101)", "action": "..."}
                    ]
                }
            }
        ]
    }
    """

    plan_lines = []

    for plan_wrapper in data.get("plans", []):
        result = plan_wrapper.get("result", {})

        for action_item in result.get("plan", []):
            raw_action_name = action_item.get("name", "")

            # Ignore a fallback item that may appear if parsing failed.
            if raw_action_name == "Raw Result":
                continue

            cleaned = clean_plan_action(raw_action_name)

            if cleaned:
                plan_lines.append(cleaned)

    # Remove duplicate actions but keep their order.
    unique_plan = []
    seen = set()

    for action in plan_lines:
        if action not in seen:
            unique_plan.append(action)
            seen.add(action)

    return unique_plan


KNOWN_PDDL_ACTIONS = {
    "set-light-off",
    "set-light-medium",
    "set-light-max",
    "set-fan-low",
    "set-fan-medium",
    "set-fan-high",
    "lock-door",
    "unlock-door",
    "set-buzzer-off",
    "set-buzzer-low",
    "set-buzzer-high",
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
    """Translate one grounded PDDL action to an MQTT command."""

    global current_actuator_state

    action = clean_plan_action(action_line)
    base_topic = f"hospital/{room_id}"

    print(f"Executing PDDL action: {action}")

    if action.startswith("(set-light-off"):
        client.publish(f"{base_topic}/cmd/light", "0")
        current_actuator_state["light"] = "off"

    elif action.startswith("(set-light-medium"):
        client.publish(f"{base_topic}/cmd/light", "60")
        current_actuator_state["light"] = "medium"

    elif action.startswith("(set-light-max"):
        client.publish(f"{base_topic}/cmd/light", "100")
        current_actuator_state["light"] = "max"

    elif action.startswith("(set-fan-low"):
        client.publish(f"{base_topic}/cmd/fan", "30")
        current_actuator_state["fan"] = "low"

    elif action.startswith("(set-fan-medium"):
        client.publish(f"{base_topic}/cmd/fan", "60")
        current_actuator_state["fan"] = "medium"

    elif action.startswith("(set-fan-high"):
        client.publish(f"{base_topic}/cmd/fan", "100")
        current_actuator_state["fan"] = "high"

    elif action.startswith("(lock-door"):
        client.publish(f"{base_topic}/cmd/door", "lock")
        current_actuator_state["door"] = "locked"

    elif action.startswith("(unlock-door"):
        client.publish(f"{base_topic}/cmd/door", "unlock")
        current_actuator_state["door"] = "unlocked"

    elif action.startswith("(set-buzzer-off"):
        client.publish(f"{base_topic}/cmd/buzzer", "off")
        current_actuator_state["buzzer"] = "off"

    elif action.startswith("(set-buzzer-low"):
        client.publish(f"{base_topic}/cmd/buzzer", "low")
        current_actuator_state["buzzer"] = "low"

    elif action.startswith("(set-buzzer-high"):
        client.publish(f"{base_topic}/cmd/buzzer", "high")
        current_actuator_state["buzzer"] = "high"

    else:
        print(f"Warning: no MQTT mapping for PDDL action: {action}")


def execute_pddl_plan(client: mqtt.Client, room_id: str, plan_lines: list[str]):
    """Execute complete PDDL plan by publishing MQTT actuator commands."""

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

        execute_pddl_plan(client, room_id, plan_lines)
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
