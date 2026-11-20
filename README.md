# FloodIQ Disaster Management Platform

**AI-Assisted Urban Flood Intelligence & Emergency Response Coordination**

> **Prototype Disclaimer**: This is a hackathon prototype. Zone risk scores use an
> explainable heuristic, not a validated hydrological model. Response teams and their
> locations are illustrative demonstration data. Groq AI assists with incident interpretation,
> but human operators control all assignments.

## Quick Start

```bash
# 1. Clone and enter the project
cd FloodIQ

# 2. Create virtual environment
python -m venv .venv
# macOS / Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env and add your GROQ_API_KEY and GROQ_MODEL (optional — deterministic fallback works without it)
# Optional: set CORS_ORIGINS=http://localhost:3000 for custom frontend origins
# Frontend: copy frontend/.env.example to frontend/.env.local if API is not on localhost:8000

# 5. Run the FastAPI backend (http://localhost:8000, docs at /docs, health at /health)
uvicorn api:app --host 0.0.0.0 --port 8000

# 6. Run the Next.js frontend (in a second terminal, http://localhost:3000)
cd frontend
npm install
npm run dev

# 7. Run backend tests
pytest tests/ -v
```

## Three-Minute Demo Flow

1. **Command Center (`1. Command Center`)**: Start at the `20 mm` baseline simulation. Point out the 5 Hyderabad pilot zones, KPIs, and vulnerability-first incident queue.
2. **Cloudburst Simulation (`100 mm`)**: Click `100 mm` in the sidebar and open `2. Predict — Flood Risk` to show zone scores, risk bands, the `R = 0.40P + 0.30D + 0.30L` breakdown chart, and dynamic checklists in `3. Prepare — Readiness`.
3. **Citizen Intake & AI Triage (`4. Citizen Reporting`)**: Load Incident A (stranded elderly near Musi Riverfront) and submit to see the extracted vulnerability/hazard flags, triage mode, and priority score (~92/100).
4. **Human-in-the-Loop Dispatch (`5. Respond — Control Room`)**: Click **Proceed to Control Room Response Dispatch**, inspect the priority breakdown and recommended team (`Water Rescue Bravo`), approve dispatch with an operator note, and advance status to `In Progress` / `Resolved`.
5. **Audit Trail & Reset (`6. Incident History` & `7. System Information`)**: Review the chronological timeline, explain fallback resilience and prototype limitations, then click **Reset Demo Data** in the sidebar.

## Architecture

| Module | Responsibility |
|---|---|
| `config.py` | Configuration, constants, environment variables |
| `database.py` | SQLite schema, CRUD, workflow transitions |
| `weather.py` | Open-Meteo integration with offline fallback |
| `risk_engine.py` | Explainable flood risk scoring |
| `ai_engine.py` | Gemini AI triage with deterministic fallback |
| `response_engine.py` | Priority scoring and team recommendation |
| `app.py` | Streamlit UI — navigation, rendering, forms |

## Team

Built for a 24-hour hackathon by a team of three.

## License

MIT
