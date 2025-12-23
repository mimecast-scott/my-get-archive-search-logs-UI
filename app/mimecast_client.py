import datetime as dt
import logging
from typing import List, Dict, Any, Optional

import httpx

from .settings import settings

logger = logging.getLogger("mimecast")

TOKEN_URL = "https://api.services.mimecast.com/oauth/token"
ARCHIVE_SEARCH_URL = "https://api.services.mimecast.com/api/archive/get-archive-search-logs"


# -------------------------------------------------
# OAuth
# -------------------------------------------------

async def get_access_token() -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_id": settings.mimecast_client_id,
                "client_secret": settings.mimecast_client_secret,
                "grant_type": "client_credentials",
            },
        )
        resp.raise_for_status()
        token = resp.json().get("access_token")
        if not token:
            raise RuntimeError("No access_token returned from Mimecast")
        return token


# -------------------------------------------------
# Fetch archive search logs (API 2.0 compliant)
# -------------------------------------------------

async def fetch_search_logs(
    start: dt.datetime,
    end: dt.datetime,
) -> List[Dict[str, Any]]:
    """
    Fetch ALL archive search logs between start and end.
    Handles API 2.0 pagination correctly using pageToken.
    """

    token = await get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    start_iso = start.isoformat().replace("+00:00", "Z")
    end_iso = end.isoformat().replace("+00:00", "Z")

    page_token: Optional[str] = None
    all_logs: List[Dict[str, Any]] = []
    page = 0
    total_count: Optional[int] = None

    async with httpx.AsyncClient(timeout=60) as client:
        while True:
            payload: Dict[str, Any] = {
                "meta": {
                    "pagination": {
                        "pageSize": settings.archive_page_size,
                    }
                },
                "data": [
                    {
                        "from": start_iso,
                        "to": end_iso,
                    }
                ],
            }

            if page_token:
                payload["meta"]["pagination"]["pageToken"] = page_token

            logger.info(
                "Mimecast request: %s → %s (pageToken=%s)",
                start_iso,
                end_iso,
                "set" if page_token else "none",
            )

            resp = await client.post(
                ARCHIVE_SEARCH_URL,
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()

            body = resp.json()

            page += 1

            pagination = body.get("meta", {}).get("pagination", {})
            page_token = pagination.get("next")

            if total_count is None:
                total_count = pagination.get("totalCount")

            data = body.get("data") or []
            logs = []
            if data and isinstance(data, list):
                logs = data[0].get("logs") or []

            all_logs.extend(logs)

            logger.info(
                "Fetched page %d: %d logs (total so far: %d%s)",
                page,
                len(logs),
                len(all_logs),
                f" / {total_count}" if total_count else "",
            )

            if not page_token:
                break

    return all_logs
