# MBM Radar 🚨

MBM Radar is a professional-grade, real-time scanning and alert dispatch system designed for US Stock Markets (NASDAQ, NYSE, AMEX). The system detects high-momentum and breakout stocks, runs them through strict Shariah compliance filters (activity screens and financial ratio checks), evaluates their setup using a comprehensive scoring system, and alerts users via Telegram channel updates and direct bot messages.

---

## Technical Stack
- **Backend Core**: Python 3.12+ / FastAPI / AsyncIO
- **Telegram Interface**: Aiogram 3.x (with FSM state management)
- **Database & Cache**: PostgreSQL / Redis / SQLAlchemy / Alembic
- **Task Orchestration**: APScheduler / Async background loop workers
- **Deployment**: Docker / Docker Compose / Nginx Reverse Proxy
- **Quality Assurance**: Pytest / Black / Ruff / MyPy

---

## Directory Structure
```text
mbm_radar/
├── app/                        # Main application package
│   ├── api/                    # FastAPI endpoints & routers
│   ├── bot/                    # Telegram bot handlers & middleware
│   ├── core/                   # Configurations and logging
│   ├── database/               # DB Session and database seeding
│   ├── filters/                # Shariah and stock scanners criteria
│   ├── indicators/             # Tech analysis indicators
│   ├── models/                 # SQLAlchemy models
│   ├── notifications/          # Message template formatting and dispatching
│   ├── scanner/                # Real-time WebSocket/REST aggregators
│   ├── scheduler/              # Expiry checks and scheduled cron scripts
│   ├── signals/                # scoring engine logic
│   └── utils/                  # Helper utilities
├── docker/                     # Dockerfile and Nginx configuration templates
├── docs/                       # Operational guides
├── tests/                      # Pytest unit and integration tests
├── pyproject.toml              # Dependency configuration file
├── docker-compose.yml          # Container coordination
└── .env                        # Local configurations
```

---

## Configuration Variables (.env)
Duplicate the `.env.example` template to `.env` and fill in the required API keys and credentials:
```bash
# --- Database Configuration ---
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/mbm_radar

# --- Redis Configuration ---
REDIS_URL=redis://redis:6379/0

# --- Telegram Configuration ---
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHANNEL_ID=-1001234567890

# --- API Keys for Stock Providers ---
FMP_API_KEY=your_fmp_api_key_here

# --- Active Providers configuration ---
ACTIVE_DATA_PROVIDER=FMP
```

---

## Running the Project

### Using Docker Compose (Production Ready)
The system is fully containerized and can be started with a single command:
```bash
docker compose up --build -d
```
This spawns:
1. `db`: PostgreSQL instance persisting to `postgres_data` volume.
2. `redis`: Redis server caching sent alerts and managing cooldown locks.
3. `app`: FastAPI service running the WebSocket server, scanner worker, scheduler, and Telegram bot listener.
4. `nginx`: Nginx proxy forwarding request to the FastAPI app and managing rate-limiting.

### Running Locally for Development
1. Install Python dependencies:
   ```bash
   poetry install
   ```
2. Start the local database and redis server (or connect to remote endpoints).
3. Initialize the database schema and seed data:
   ```bash
   python -m app.database.init_db
   ```
4. Run the development server:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

---

## Verification & Testing
Run the complete unit test suite using Pytest:
```bash
pytest tests/
```
