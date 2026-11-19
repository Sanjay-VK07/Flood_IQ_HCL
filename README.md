# FloodIQ — AI-Powered Urban Flood Intelligence & Emergency Response

> **Prototype Disclaimer**: This is a hackathon prototype. Zone risk scores use an
> explainable heuristic, not a validated hydrological model. Response teams and their
> locations are illustrative demonstration data. AI assists with incident interpretation,
> but human operators control all assignments.

## Quick Start

```bash
# 1. Clone and enter the project
cd FloodIQ

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY (optional — fallback works without it)

# 5. Run the application
streamlit run app.py

# 6. Run tests
pytest tests/ -v
```

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
