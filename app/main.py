import asyncio
import datetime as dt
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .settings import settings
from .db import connect_db, init_schema, kv_get, kv_set, upsert_logs
from .mimecast_client import fetch_search_logs


# -------------------------------------------------------------------
# App setup
# -------------------------------------------------------------------

app = FastAPI(title="Mimecast Search Logs (API 2.0)")
templates = Jinja2Templates(directory="app/templates")
scheduler = AsyncIOScheduler()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mimecast")

LAST_POLLED_KEY = "last_polled_end_utc"
BOOTSTRAP_DONE_KEY = "bootstrap_completed"


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_iso(ts: str) -> dt.datetime:
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


# -------------------------------------------------------------------
# Polling logic
# -------------------------------------------------------------------

async def poll_once():
    conn = connect_db()
    init_schema(conn)

    now = utcnow()
    last = kv_get(conn, LAST_POLLED_KEY)
    bootstrapped = kv_get(conn, BOOTSTRAP_DONE_KEY)

    if not bootstrapped:
        start = now - dt.timedelta(days=settings.initial_backfill_days)
        logger.info(
            "Initial startup backfill: last %d days (from %s)",
            settings.initial_backfill_days,
            start,
        )
    else:
        if last:
            start = parse_iso(last) - dt.timedelta(seconds=settings.lookback_seconds)
        else:
            start = now - dt.timedelta(seconds=settings.lookback_seconds)

        logger.info("Delta poll from cursor: %s", start)

    end = now

    logs = await fetch_search_logs(start=start, end=end)
    inserted = upsert_logs(conn, logs)

    kv_set(conn, LAST_POLLED_KEY, end.isoformat().replace("+00:00", "Z"))
    kv_set(conn, BOOTSTRAP_DONE_KEY, "1")

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "fetched": len(logs),
        "inserted": inserted,
    }


# -------------------------------------------------------------------
# Startup (NON-BLOCKING)
# -------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    logger.info("Application startup: initialising DB and scheduler")

    conn = connect_db()
    init_schema(conn)

    # Start scheduler immediately (UI becomes available)
    scheduler.add_job(
        poll_once,
        "interval",
        seconds=settings.poll_seconds,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info("Scheduler started (interval=%ss)", settings.poll_seconds)

    # Fire-and-forget initial poll
    async def initial_poll():
        try:
            result = await poll_once()
            logger.info("Initial background poll completed: %s", result)
        except Exception:
            logger.exception("Initial background poll FAILED")

    asyncio.create_task(initial_poll())


# -------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index(request: Request, days: int | None = None):
    days = days or settings.default_days
    since = (utcnow() - dt.timedelta(days=days)).isoformat()

    conn = connect_db()
    rows = conn.execute(
        """
        SELECT email_addr, COUNT(*) AS cnt
        FROM search_logs
        WHERE create_time >= ?
        GROUP BY email_addr
        ORDER BY cnt DESC
        """,
        [since],
    ).fetchall()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "rows": [{"email": r[0], "count": r[1]} for r in rows],
            "days": days,
        },
    )


@app.post("/admin/reset-cursor")
def reset_cursor():
    conn = connect_db()
    init_schema(conn)
    conn.execute(
        "DELETE FROM kv WHERE k IN (?, ?)",
        [LAST_POLLED_KEY, BOOTSTRAP_DONE_KEY],
    )
    conn.commit()
    return {"status": "ok", "message": "Cursor + bootstrap reset"}


@app.get("/user/{email}", response_class=HTMLResponse)
def user_detail(request: Request, email: str, days: int | None = None):
    days = days or settings.default_days
    since = (utcnow() - dt.timedelta(days=days)).isoformat()

    conn = connect_db()
    rows = conn.execute(
        """
        SELECT
            create_time,
            email_addr,
            source,
            search_text,
            search_reason,
            description
        FROM search_logs
        WHERE email_addr = ?
          AND create_time >= ?
        ORDER BY create_time DESC
        """,
        [email.lower(), since],
    ).fetchall()

    rows = [
        {
            "create_time": r[0],
            "email_addr": r[1],
            "source": r[2],
            "search_text": r[3],
            "search_reason": r[4],
            "description": r[5],
        }
        for r in rows
    ]

    return templates.TemplateResponse(
        "user.html",
        {
            "request": request,
            "email": email,
            "rows": rows,
            "days": days,
        },
    )


@app.get("/calendar", response_class=HTMLResponse)
def calendar_view(request: Request):
    return templates.TemplateResponse(
        "calendar.html",
        {"request": request},
    )


@app.get("/api/searches-per-day")
def searches_per_day(year: int | None = None, month: int | None = None):
    now = utcnow()
    year = year or now.year
    month = month or now.month

    start = dt.datetime(year, month, 1, tzinfo=dt.timezone.utc)
    if month == 12:
        end = dt.datetime(year + 1, 1, 1, tzinfo=dt.timezone.utc)
    else:
        end = dt.datetime(year, month + 1, 1, tzinfo=dt.timezone.utc)

    conn = connect_db()
    rows = conn.execute(
        """
        SELECT substr(create_time, 1, 10) AS day, COUNT(*)
        FROM search_logs
        WHERE create_time >= ?
          AND create_time < ?
        GROUP BY day
        ORDER BY day
        """,
        [start.isoformat(), end.isoformat()],
    ).fetchall()

    return {
        "year": year,
        "month": month,
        "days": [{"date": r[0], "count": r[1]} for r in rows],
    }


@app.get("/api/searches-by-day")
def searches_by_day(date: str):
    conn = connect_db()

    start = f"{date}T00:00:00"
    end = f"{date}T23:59:59"

    rows = conn.execute(
        """
        SELECT
          email_addr,
          create_time,
          source,
          search_text,
          search_reason,
          description
        FROM search_logs
        WHERE create_time >= ?
          AND create_time <= ?
        ORDER BY email_addr, create_time DESC
        """,
        [start, end],
    ).fetchall()

    grouped = {}
    for r in rows:
        grouped.setdefault(r[0], []).append({
            "create_time": r[1],
            "source": r[2],
            "search_text": r[3],
            "search_reason": r[4],
            "description": r[5],
        })

    return {
        "date": date,
        "users": [
            {"email": email, "count": len(entries), "entries": entries}
            for email, entries in grouped.items()
        ],
    }


@app.get("/day/{date}", response_class=HTMLResponse)
def day_view(request: Request, date: str):
    return templates.TemplateResponse(
        "day.html",
        {"request": request, "date": date},
    )


@app.get("/health")
def health():
    return {"ok": True}
