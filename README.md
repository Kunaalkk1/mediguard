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

Light brightness and fan speed use a **0–100 scale everywhere** (GUI, PDDL,
MQTT). The drivers map that scale into a **0–40 % PWM duty** ceiling calibrated
for the hardware (`HW_MAX_DUTY` in `actuators/light.py` and `actuators/fan.py`),
so 100 = 40 % duty.

## Hardware pin / port map

The GrovePi+ sits on the Raspberry Pi's I²C bus (I²C address `0x04`; Pi pins
**SDA = GPIO2 / phys 3**, **SCL = GPIO3 / phys 5**). Most peripherals plug into
GrovePi ports; the light and fan are driven by the Pi's own hardware PWM into an
L298N motor driver.

### Sensors

| Peripheral | Kind | Bus / driver | Port / pin | Code |
| --- | --- | --- | --- | --- |
| Grove light sensor | analog | GrovePi | **A0** | `sensors/grove_sensors.py` `LIGHT_PORT` |
| Bed pressure (RP-S40-ST FSR) | analog | GrovePi | **A1** | `sensors/grove_sensors.py` `PRESSURE_PORT` |
| MQ135 gas / air quality | analog | GrovePi | **A2** | `sensors/grove_sensors.py` `GAS_PORT` |
| Grove PIR motion | digital | GrovePi | **D2** | `sensors/grove_sensors.py` `PIR_PORT` |
| DHT11 temperature + humidity | digital | GrovePi | **D4** | `sensors/dht_reader.py` `DHT_PORT` |
| Grove button (SOS) | digital | GrovePi | **D7** | `sensors/grove_sensors.py` `SOS_PORT` |
| Pulse / SpO₂ (vitals) | software | — | — | `sensors/vitals.py` (simulated) |

### Actuators

| Peripheral | Kind | Bus / driver | Port / pin | Code |
| --- | --- | --- | --- | --- |
| Red alert LED | digital | GrovePi | **D3** | `actuators/red_led.py` `RED_LED_PORT` |
| Buzzer | digital | GrovePi | **D5** | `actuators/buzzer.py` `BUZZER_PORT` |
| Door lock relay (solenoid) | digital | GrovePi | **D6** | `actuators/lock.py` `RELAY_PORT` |
| Light (L298N ENB) | PWM | Pi hardware PWM | **GPIO12** (pwm0, phys 32) | `actuators/light.py` `LIGHT_PWM_PIN` |
| Fan (L298N ENA) | PWM | Pi hardware PWM | **GPIO13** (pwm1, phys 33) | `actuators/fan.py` `FAN_PWM_PIN` |

> The light/fan PWM pins need the `pwm-2chan` overlay under `[all]` in
> `/boot/firmware/config.txt` (`dtoverlay=pwm-2chan,pin=12,func=4,pin2=13,func2=4`),
> then a reboot. The L298N direction pins (IN1–IN4) are tied to fixed levels in
> hardware, so only the enable pins are driven.

## Manual vs. auto control

The **AUTO** button on the dashboard switches light + fan between:

* **Auto** (default, button glowing): the AI planner drives light and fan.
* **Manual**: the light/fan sliders become live and override the planner.

Precedence is **safety > manual > auto** — an active emergency always drives the
actuators regardless of mode, and manual setpoints resume once it clears.

The **door** is controlled independently of that toggle, matching the spec: the
AI planner only sets it while *Resting* (locked) and in critical states
(unlocked); when the patient is *Awake* the door is manual — press and **hold
the lock button for 0.5 s** to toggle it. Outside an emergency, a door left
unlocked for **60 s** auto-locks. During an emergency the door is forced
unlocked and the lock toggle is disabled.

## AI planner behaviour

The planner re-plans whenever the room/patient state changes and emits a plan of
`set-…` actions. Goals are **partial** — an actuator the planner doesn't own in a
given state (e.g. the door while Awake) is left untouched. Summary:

| State | Light | Fan | Door | Buzzer | Red LED |
| --- | --- | --- | --- | --- | --- |
| Hazardous / Emergency / Distress | 100 % | — | unlock | high | solid on |
| Out-of-bed | — | — | — | low (after 15 min) | blink |
| Resting | off | auto (DHT) | lock | off | off |
| Awake | auto (sunlight) or manual | auto (DHT) or manual | manual | off | off |

`PLANNER_MODE` selects the solver: `online` (Planning.Domains), `local` (Fast
Downward), or `offline` (a built-in solver, no internet). In `online` mode, if
the service is unreachable it automatically falls back to the offline planner
(`PLANNER_FALLBACK_OFFLINE=1`), so the system keeps working with no internet.

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
| `MEDIGUARD_HOST` | `0.0.0.0` | Dashboard bind address (`0.0.0.0` = reachable on the LAN / via `mediguard.local`; `127.0.0.1` = localhost only) |
| `MEDIGUARD_PORT` | `7801` | Dashboard port (set to `80` to drop the `:7801`, but that needs sudo on the Pi) |

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

# 4. Run the two processes (separate terminals, tmux, or systemd units).
python3 src/AI_pddl_planner_service.py      # terminal A
python3 src/main.py                         # terminal B
```

The dashboard is now live on the Pi at **http://localhost:7801** (and at
**http://mediguard.local:7801** for any device on the same network — see
[Networking](#networking-mediguardlocal-no-hotspot) below).

### Networking: `mediguard.local` (no hotspot)

MediGuard no longer runs its own Wi-Fi access point. Put the Pi on your normal
Wi-Fi or Ethernet, and the dashboard (bound to `0.0.0.0`) is reachable from any
device on that same network. To reach it by name instead of a changing IP, run
the one-time setup once on the Pi:

```bash
sudo bash scripts/pi_setup.sh      # sets hostname + mDNS + RealVNC, then: sudo reboot
```

That script sets the Pi's hostname to `mediguard` and enables `avahi-daemon`
(mDNS/Bonjour), so `mediguard.local` resolves for every phone/PC on the LAN.
After it runs, open the dashboard from any device:

- **http://mediguard.local:7801**

`main.py` prints this URL (plus the raw LAN IP as a fallback) at startup. To
drop the `:7801` and open just **http://mediguard.local**, set `MEDIGUARD_PORT=80`
in `.env` and run `main.py` with `sudo` (binding port 80 needs root on the Pi).

> mDNS works out of the box on Android, iOS and macOS. On Windows it needs the
> built-in mDNS (Windows 10/11 have it) or Apple's Bonjour; if `.local` won't
> resolve there, use the LAN IP the startup banner prints.

### Remote desktop — view the Pi's screen from a PC/Android (RealVNC)

`scripts/pi_setup.sh` also enables **RealVNC**, the remote-desktop server that
ships with Raspberry Pi OS, so you can see and control the Pi's GUI from another
machine:

1. Install the free **RealVNC Viewer** on your PC or Android device.
2. Connect it to **`mediguard.local`** (or the Pi's IP).
3. Log in with the Pi's username/password — you get the full desktop.

The Pi's terminal is separately available over SSH at `ssh pi@mediguard.local`.
For an untrusted network you can tunnel VNC through SSH so it's encrypted and
no VNC port is exposed:

```bash
# On your PC: forward local port 5901 to the Pi's VNC server over SSH,
ssh -L 5901:localhost:5900 pi@mediguard.local
# then point RealVNC Viewer at  localhost:5901
```

To enable VNC/SSH by hand instead of the script: `sudo raspi-config` →
*Interface Options* → *VNC* / *SSH* → enable.

### Full-screen / kiosk

The dashboard calls the browser's full-screen API on the first tap/click
automatically. For an unattended kiosk on the Pi's own display, launch Chromium
in kiosk mode instead:

```bash
chromium-browser --kiosk --app=http://localhost:7801
```
