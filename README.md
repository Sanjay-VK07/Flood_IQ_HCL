# FloodIQ Disaster Management Platform

**AI-Assisted Urban Flood Intelligence & Emergency Response Coordination**

> **Technical Scope**: Zone risk scores use an explainable heuristic (`R = 0.40P + 0.30D + 0.30L`), not a validated hydrological forecasting model. Response teams, bases, and equipment records are configured operational data. Groq AI (with deterministic rule-based fallback) assists with incident triage, while human operators retain sole dispatch authority.

---

## Architecture & Portals

FloodIQ connects three roles through one **Next.js** frontend (`frontend/`), one **FastAPI** backend (`api.py`), and one shared **SQLite** database (`floodiq.db`):

1. **Citizen Portal (`/citizen`)**: Neighborhood risk advisories, emergency reporting with optional image upload and guest tracking (`TRK-...`), `My Reports`, and safety guidance.
2. **Municipal Authority Portal (`/`, `/risk`, `/preparedness`, `/report`, `/control-room`, `/history`, `/system`)**: Command Center, catchment risk assessment, preparedness checklists, incident intake, human-approved dispatch, audit timelines, and system diagnostics.
3. **Emergency Response Team Portal (`/team`)**: Scoped dispatch queue for assigned units, assignment acknowledgement, on-scene progress updates, field notes, and mission resolution.

---

## Quick Start (Clean Clone)

### 1. Prerequisites
- **Python 3.11+** (tested on Python 3.11.15; `venv` + `pip`)
- **Node.js 20+** and **npm 10+** (tested on Node v22.23.4, npm 10.9.9)
- **Git**

### 2. Clone the Repository

```bash
git clone https://github.com/Sanjay-VK07/Flood_IQ_HCL.git
cd Flood_IQ_HCL
```

### 3. Backend Setup & Startup (Terminal 1)

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn api:app --host 0.0.0.0 --port 8000
```

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn api:app --host 0.0.0.0 --port 8000
```

- **Groq AI (Optional)**: Set `GROQ_API_KEY` in `.env` (get a key at `https://console.groq.com/keys`). Leave it blank to run with the built-in deterministic rule-based triage fallback (`GROQ_MODEL` defaults to `openai/gpt-oss-20b`).
- **SQLite Initialization**: `floodiq.db` is automatically created and seeded on FastAPI startup (`init_db()` in `api.py` using `data/hyderabad_zones.json` and `data/seed_data.json`).
- **Verify Backend**:
  - Health check: `http://localhost:8000/health`
  - OpenAPI docs: `http://localhost:8000/docs`

### 4. Frontend Setup & Startup (Terminal 2)

```bash
cd frontend
npm install

# Optional: copy frontend/.env.example to frontend/.env.local if overriding NEXT_PUBLIC_API_URL
# By default, the browser resolves FastAPI on port 8000 of the current hostname.

npm run build
npm run start -- -H 0.0.0.0 -p 3000
```

Open `http://localhost:3000/login` in your browser.

> If port `3000` is occupied on your machine, start Next.js on another port (e.g., `-p 3005`) and include `http://localhost:3005` in `CORS_ORIGINS` in `.env`.

---

## Environment Variables

### Backend (`.env`, template in `.env.example`)
| Variable | Default | Purpose |
|---|---|---|
| `GROQ_API_KEY` | *(empty)* | Optional Groq API key for structured LLM triage; empty/invalid/rate-limited triggers deterministic fallback |
| `GROQ_MODEL` | `openai/gpt-oss-20b` | Groq model supporting Structured Outputs (`json_schema`) |
| `GROQ_COOLDOWN_SECONDS` | `60` | Cooldown after HTTP `429` rate-limit responses |
| `GROQ_MAX_RETRIES` | `2` | Max bounded retries for transient provider errors |
| `DATABASE_PATH` | `floodiq.db` | SQLite database file path |
| `WEATHER_API_TIMEOUT` | `10` | Open-Meteo request timeout in seconds |
| `OFFLINE_MODE` | `false` | Forces offline/fallback modes for weather & AI |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Comma-separated allowed frontend origins |

### Frontend (`frontend/.env.local`, template in `frontend/.env.example`)
| Variable | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` (or dynamic `http://<host>:8000` in browser) | FastAPI backend base URL |

---

## Dataset Availability

The historical dataset (`data/floodiq_training_dataset.csv`, 28,943 rows) and metadata (`data/dataset_metadata.json`) are pre-generated in the repository from Open-Meteo Historical Weather (2010–2025), Zenodo Global Flood Records, and NASA SRTM 90m (`data/cache/`). To regenerate it from cached/public sources:

```bash
python data_pipeline.py
```

---

## Authentication & Demo Accounts

On `/login`, select a role tab (`Citizen`, `Municipal Authority`, `Response Team`), use **Report an Emergency** for unauthenticated guest access (`/citizen`), or expand **Explore Demo Accounts**:

| Role | Name / Unit | Email | Password | Landing Route |
|---|---|---|---|---|
| **Citizen** | Asha Reddy | `citizen@floodiq.demo` | `Citizen@123` | `/citizen` |
| **Citizen (Alt)** | Citizen 2 | `citizen2@floodiq.demo` | `Citizen@123` | `/citizen` |
| **Municipal Authority** | Duty Officer Verma | `authority@floodiq.demo` | `Authority@123` | `/` |
| **Response Team** | Water Rescue Bravo (`wrt_02`) | `bravo@floodiq.demo` | `Team@123` | `/team` |
| **Response Team (Alt)** | Water Rescue Alpha (`wrt_01`) | `alpha@floodiq.demo` | `Team@123` | `/team` |

---

## End-to-End Walkthrough (2–3 Minutes)

1. **Citizen Report (`/login` → `/citizen`)**: Expand **Explore Demo Accounts** → click **Citizen Demo (Asha Reddy)** → open **Report** → choose `Musi Riverfront`, `Water Rescue / Stranded`, enter landmark and people count, and click **Transmit Emergency Report**. Note the generated Incident ID (`FIQ-...`) and Tracking Code (`TRK-...`).
2. **Authority Review & Dispatch (`/control-room`)**: Sign out → sign in as **Authority Demo (Officer Verma)** → open **Response Control Room** → select the new incident, inspect the AI/fallback triage and recommended unit (`Water Rescue Bravo`), and click **Authorize & Dispatch Team**.
3. **Response Team Execution (`/team`)**: Sign out → sign in as **Field Unit Demo (Bravo wrt_02)** → click **Acknowledge Assignment** → **On-Scene / Start Response** (with a field note) → **Mark Mission Resolved**.
4. **Cross-Portal Sync & Reset**: Check Citizen **My Reports** or Authority **Incident History** (`/history`) for the complete 6-step timeline. Use **Reset Scenario Data** in the Authority sidebar to restore the 2 baseline incidents and 5 available teams.

---

## Automated Verification & Checks

**Backend tests (118 tests):**
```bash
pytest tests/ -v
```
*(Note: `test_live_groq_api_integration` runs against Groq when `GROQ_API_KEY` is configured and skips cleanly when unset.)*

**Three-session integration script (writes to `DATABASE_PATH`):**
```bash
python scripts/verify_three_sessions.py
```

**Frontend lint, typecheck & production build:**
```bash
cd frontend
npm run lint
npx tsc --noEmit
npm run build
```

---

## Troubleshooting

- **Port `3000` or `8000` already in use**: Start Next.js on `-p 3005` and add `http://localhost:3005` to `CORS_ORIGINS` in `.env`, then restart Uvicorn.
- **PowerShell `Activate.ps1` execution policy error**: Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` before activating `.venv\Scripts\Activate.ps1`, or invoke `.venv\Scripts\python.exe` directly.
- **`GROQ_API_KEY` missing, invalid (`401`), or rate-limited (`429`)**: FloodIQ automatically switches to `rule_based` deterministic triage so all workflows continue without interruption. Check `/system` for current provider diagnostics.
- **LAN access from another device**: Start both servers with `--host 0.0.0.0` / `-H 0.0.0.0`, allow TCP ports `8000` and `3000`/`3005` in your firewall, and add `http://<your-lan-ip>:3000` to `CORS_ORIGINS` in `.env`.

---

## License

MIT License.
