PDDL AI Planning Upgrade - Beginner Steps

WHAT CHANGES FROM RULE-BASED PLANNER?
-------------------------------------
Old file:
  planner_service_rule_based.py

New PDDL files:
  domain.pddl
  pddl_planner_service.py

Unchanged or reusable:
  AI_sensor_publisher.py
  AI_actuator_subscriber.py
  .env

The PDDL service receives the same MQTT state:
  hospital/room101/state

It generates:
  problem_latest.pddl

It runs a PDDL planner and receives plan actions like:
  (set-light-max light1 room101)
  (unlock-door door1 room101)
  (set-buzzer-high buzzer1 room101)

It translates those actions into MQTT actuator commands:
  hospital/room101/cmd/light
  hospital/room101/cmd/fan
  hospital/room101/cmd/door
  hospital/room101/cmd/buzzer


STEP 1 - COPY FILES
-------------------
Copy these files into your VS Code project folder:
  C:\Users\YOUR_NAME\Documents\mediguard-ai-planner

Files:
  domain.pddl
  pddl_planner_service.py
  AI_sensor_publisher.py
  AI_actuator_subscriber.py
  .env.template
  requirements.txt

Rename .env.template to .env if you do not already have .env.


STEP 2 - UPDATE .env
--------------------
For laptop-only simulation:
  BROKER_HOST=localhost
  BROKER_PORT=1883
  ROOM_ID=room101
  PLANNER_MODE=online
  PLANNING_SERVICE_URL=https://solver.planning.domains/solve

For Raspberry Pi later:
  Change BROKER_HOST to your Raspberry Pi IP address.


STEP 3 - INSTALL PYTHON PACKAGES
--------------------------------
Open VS Code terminal inside mediguard-ai-planner.

Run:
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  .\.venv\Scripts\Activate.ps1
  pip install -r requirements.txt


STEP 4 - RUN THE SYSTEM IN THIS ORDER
-------------------------------------
Terminal 1:
  python AI_actuator_subscriber.py

Terminal 2:
  python pddl_planner_service.py

Terminal 3:
  python AI_sensor_publisher.py


STEP 5 - EXPECTED FLOW
----------------------
AI sensor publishes:
  room_state / patient_state

PDDL service:
  detects state change
  writes problem_latest.pddl
  calls planner
  receives PDDL action plan
  publishes full plan to hospital/room101/plan
  publishes actuator commands to hospital/room101/cmd/#

AI actuator:
  prints received commands


STEP 6 - DASHBOARD TOPICS
-------------------------
Dashboard should subscribe to:
  hospital/room101/#

Important dashboard messages:
  hospital/room101/state     -> current symbolic state
  hospital/room101/plan      -> PDDL plan and actuator state
  hospital/room101/cmd/light -> light command
  hospital/room101/cmd/fan   -> fan command
  hospital/room101/cmd/door  -> door command
  hospital/room101/cmd/buzzer-> buzzer command


STEP 7 - RASPBERRY PI INTEGRATION LATER
---------------------------------------
Keep pddl_planner_service.py on laptop.
Replace:
  AI_sensor_publisher.py with pi_sensor_node.py
  AI_actuator_subscriber.py with pi_actuator_node.py

The MQTT topics stay the same.
