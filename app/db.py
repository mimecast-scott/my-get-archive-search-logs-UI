import json
import hashlib
from typing import Any, Iterable
import libsql

from .settings import settings


def connect_db():
    # libsql.connect can be local-only or an embedded replica that syncs from remote
    # (sync_url/auth_token optional). :contentReference[oaicite:4]{index=4}
    if settings.libsql_url and settings.libsql_auth_token:
        return libsql.connect(
            settings.db_path,
            sync_url=settings.libsql_url,
            auth_token=settings.libsql_auth_token,
        )
    return libsql.connect(settings.db_path)


def init_schema(conn) -> None:
    conn.execute("""
    CREATE TABLE IF NOT EXISTS search_logs (
      id TEXT PRIMARY KEY,
      create_time TEXT NOT NULL,
      email_addr TEXT NOT NULL,
      search_text TEXT,
      muse_query TEXT,
      description TEXT,
      search_reason TEXT,
      source TEXT,
      is_admin INTEGER,
      search_path TEXT,
      raw_json TEXT
    );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_search_logs_email_time ON search_logs(email_addr, create_time);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_search_logs_time ON search_logs(create_time);")

    conn.execute("""
    CREATE TABLE IF NOT EXISTS kv (
      k TEXT PRIMARY KEY,
      v TEXT
    );
    """)
    conn.commit()


def stable_log_id(log: dict[str, Any]) -> str:
    # Create a stable ID to dedupe across polling windows/pages
    parts = [
        str(log.get("emailAddr", "")).lower(),
        str(log.get("createTime", "")),
        str(log.get("searchText", "")),
        str(log.get("museQuery", "")),
        str(log.get("searchPath", "")),
    ]
    h = hashlib.sha256(("|".join(parts)).encode("utf-8")).hexdigest()
    return h


def upsert_logs(conn, logs: Iterable[dict[str, Any]]) -> int:
    inserted = 0
    for log in logs:
        _id = stable_log_id(log)
        raw = json.dumps(log, separators=(",", ":"), ensure_ascii=False)

        # INSERT OR IGNORE to keep it idempotent
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO search_logs
            (id, create_time, email_addr, search_text, muse_query, description, search_reason, source, is_admin, search_path, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                _id,
                log.get("createTime"),
                (log.get("emailAddr") or "").lower(),
                log.get("searchText"),
                log.get("museQuery"),
                log.get("description"),
                log.get("searchReason"),
                log.get("source"),
                1 if log.get("isAdmin") else 0,
                log.get("searchPath"),
                raw,
            ],
        )
        # libsql/sqlite cursor rowcount behaviour can vary; treat as best-effort
        if getattr(cur, "rowcount", 0) == 1:
            inserted += 1

    conn.commit()
    return inserted


def kv_get(conn, k: str) -> str | None:
    row = conn.execute("SELECT v FROM kv WHERE k = ?", [k]).fetchone()
    return row[0] if row else None


def kv_set(conn, k: str, v: str) -> None:
    conn.execute("INSERT INTO kv (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", [k, v])
    conn.commit()
