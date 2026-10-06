# AeroMind — PX4 Drone Command, Telemetry & Analytics Platform

AeroMind is an isolated application layer for PX4 operations. It provides a responsive React dashboard, an asynchronous FastAPI/MAVSDK bridge, SQLite/PostgreSQL persistence, mission planning, guarded vehicle commands, telemetry WebSockets and explainable anomaly analytics. It does **not** replace or patch PX4 flight-control code.

> **Repository inspection / PX4 boundary:** the checked-out repository at the start of this work contained only its original `README.md`; it is not a `PX4-Autopilot` source checkout. There were no PX4 version tags, SITL targets, Gazebo files, MAVLink message definitions or simulator workflows to inspect in-tree. Accordingly, all application code is under the new `drone-ai-platform/` directory. No PX4 source was copied, modified or replaced. When a separate PX4 checkout is available, the included read-only inspection scripts report its revision, message files, simulator directories and targets before the launch helper chooses a target. The documented modern Gazebo example is `make px4_sitl gz_x500`; verify it against the **actual** checkout with the helper rather than assuming it exists. See the official [PX4 simulation](https://docs.px4.io/main/en/simulation/), [Gazebo](https://docs.px4.io/main/en/sim_gazebo_gz/) and [MAVSDK Python](https://mavsdk.mavlink.io/main/en/python/) documentation.

## Architecture

```text
PX4 SITL / MAVLink UDP
          │  MAVSDK-Python (async reconnecting supervisor)
          ▼
FastAPI ── telemetry hub ── WebSocket /ws/telemetry + REST /api/*
          │                         │
          │ SQLAlchemy              └── React 18 + Vite + Tailwind 4
          ▼                              Leaflet maps · Recharts
SQLite (local) / PostgreSQL (deploy)
```

- **Frontend:** React + TypeScript, Vite, Tailwind CSS, Leaflet/OpenStreetMap, Recharts and Lucide. Pages: Overview, Live Flight, Mission Planner, Telemetry, Drone Health, AI Analytics, Flight Logs, Alerts Center, Settings and System Status. The UI includes mobile navigation, loading/empty/error states, a visible simulated-data banner, command confirmations and WebSocket reconnect with REST fallback.
- **Backend:** FastAPI, Pydantic v2, async SQLAlchemy, MAVSDK-Python 2.x and a single telemetry hub that fans out snapshots to bounded WebSocket subscriber queues. The MAVSDK supervisor reconnects with capped backoff after SITL restarts. Analytics run off the event loop so estimator/model work does not stall REST or telemetry I/O.
- **Storage:** `users`, `drones`, `telemetry_records`, `missions`, `waypoints`, `flights`, `alerts` and `system_events` tables. SQLite is the local default; PostgreSQL/asyncpg is supported. Alembic migration configuration and the initial schema revision are included.
- **Authentication:** Argon2 password hashing, short-lived JWT bearer access tokens, one-use short-lived WebSocket tickets, operator/admin roles and optional admin bootstrap through environment variables. Self-registration only creates an `operator`.
- **PX4 boundary:** MAVLink telemetry, mission upload and actions are sent through MAVSDK; there are no direct writes to PX4 source. PX4 remains responsible for flight control, arming checks, failsafes and geofence enforcement.

## Prerequisites

- Python 3.11 or later (3.12 recommended for containers).
- Node.js 22 LTS and npm.
- For real PX4 SITL: a separate PX4-Autopilot checkout and its supported Linux build toolchain. Follow the PX4 documentation for the version in that checkout; Gazebo is not bundled with AeroMind.
- Docker Compose is optional. It was not available in the implementation environment, so the Compose stack is provided but was not executed here.

## Quick start — Linux / macOS

From the repository root:

```bash
cd drone-ai-platform
cp .env.example .env
./scripts/install.sh
```

For local development, `SECRET_KEY` may remain blank: the backend creates a random development-only signing key at startup. Tokens will be invalidated when that process restarts. **Set a unique secret of at least 32 characters for shared or production deployments.** Do not commit `.env`.

Start each process in a separate terminal:

```bash
cd drone-ai-platform
./scripts/start-backend.sh
```

```bash
cd drone-ai-platform
./scripts/start-frontend.sh
```

Open **http://localhost:5173**, choose **Create an account**, and register an operator. No default users or demo passwords are seeded. FastAPI docs are at **http://localhost:8000/docs** and the public health check is **http://localhost:8000/health**.

The default `TELEMETRY_MODE=mock` starts clearly labeled simulated telemetry so the dashboard, maps, charts, storage, WebSocket and analytics can be demonstrated without a simulator. Vehicle controls and mission upload are deliberately rejected in mock/offline mode. Mock values must never be treated as aircraft telemetry.

## Windows PowerShell

PX4's supported build workflow is Linux-based; for SITL on Windows use WSL2 with the PX4-supported Ubuntu toolchain. The application itself can run in PowerShell.

```powershell
cd .\drone-ai-platform
Copy-Item .env.example .env
.\scripts\install.ps1
```

Optional: persist a local signing key in `.env` (do not use a shared or production key in source control):

```powershell
$secret = & .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
(Get-Content .env) -replace '^SECRET_KEY=.*$', "SECRET_KEY=$secret" | Set-Content .env
```

Use two PowerShell terminals:

```powershell
cd .\drone-ai-platform
.\scripts\start-backend.ps1
```

```powershell
cd .\drone-ai-platform
.\scripts\start-frontend.ps1
```

Then browse to **http://localhost:5173** and register an operator. PowerShell PX4 inspection / launch helpers are also provided:

```powershell
$env:PX4_DIR = 'C:\src\PX4-Autopilot'
.\scripts\inspect-px4.ps1 -Px4Dir $env:PX4_DIR
$env:PX4_SITL_TARGET = 'gz_x500'  # optional; leave unset to choose a detected target
.\scripts\start-px4-sitl.ps1 -Px4Dir $env:PX4_DIR
```

Run those PX4 helpers inside a PX4-supported Linux/WSL2 environment. If the backend runs on Windows while SITL runs in WSL2, configure the MAVLink destination/interface so UDP reaches the backend host; `udp://:14540` only works when the SITL network is forwarding to the listener. For the least network friction, run PX4 SITL and the backend in the same Linux/WSL2 environment and open the forwarded Vite port in the Windows browser.

## Connect to an existing PX4 SITL checkout

First inspect the actual PX4 tree (the current AeroMind checkout does not contain one):

```bash
cd drone-ai-platform
PX4_DIR="$HOME/src/PX4-Autopilot" ./scripts/inspect-px4.sh
```

The script prints `git describe`, target and simulator directories, a sample/count of `.msg` definitions, Gazebo executables and the output from `make px4_sitl list_vmd_make_targets`. It does not build or modify PX4. To start a target reported by that checkout:

```bash
export PX4_DIR="$HOME/src/PX4-Autopilot"
# Optional override if the helper cannot infer a target from the target list:
export PX4_SITL_TARGET=gz_x500
./scripts/start-px4-sitl.sh
```

PX4's current documentation gives `make px4_sitl gz_x500` as a Gazebo example, but installed simulators, vehicle targets and prerequisites vary by PX4 revision. The launcher checks the target list and prefers a detected `gz_x500`, otherwise a detected `gazebo-classic_iris`; if neither is reported it exits with the discovered targets and asks for `PX4_SITL_TARGET` rather than guessing. Gazebo setup and PX4 build prerequisites must be installed separately following the version-specific [PX4 developer setup](https://docs.px4.io/main/en/dev_setup/) instructions.

In `drone-ai-platform/.env`, set:

```dotenv
TELEMETRY_MODE=px4
PX4_SYSTEM_ADDRESS=udp://:14540
MAVSDK_SERVER_ADDRESS=127.0.0.1
MAVSDK_SERVER_PORT=50051
```

Restart the backend after changing environment values. MAVSDK-Python binds the configured UDP endpoint and exposes PX4 telemetry/actions. Make sure the PX4 SITL MAVLink instance sends to the backend's reachable UDP port and that host firewalls / WSL / Docker networking permit it. **The correct destination is network-layout-specific.** `14540/udp` is the common local MAVSDK PX4 SITL endpoint; it is not a substitute for checking the actual PX4 MAVLink configuration. The backend reports `PX4 unavailable; reconnecting` and retries automatically if the simulator is not running yet or restarts later.

## Docker Compose

The Compose stack runs PostgreSQL, FastAPI and the static Nginx/Vite frontend. PX4 itself remains external. Prepare local secrets before launching:

```bash
cd drone-ai-platform
cp .env.example .env
# Generate values locally, then copy them into .env (hex is URL-safe for the Compose DSN):
python3 -c 'import secrets; print("SECRET_KEY=" + secrets.token_urlsafe(48)); print("POSTGRES_PASSWORD=" + secrets.token_hex(32))'
# For a production-like deployment, also set APP_ENV=production,
# ALLOW_REGISTRATION=false and configure an admin bootstrap account securely.
docker compose up --build
```

Open **http://localhost:5173**. Compose maps API/WebSocket traffic through Nginx to FastAPI, and exposes `14540/udp` for an externally configured SITL stream. For production schema management, set `AUTO_CREATE_SCHEMA=false`, apply migrations before starting the web service, and keep the database volume backed up:

```bash
docker compose run --rm backend alembic upgrade head
docker compose up -d
```

Use a URL-safe PostgreSQL password when interpolating `DATABASE_URL` in Compose (or provide an encoded DSN through your deployment secret manager). Restrict published ports, configure TLS at a reverse proxy, set a specific `CORS_ORIGINS` allowlist, disable public registration and provision credentials out-of-band before real operations. Compose defaults are intended for a local demo, not a hardened public deployment.

## Configuration

See [`drone-ai-platform/.env.example`](drone-ai-platform/.env.example). Important variables:

| Variable | Purpose |
|---|---|
| `APP_ENV` | `development`, `test` or `production`. Production requires `SECRET_KEY` (32+ characters). |
| `SECRET_KEY` | JWT signing secret. Random ephemeral fallback is development-only. |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/aeromind.db` locally, or `postgresql+asyncpg://...` for PostgreSQL. |
| `AUTO_CREATE_SCHEMA` | Create tables on startup for local development. Use Alembic explicitly for production. |
| `CORS_ORIGINS` | Comma-separated allowed browser origins. Vite proxies `/api` and `/ws` in development. |
| `VITE_BACKEND_TARGET` | Optional server-side Vite proxy target (default `http://127.0.0.1:8000`); browser requests remain same-origin. |
| `ALLOW_REGISTRATION` | Public account registration switch; disable after provisioning production users. |
| `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_PASSWORD` | Optional first-start administrator creation. Set both; password must be at least 12 characters. No account is created when blank. |
| `TELEMETRY_MODE` | `mock` (demo), `px4` (MAVSDK) or `disabled`. |
| `PX4_SYSTEM_ADDRESS` | MAVSDK system address, commonly `udp://:14540` for local SITL. |
| `MAVSDK_SERVER_ADDRESS`, `MAVSDK_SERVER_PORT` | MAVSDK gRPC server endpoint; defaults to `127.0.0.1:50051`. |
| `PX4_CONNECT_TIMEOUT_S`, `RECONNECT_BACKOFF_MAX_S` | Connection timeout and bounded reconnect delay. |
| `MOCK_TICK_SECONDS`, `TELEMETRY_PERSIST_INTERVAL_S` | Demo sample cadence and database write interval. |
| `SAFE_MAX_ALTITUDE_M`, `SAFE_MAX_SPEED_M_S`, `MAX_MISSION_WAYPOINTS` | Backend-side advisory/validation limits. Configure for local operating rules; PX4 remains authoritative. |

## Authentication and roles

- `POST /api/auth/register` and `POST /api/auth/login` accept JSON `{ "email": "...", "password": "..." }` and return a JWT. Passwords are Argon2-hashed. Public registration, when enabled, creates the `operator` role only.
- Send `Authorization: Bearer <access_token>` to protected REST routes. `GET /api/auth/me` returns the active account.
- Configure `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD` before first start to create an administrator. Never put a production password in Git or chat. Set `ALLOW_REGISTRATION=false` after provisioning.
- The browser obtains a one-use short-lived ticket with `POST /api/auth/ws-ticket`; that ticket, not the long-lived JWT, is used for the WebSocket handshake. Tickets expire and are consumed once.
- Operators and admins may use operational APIs. Mission records are scoped to their owner; admins can manage all missions. Add organization-specific RBAC/tenant isolation before sharing one deployment across independent fleets.

## Telemetry and WebSocket flow

MAVSDK subscription tasks normalize position, attitude/heading, NED ground speed, battery, GNSS, health, flight mode, arming/in-air state and home position into a shared snapshot. Fixed-wing airspeed is collected when the MAVSDK stream provides it. CPU load, link quality and other vehicle-specific values remain `null` if not reported; the UI does not invent those measurements. `distance_from_home_m` is calculated from GPS/home coordinates. Telemetry snapshots are persisted at the configured interval and broadcast through bounded subscriber queues so a slow browser cannot block MAVSDK.

`GET /api/telemetry/latest` provides a snapshot; `/api/telemetry/history` reads stored records. `/ws/telemetry` sends:

```json
{"type":"telemetry","data":{"source":"px4","connected":true}}
{"type":"heartbeat","timestamp":"2026-10-06T00:00:00+00:00"}
```

The frontend reconnects with capped backoff and polls the snapshot endpoint every three seconds while the stream is unavailable. Stored samples hydrate the map/chart history when a browser first connects. In `mock` mode `source` is always `mock`, the interface displays a **SIMULATED** label and all real-vehicle actions remain locked.

## Missions and safe control

Missions are saved as drafts with ordered waypoints (latitude, longitude, altitude relative to home and hold time). The browser validates basic values and the backend revalidates mission size, coordinates, altitude, upload length, vehicle connection and state. Upload requires an actual `px4` MAVSDK connection and a disarmed, grounded vehicle with estimator/global/home position available. `MissionRaw` encodes waypoint hold time as MAVLink `MAV_CMD_NAV_WAYPOINT` `param1`; the route is uploaded but **not started automatically**. Review the uploaded plan in the ground-control application before launching it.

Every command requires an explicit browser confirmation and is validated again server-side. Commands are never sent when the configured mode is not `px4`, the telemetry link is down, or MAVSDK is not ready. Arming requires healthy estimator/global position, home, adequate GNSS and at least 20% reported battery. Takeoff altitude is checked against the configured limit. Disarm is blocked while airborne; hold/land require an armed airborne vehicle; RTL requires an armed vehicle. The supported mode selector is limited to `HOLD`, `LAND` and `RETURN_TO_LAUNCH`. These software checks supplement — never replace — PX4 preflight checks, failsafes, local law, a safety pilot and a vehicle-specific operating procedure.

## Analytics, alerts and flight history

The analytics service combines explicit rules with NumPy/Pandas feature processing and a rolling scikit-learn `IsolationForest`. It checks altitude/speed limits, low battery, GPS satellite quality and implausible position jumps, estimator health, sensor calibration and contextual telemetry outliers. Scores are 0–100, alerts include severity/category/reason, and recommendations are rule-mapped and inspectable. Findings are persisted to the Alerts Center with acknowledgement metadata; repeated identical findings are rate-limited in the local telemetry process. This is **decision support**, not a certified safety system or a substitute for a qualified operator.

Flights are summarized from in-air telemetry transitions. Flight Logs displays history and stored telemetry samples; operators can select flight rows and telemetry rows for authenticated CSV export. Downloads use the Authorization header rather than putting the access token into a URL. Current-session track and persisted telemetry history are available to the map and charts.

## API reference

Interactive OpenAPI documentation is served at `/docs` (ReDoc at `/redoc`). Protected endpoints require a bearer token unless noted.

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/auth/register` | Register operator (public when enabled). |
| `POST` | `/api/auth/login` | Issue access token. |
| `GET` | `/api/auth/me` | Current user. |
| `POST` | `/api/auth/ws-ticket` | Issue one-use WebSocket ticket. |
| `GET` | `/api/drone/status` | Current vehicle and control status. |
| `POST` | `/api/drone/connect` | Request a PX4 reconnect attempt. |
| `POST` | `/api/drone/command` | Guarded arm/disarm/takeoff/land/RTL/hold/mode request. |
| `GET` | `/api/telemetry/latest` | Latest normalized snapshot. |
| `GET` | `/api/telemetry/history` | Persisted telemetry (`limit`, optional `since`). |
| `GET` | `/api/telemetry/export.csv` | Telemetry CSV (`limit` or selected record `ids`). |
| `GET`, `POST` | `/api/missions` | List and create mission drafts. |
| `GET`, `PUT`, `DELETE` | `/api/missions/{id}` | Read, replace/reorder waypoints, or delete. |
| `POST` | `/api/missions/{id}/upload` | Validate and upload mission to PX4. |
| `GET` | `/api/flights` | Flight summaries. |
| `GET` | `/api/flights/export.csv` | Flight CSV (`limit` or selected `ids`). |
| `GET` | `/api/analytics/summary` | Risk, health, alert and timeline summary. |
| `GET` | `/api/alerts` | Alert history/filtering. |
| `POST` | `/api/alerts/{id}/acknowledge` | Acknowledge an alert. |
| `GET` | `/api/system/status` | API/database/PX4/MAVSDK/WebSocket status. |
| `GET` | `/api/system/events` | Recent connection/command events. |
| `WS` | `/ws/telemetry?ticket=...` | Ticket-authenticated real-time telemetry. |
| `GET` | `/health` | Public liveness endpoint. |

## Database migrations

Development can use `AUTO_CREATE_SCHEMA=true`. For a persistent or production database, use Alembic:

```bash
cd drone-ai-platform/backend
# Set DATABASE_URL in the environment or ../.env first.
../.venv/bin/alembic upgrade head
```

PowerShell:

```powershell
Set-Location .\drone-ai-platform\backend
..\.venv\Scripts\python.exe -m alembic upgrade head
```

For future model changes, generate and review migrations (`alembic revision --autogenerate -m "describe change"`) and apply them deliberately. Do not use automatic schema creation as a substitute for reviewed production migrations.

## Tests and checks

```bash
cd drone-ai-platform/backend
../.venv/bin/pytest -q
../.venv/bin/ruff check app tests migrations
```

```bash
cd drone-ai-platform/frontend
npm test -- --reporter=dot
npm run build    # includes strict TypeScript checking
npm audit
```

The backend suite covers hashing/JWT, safe command validation, mission validation/reordering, telemetry analytics including GPS and IsolationForest outliers, MAVSDK field normalization, authenticated REST, database persistence and authenticated WebSocket streaming. Frontend component tests run in Vitest. Real PX4 SITL / Gazebo was not present in this checkout, so physical simulator connection, mission upload and command execution must be verified in a separate PX4 environment before operational use.

## Troubleshooting

- **PX4 cannot connect:** confirm `TELEMETRY_MODE=px4`, inspect the actual PX4 checkout/target, verify UDP destination and firewall, and ensure `PX4_SYSTEM_ADDRESS` matches the MAVLink instance. Check `MAVSDK_SERVER_ADDRESS`/port `50051` and backend JSON logs. Mock data is intentionally not a substitute for a missing PX4 link.
- **SITL launcher says no recognized target:** use `inspect-px4.sh` / `inspect-px4.ps1`, then set `PX4_SITL_TARGET` to a target the installed checkout actually lists.
- **Gazebo command is missing:** install the simulator version supported by that PX4 branch; this application package does not install or start Gazebo unless the SITL script is run.
- **WebSocket closes with 4401:** the one-use ticket was missing, expired or already consumed. The frontend obtains a fresh ticket and reconnects automatically; make sure the reverse proxy forwards `/ws/` with Upgrade headers.
- **Dashboard shows HTTP fallback:** verify FastAPI is on port 8000 and Vite's server-side proxy points to it. Browser code uses relative `/api` and `/ws` paths; it does not call a browser-side `localhost` backend.
- **Arming/mission upload rejected:** inspect current `ekf_ok`, global/home position, GPS satellites, battery, armed/in-air state and backend safety envelope. A rejected request is intentional; resolve the vehicle preflight issue in PX4/QGroundControl.
- **PowerShell / Windows SITL:** use WSL2 Ubuntu for PX4's Linux toolchain and configure UDP routing between WSL and the backend. The PowerShell scripts are convenience wrappers, not a native PX4 Windows toolchain.
- **Database:** check `DATABASE_URL`, `AUTO_CREATE_SCHEMA`, migrations and write permissions to `backend/data`. SQLite is for local development; use PostgreSQL for a shared deployment and maintain backups.

## Project layout

```text
drone-ai-platform/
  backend/app/{api,core,repositories,services}/  FastAPI, auth, DB and MAVSDK services
  backend/tests/                               Unit and integration tests
  backend/migrations/                          Alembic environment and revisions
  frontend/src/{components,pages,hooks,services}/ React application
  scripts/                                     Linux/macOS + PowerShell setup/SITL helpers
  backend/Dockerfile  frontend/Dockerfile  docker-compose.yml
```
