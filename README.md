# Mimecast Search Logs – FastAPI App

A lightweight FastAPI application that ingests **Mimecast Search Logs (API 2.0)**, stores them locally in SQLite, and provides a clean web UI to explore search activity by **user**, **day**, and **calendar view**.

Designed to be:
- Safe to restart
- Efficient with API usage
- Immediately available on startup
- Easy to validate and extend

---

## Features

### ✅ Ingestion & Polling
- OAuth 2.0 (client_credentials) authentication
- Initial backfill (once only)
- Delta polling on subsequent runs
- Overlap window to avoid missing delayed events
- Idempotent inserts (duplicates ignored)
- Background polling (UI is available immediately)

### ✅ Storage
- SQLite / libSQL compatible
- Simple schema
- Cursor tracking using key-value table
- Safe restarts and crash recovery

### ✅ Web UI
- Summary view by user
- Detailed per-user search history
- Calendar view showing searches per day
- Click a day to drill into searches grouped by user
- Tailwind CSS (no JS build step)

### ✅ APIs
- Health endpoint
- Search counts per day
- Easy validation of raw data in the database

---

## Architecture Overview

```
FastAPI
  ├── Background Poller (APScheduler)
  │     └── Mimecast Search Logs API (2.0)
  ├── SQLite (local or libSQL)
  ├── Jinja2 Templates (UI)
  └── REST Endpoints
```

### Polling Logic
- **First run**: backfills the last `N` days (configurable)
- **Subsequent runs**: polls only the delta since the last cursor
- **Overlap window** ensures no gaps due to API latency
- Cursor stored in DB (`kv` table)

---

## Requirements

- Python 3.11+
- Mimecast API 2.0 credentials
- Docker (optional but recommended)

---

## Environment Variables

Create a `.env` file:

```env
MIMECAST_CLIENT_ID=your_client_id
MIMECAST_CLIENT_SECRET=your_client_secret

# Optional overrides
INITIAL_BACKFILL_DAYS=30
POLL_SECONDS=3600
LOOKBACK_SECONDS=7200
DB_PATH=/data/searchlogs.db
```

---

## Running Locally

### 1️⃣ Install dependencies

```bash
pip install -r requirements.txt
```

### 2️⃣ Start the app

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 3️⃣ Open the UI

```
http://localhost:8000
```

---

## Running with Docker

```bash
docker compose up --build
```

The UI will be available immediately, while log ingestion runs in the background.

---

## Routes

### UI
| Route | Description |
|-----|------------|
| `/` | User summary |
| `/user/{email}` | User search detail |
| `/calendar` | Monthly calendar view |
| `/calendar/day/YYYY-MM-DD` | Searches for a specific day |

### API
| Route | Description |
|------|-------------|
| `/api/searches-per-day` | Search counts by day |
| `/health` | Health check |
| `/admin/reset-cursor` | Reset poll cursor (admin) |

---

## Database Schema (Simplified)

### `search_logs`
| Column | Description |
|------|-------------|
| create_time | Event timestamp (UTC) |
| email_addr | User email |
| source | Search source (archive, etc.) |
| search_text | Query string |
| search_reason | Reason / policy |
| description | Action description |

### `kv`
| Key | Purpose |
|----|---------|
| `last_polled_end_utc` | Cursor for delta polling |
| `bootstrap_done` | Indicates initial backfill completed |

---

## Why This Exists

Mimecast provides excellent audit data, but:
- Raw APIs are hard to explore manually
- UI access is limited
- Long-term historical analysis is awkward

This app gives:
- **Visibility** into search behaviour
- **Accountability** by user and day
- **A foundation** for further analytics or alerting

---

## Safety & Efficiency

- No destructive operations by default
- No blocking startup behaviour
- Restart-safe
- Duplicate-safe
- Low API overhead

---

## Ideas for Extension

- Authentication / RBAC
- Export to CSV
- Alerts for abnormal search behaviour
- Integration with SIEM
- ClickHouse or DuckDB backend
- Multi-tenant support

---

## License

MIT License  
Use it, fork it, extend it.

---

## Disclaimer

This project is **not affiliated with or endorsed by Mimecast**.  
Use of the Mimecast API is subject to Mimecast’s terms and conditions.
