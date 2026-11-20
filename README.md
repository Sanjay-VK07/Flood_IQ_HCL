# FloodIQ Disaster Management Platform

**AI-Assisted Urban Flood Intelligence & Emergency Response Coordination**

> **Prototype Disclaimer**: This is a hackathon prototype for disaster response coordination. Zone risk scores use an explainable heuristic, not a validated hydrological model. Response teams, bases, and locations are illustrative demonstration data. Groq AI or rule-based fallback assists with incident interpretation, while human operators retain sole dispatch authority. The app does not predict floods or dispatch real-world responders.

---

## Architecture & Portals

FloodIQ links three distinct roles through a unified FastAPI backend and SQLite persistence layer:

1. **Citizen Portal (`/citizen`)**: Neighborhood flood intelligence, quick emergency reporting with location, description, affected persons, and guest tracking (`TRK-...`).
2. **Municipal Authority Portal (`/`, `/control-room`, `/history`, `/risk`)**: Citywide command center, zone telemetry, AI/rule-based triage review, and human-approved team dispatch.
3. **Emergency Response Team Portal (`/team`)**: Tactical queue for assigned field units, order acknowledgement, field note submission, and on-scene resolution.

---

## Quick Start

### 1. Prerequisites
- Python 3.9+ (with venv)
- Node.js 18+ (with npm)

### 2. Backend Setup

```bash
cd FloodIQ

# Create & activate virtual environment
python3 -m venv venv
source venv/bin/activate    # On Windows: venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# GROQ_API_KEY can remain blank — app uses deterministic rule-based triage fallback

# Start FastAPI backend (port 8000)
uvicorn api:app --host 0.0.0.0 --port 8000
```
Backend health check: `http://localhost:8000/health`  
Interactive OpenAPI documentation: `http://localhost:8000/docs`

### 3. Frontend Setup (in a separate terminal)

```bash
cd FloodIQ/frontend

# Install dependencies
npm install

# Build & run production server (port 3000)
npm run build
npm run start -- -p 3000
```
Open `http://localhost:3000` in your browser.

> **Note for Judges**: Use the production workflow (`npm run build && npm run start -- -p 3000`) for evaluation. Running in production mode provides maximum responsiveness and ensures Next.js development diagnostic overlays (such as the route-info indicator) are disabled.

---

## Entry Flow & Authentication

On first visit or after sign-out, the app presents the **Sign-In / Portal Selection** screen (`/login`).

Users can choose their operational role using the one-tap **Demo Profile Switcher**:

| Role | Demo Identity | Credentials | Landing Destination |
|---|---|---|---|
| **Citizen** | Asha Reddy | `citizen@floodiq.demo` / `Citizen@123` | `/citizen` (Overview tab) |
| **Municipal Authority** | Duty Officer Verma | `authority@floodiq.demo` / `Authority@123` | `/` (Command Center) |
| **Field Response Unit** | Commander Vikram Singh (Bravo) | `bravo@floodiq.demo` / `Team@123` | `/team` (Tactical Queue) |
| **Public Guest** | Unauthenticated Citizen | *None required* | `/citizen` (Guest Mode) |

Signing out from any portal returns the user to the portal selection screen.

---

## 2–3 Minute Judge Demo Script

### Step 1: Citizen Emergency Submission (45s)
1. Open `http://localhost:3000/login` and click **Load Citizen Demo (Asha Reddy)**.
2. The Citizen Portal opens on the **Dashboard** overview. Click **Report** tab (or **Submit Emergency Report**).
3. Select zone **Musi Riverfront**, emergency type **Water Rescue / Stranded**, and landmark `Chaderghat Low Bridge Lane 4`.
4. Enter affected people: `3` and description: *"Ground floor flooded, elderly residents trapped."*
5. Click **Submit Report**.
6. View the confirmation receipt showing **Incident ID** (`FIQ-...`), **Tracking Code** (`TRK-...`), and initial AI triage status.

### Step 2: Municipal Authority Review & Dispatch Approval (60s)
1. In a second browser tab (or sign out and switch), sign in as **Load Authority Demo (Officer Verma)**.
2. On the **Command Center** (`/`), the newly reported incident appears in the queue.
3. Click **Review & Dispatch** or navigate to **Response Control Room** (`/control-room`).
4. Select the incident to review:
   - Priority score and vulnerability breakdown.
   - AI triage rationale (or deterministic fallback reasoning).
   - Recommended response unit: **Water Rescue Bravo** (with score and availability).
5. Enter an operator dispatch note (e.g., *"Deploy rubber dinghy with life jackets"*) and click **Authorize & Dispatch Team**.
6. Status advances to **Team Assigned**.

### Step 3: Response Team Tactical Execution & Resolution (45s)
1. Switch to a third tab (or sign out and switch) and sign in as **Load Field Unit Demo (Bravo wrt_02)**.
2. The tactical queue displays the assigned incident.
3. Click **Acknowledge Assignment** → status advances to **Acknowledged**.
4. Enter an en-route/arrival note and click **Mark In Progress** → status advances to **In Progress**.
5. Enter field resolution notes (e.g., *"All 3 residents safely evacuated to dry shelter"*) and click **Submit Resolution** → status advances to **Resolved**.

### Step 4: Cross-Portal Synchronization & Verification (15s)
1. Check the Citizen Portal (**My Reports** or **Tracking** with tracking code) → incident shows **Resolved** with complete timeline.
2. Check Authority Portal (**Incident History** or **Control Room**) → incident reflects **Resolved** with complete audit history.

---

## Weather Integration & Rainfall Forecast

- **Live Weather Mode**: FloodIQ connects to the Open-Meteo API for real-time precipitation and a **6-hour hourly rainfall outlook** across Hyderabad's pilot zones.
- **Transparency & Separation**: The 6-hour forecast (source: Open-Meteo, with explicit IST time window) is displayed in **Flood Risk Intelligence** (`/risk`) as an informational input. It is strictly kept separate from the heuristic risk score and is never represented as a flood probability.
- **Scenario Simulation**: Operators can toggle the simulation slider (`20 mm`, `50 mm`, `100 mm`) to test system preparedness and team capacity under varying conditions.
- **Graceful Fallback**: If Open-Meteo is unreachable, the system automatically switches to cached values or offline baseline telemetry without crashing.

---

## Automated Verification

```bash
# Run backend pytest suite (116 tests)
pytest tests/ -v

# Run 3-portal end-to-end integration test
python3 scripts/verify_three_sessions.py

# Run frontend build check
cd frontend && npm run build
```

---

## License

MIT License. Designed and built for the AI Disaster Response Hackathon.
