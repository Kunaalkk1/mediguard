# MediGuard

A smart hospital-room monitoring and automation system. Sensors describe the
room and patient, an **AI (PDDL) planner** decides how the actuators should
respond, and a live dashboard visualises both the current state and the latest
plan being executed.

The system spans two machines communicating **indirectly over MQTT**:

```
  Raspberry Pi (src/main.py)                 Planner host (src/AI_pddl_planner_service.py)
  ┌───────────────────────────┐              ┌────────────────────────────┐
  │ sensors → brain (classify) │  state ───▶  │ generate PDDL problem       │
  │ local safety + actuators   │◀── cmd ────  │ call planner, get plan      │
  │ Flask dashboard (localhost)│◀── plan ───  │ publish plan to dashboard   │
  └───────────────────────────┘   MQTT        └────────────────────────────┘
```

## Components

| Piece | File | Role |
| --- | --- | --- |
| Sensor readers | `src/sensors/` | GrovePi light/gas/PIR/pressure, DHT temp+humidity, SOS button, simulated vitals |
| Brain | `src/main.py`, `src/logic/` | Classify snapshots → room/patient state, run local safety, publish state |
| MQTT bridge | `src/mqtt_bridge.py` | Publish state, receive planner commands, drive actuators, forward the plan to the dashboard |
| AI planner | `src/AI_pddl_planner_service.py`, `src/domain.pddl` | Auto-generate a PDDL problem each cycle and solve it |
| Dashboard | `src/web_server.py`, `src/templates/`, `src/static/` | Live visualisation hosted on `localhost` |

## Sensors & actuators

* **Sensors (7):** light, gas (MQ135), PIR motion, bed pressure (FSR), temperature,
  humidity, SOS button. Vital signs (pulse/SpO2) are a **simulated/virtual**
  sensor — the physical SpO2 module was removed because a real distress reading
  cannot be produced safely on the bench.
* **Actuators (5):** light (PWM), fan (PWM), door lock (relay), buzzer, red alert LED.

## Emergencies (how to demonstrate each)

| Emergency | Trigger | Result |
| --- | --- | --- |
| **SOS** | Physical SOS button held **2 seconds** (toggles on/off) | Room `emergency` |
| **Hazard** | Gas sensor above threshold / high temperature | Room `hazardous` |
| **Medical** | Dashboard **"Simulate Medical Emergency"** button (stands in for the removed SpO2 sensor) | Patient `distress` |

All toggles are latching: activate once, deactivate on the next trigger.

## Running

1. **Start an MQTT broker** (e.g. Mosquitto) reachable at `BROKER_HOST:BROKER_PORT`.
2. **Start the planner service** (any machine that can reach the broker):
   ```
   python src/AI_pddl_planner_service.py
   ```
3. **Start the Pi node + dashboard:**
   ```
   python src/main.py
   ```
4. Open the dashboard at **http://localhost:7801**.

`src/main.py` runs in simulation on a laptop automatically (no GrovePi needed);
set `USE_SIMULATOR = False` to use real hardware on the Pi. If the broker is not
up yet, `main.py` still starts and keeps retrying — the dashboard and local
safety behaviour work regardless.

### Configuration (`.env`)

| Variable | Default | Meaning |
| --- | --- | --- |
| `BROKER_HOST` / `BROKER_PORT` | `127.0.0.1` / `1883` | MQTT broker |
| `ROOM_ID` | `room101` | Room identifier used in MQTT topics |
| `PLANNER_MODE` | `online` | `online` (Planning.Domains) or `local` (Fast Downward) |
| `MEDIGUARD_HOST` | `0.0.0.0` | Dashboard bind address (`0.0.0.0` = reachable over the hotspot; `127.0.0.1` = localhost only) |
| `MEDIGUARD_PORT` | `7801` | Dashboard port |

## Deploy on the Raspberry Pi

Do this once the code is on the Pi (via `git pull` or `scp`):

```bash
# 1. Dependencies (use a venv if your Pi OS is "externally managed")
cd mediguard
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install smbus2 RPi.GPIO          # real GrovePi hardware only

# 2. MQTT broker
sudo apt update && sudo apt install -y mosquitto mosquitto-clients
sudo systemctl enable --now mosquitto

# 3. Use real sensors/actuators (skip to run in simulation)
#    edit src/main.py  ->  USE_SIMULATOR = False

# 4. Run the two processes (separate terminals, tmux, or systemd units)
python3 src/AI_pddl_planner_service.py     # terminal A
python3 src/main.py                         # terminal B
```

The dashboard is now live on the Pi at **http://localhost:7801** (and on
`http://<pi-ip>:7801` for any device on the same network).

### Create a Wi-Fi hotspot and open the GUI from your phone

Raspberry Pi OS (Bookworm) uses NetworkManager, so one command starts an access
point on the built-in Wi-Fi:

```bash
sudo nmcli device wifi hotspot ssid MediGuard password "mediguard123" ifname wlan0

# Show the Pi's hotspot IP (NetworkManager uses 10.42.0.1 by default)
nmcli -g IP4.ADDRESS device show wlan0
```

To make the hotspot start automatically on every boot instead:

```bash
sudo nmcli connection add type wifi ifname wlan0 con-name MediGuardAP autoconnect yes ssid MediGuard
sudo nmcli connection modify MediGuardAP 802-11-wireless.mode ap ipv4.method shared \
     wifi-sec.key-mgmt wpa-psk wifi-sec.psk "mediguard123"
sudo nmcli connection up MediGuardAP
```

Then on your phone:

1. Join the Wi-Fi network **MediGuard** (password `mediguard123`).
2. Open a browser to **http://10.42.0.1:7801** (use the IP printed above).
3. Tap once — the dashboard requests full-screen on the first interaction.

> The Pi's single Wi-Fi radio can either host the hotspot **or** be a Wi-Fi
> client, not both at once. Use the Ethernet port if the Pi also needs internet
> (e.g. for the online planner).

### Full-screen / kiosk

The dashboard calls the browser's full-screen API on the first tap/click
automatically. For an unattended kiosk on the Pi's own display, launch Chromium
in kiosk mode instead:

```bash
chromium-browser --kiosk --app=http://localhost:7801
```
