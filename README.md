# FireGuard AI — Vision-Based Fire Detection with Automated Water Sprinkler Activation

End-to-end simulation of an intelligent fire-suppression system:

**YOLOv8 detection → temporal validation → smoke-sensor corroboration → LiDAR distance → physics-based pressure estimation → closed-loop suppression → visual verification.**

Detection runs the real trained YOLOv8 model on video. The camera, the MQ-2 smoke sensor, the TF-Luna LiDAR and the pump/valve are simulated with realistic physics, and every value that is simulated is labelled as such on the dashboard.

---

## How it works

```
 Camera / video clip ──► YOLOv8 (best.pt) ──► Temporal validation ──► Sensor fusion ──► Fire confirmed
                          fire + smoke boxes    K of last N frames,       MQ-2 smoke ppm     alarm, pan/tilt aim
                                                boxes must overlap        must corroborate        │
                                                                                                  ▼
   Verification ◄── Suppression (closed loop) ◄── Pressure estimation ◄── LiDAR distance estimation
   N fire-free         valve + pump ramp,          projectile + Bernoulli     TF-Luna samples,
   frames, post-wet    spray until YOLO sees       + Darcy-Weisbach           median filter
                       no fire                     → pump pressure
```

| # | Stage | What happens | Fails / alternative outcome |
|---|-------|--------------|------------------------------|
| 1 | **YOLOv8 detection** | `best.pt` (classes `fire`, `smoke`) runs on every frame (~65–150 ms on a laptop CPU). A fire box above the confidence threshold starts an incident. | — |
| 2 | **Temporal validation** | The fire must appear in **10 of the last 15** inferred frames and the boxes must overlap (mean IoU ≥ 0.1). | A flash, reflection or flicker never persists → **False alarm rejected**, no water. |
| 3 | **Sensor fusion** | The MQ-2 smoke sensor must exceed **300 ppm**. Smoke takes a few seconds to reach the sensor (transport delay + sensor lag). | No smoke within 15 s → **Operator alert** (camera only), no automatic water. Smoke without flames → **Smoke-only alert**. |
| 4 | **Fire confirmed** | Two independent sources agree. The alarm is raised and the pan/tilt angles to the fire are computed from the box centre (pinhole camera model). | — |
| 5 | **LiDAR distance** | TF-Luna samples (0.2–8 m, ±2 cm) are median-filtered; the slant range is converted to horizontal distance; fire size comes from box size × distance. | No valid returns (out of range or obscured by smoke) → **Escalated**. |
| 6 | **Pressure estimation** | Physics model below → required pump pressure and flow. | Above the pump maximum → **Escalated**. |
| 7 | **Suppression** | The valve opens (~1 s), the pump ramps up and water flows. The simulated fire intensity falls according to applied flow ÷ required flow; steam hides the flames. | Not knocked down within 60 s → **Escalated**. |
| 8 | **Verification** | YOLO must see **no fire for 12 consecutive frames**, then 3 s of post-wetting. If fire reappears (re-flash), suppression resumes. | — |
| 9 | **Complete** | The valve closes, an incident report is stored and the system re-arms. Residual smoke after extinguishing does not raise a new alarm. | — |

### Pressure estimation (physics)

| Step | Formula | Meaning |
|------|---------|---------|
| Geometry | `d = √(L² − Δh²)` | LiDAR slant range `L` → horizontal distance; `Δh` = nozzle height − aim height |
| Projectile | `v₀ = √( g·d² / (2·cos²θ·(Δh + d·tanθ)) )` | Jet speed so the water, launched at angle θ, lands on the fire |
| Drag margin | `v = v₀ · (1 + margin)` | Air drag allowance (default +10 %) |
| Nozzle (Bernoulli) | `Pₙ = ½·ρ·(v/Cv)²`, `Q = Cd·A·v` | Nozzle pressure and flow rate |
| Pipe friction | `ΔP_f = f·(L/D)·½ρV²`, f from Swamee–Jain (or 64/Re if laminar) | Darcy–Weisbach |
| Fittings + lift | `ΔP_m = ΣK·½ρV²`, `ΔP_z = ρ·g·Δz` | Valve/elbow losses, lifting water to the nozzle |
| Pump | `P = Pₙ + ΔP_f + ΔP_m + ΔP_z` | Required pump pressure (bar / psi) |
| Required flow | `Q_req = density × area` | NFPA 13 ordinary-hazard density 6.1 L/min/m² × fire area |

All parameters (nozzle height, angle and diameter, pipe length and diameter, pump limits, and more) can be edited on the **Settings** page. The module is `backend/app/physics.py`, unit-tested in `backend/tests/test_physics.py`.

---

## Setup (Windows)

Requirements: **Python 3.10–3.12** (not 3.13), **Node.js 18+**.

```bat
start.bat
```

`start.bat` creates the virtual environment, installs CPU PyTorch and the requirements, then starts both servers. To do it manually:

```bat
cd backend
py -3.10 -m venv venv
venv\Scripts\activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8000

cd ..\frontend
npm install
npm run dev -- --host
```

Open **http://localhost:3000**. The backend API docs are at http://localhost:8000/docs.

### Demo assets (not in git — they are large)

1. **Model:** copy the trained weights to `backend/models/best.pt`.
2. **Video clips:** convert them once (this downscales to 960 px and writes `media/clips.json`):

```bat
cd backend
venv\Scripts\activate
python tools\prepare_media.py --fire   "C:\path\bonfire.mp4"  --id bonfire  --label "Outdoor bonfire (heavy smoke)" --smoke-factor 1.3
python tools\prepare_media.py --fire   "C:\path\campfire.mp4" --id campfire --label "Campfire (light smoke)" --smoke-factor 0.8
python tools\prepare_media.py --normal "C:\path\highway.mp4"  --id highway  --label "Highway - normal scene"
```

`--smoke-factor` controls how smoky the simulated fire is, which changes how fast the MQ-2 reading rises.

---

## Presenting the demo

Open the **Pipeline** page (`/`) on the projector. Presenter controls sit under the camera; the same controls are on **`/presenter`**, so a phone on the same Wi-Fi can drive the demo (`http://<laptop-ip>:3000/presenter`).

| Key | Action | Expected outcome (about 20 s) |
|-----|--------|------------------------|
| **I** | Ignite fire | All 9 stages in order: detect (~0.5 s) → validated (~2 s) → smoke confirmed (~4 s) → LiDAR → pressure → water (~10 s) → fire out → complete |
| **F** | False alarm (0.5 s flash) | Detected, then **rejected by temporal validation**. No water. |
| **S** | Smoke only (cooking smoke) | MQ-2 alarm with no flames → **operator alert**. No water. |
| **P** | Pause / resume video | Freeze the frame while you explain a stage |
| **R** | Reset | Back to monitoring |
| slider | Fire distance | 9 m (beyond TF-Luna's 8 m range) → **escalated**; shorter or longer distances change the pressure |

Suggested order: **I** (full flow) → **R** → **F** (false alarm) → **S** (smoke only) → distance 9 m + **I** (escalation) → **R**.

The right-hand panel narrates each stage in plain words, and the card for the current stage is highlighted. Every incident is stored with its timeline on the **Incidents** page; the **Analytics** page shows totals and average response times.

**Before the review:** run the full scenario once on the presentation laptop. If the yellow *"AI is running slowly"* banner appears, close other programs, plug in the charger, or set *Inference size* to 480 px in Settings. Slower inference only makes stages take longer; it does not cause wrong decisions. *Min. time per stage on screen* (Settings) controls the pacing.

---

## Using real hardware

* **Sensors:** turn off *Simulated MQ-2 / TF-Luna sensors* in Settings and set the COM port. The Arduino sends one line per reading:
  `SMOKE:1,DIST:2.45` (optional extra fields: `PPM:540`, `STR:1830`). Lines are read continuously in the background, so readings never lag.
* **Camera:** set *Source* to *IP camera* (HTTP/MJPEG or RTSP) or *Local webcam*. Camera passwords are masked in the UI.
* The pump/valve stays simulated. The suppression stage computes the command pressure and flow that a pump controller would receive.

---

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/telemetry/latest` | Full live state (also pushed on `WS /ws/telemetry` at 4 Hz) |
| GET | `/api/stream/camera` | Annotated MJPEG stream (boxes, aim point, LiDAR beam, water jet) |
| GET/POST | `/api/scenario` | Clips and scene state / presenter actions (`ignite`, `false_alarm`, `inject_smoke`, `set_distance`, `select_clips`, `pause`, `resume`, `reset`) |
| GET | `/api/incidents` | Incident reports with timeline and metrics (paginated) |
| GET | `/api/events` | State transitions (paginated) |
| GET | `/api/events/stats` | Totals and average response times |
| GET | `/api/events/export/csv` | Incidents as CSV |
| GET/POST | `/api/settings` | Read / update settings (validated, persisted to `runtime_settings.json`) |

## Tests

```bat
cd backend
venv\Scripts\activate
python -m pytest -q
```

The tests cover physics, temporal validation, the sensor models, the simulated fire response to water, the Arduino parser, settings validation, every pipeline path (full flow, false alarm, flicker, slow CPU, camera-only alert, smoke only, LiDAR failure, pump limit, re-flash, timeout, reset) and the API.

## Project structure

```
backend/app/
  main.py         FastAPI app: detection loop, sensor/telemetry loop, MJPEG loop, REST + WebSocket
  pipeline.py     Decision state machine, narration, incident reports
  temporal.py     Sliding-window temporal validation
  physics.py      Geometry, aiming, fire size, hydraulics
  detection.py    YOLOv8 inference (+ colour-segmentation fallback)
  simulation.py   Scene ground truth, fire response to water, MQ-2 and TF-Luna models
  video.py        Clip playback / IP camera / webcam readers
  overlay.py      Annotated camera view
  hardware.py     Real Arduino serial reader
  database.py     SQLite: transitions + incidents
  config.py       Settings (.env + runtime overrides)
backend/tools/prepare_media.py   Convert demo clips
frontend/src/pages/Pipeline.jsx  Presentation page; components in src/components/pipeline/
```

> **Simulation notice:** the water suppression, pump and valve are simulated, and in demo mode so are the smoke sensor and LiDAR. Fire detection, temporal validation and verification run the real YOLOv8 model on real fire footage.
