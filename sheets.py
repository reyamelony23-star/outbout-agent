"""Google Sheets backend — used as the app's database.

Tabs:
    Users:     Email | Password Hash | Role | Name | Created At
    Prospects: Business Name | Address | Phone | Website | Email | Rating |
               Review Count | Lead Score | Search Query | Status |
               Deck Generated | Last Contacted | Owner Email | Notes
"""

from __future__ import annotations

from datetime import datetime, timezone

import hashlib
import json
import os
import time

import gspread

from config import (
    ADMIN_PASSWORD,
    GMAIL_ADDRESS,
    GOOGLE_SERVICE_ACCOUNT_FILE,
    GOOGLE_SHEETS_ID,
)

USERS_TAB = "Users"
PROSPECTS_TAB = "Prospects"

USERS_HEADERS = ["Email", "Password Hash", "Role", "Name", "Created At"]
PROSPECTS_HEADERS = [
    "Business Name",
    "Address",
    "Phone",
    "Website",
    "Email",
    "Rating",
    "Review Count",
    "Lead Score",
    "Search Query",
    "Status",
    "Deck Generated",
    "Last Contacted",
    "Owner Email",
    "Notes",
]

_client = None
_spreadsheet = None
_bootstrapped = False

PROSPECTS_CACHE_TTL = 60
USERS_CACHE_TTL = 300

_cache: dict[str, tuple[float, object]] = {}


def _cache_get(key: str, ttl: float):
    entry = _cache.get(key)
    if entry is None:
        return None
    timestamp, value = entry
    if time.time() - timestamp > ttl:
        return None
    return value


def _cache_set(key: str, value) -> None:
    _cache[key] = (time.time(), value)


def _cache_invalidate(key: str) -> None:
    _cache.pop(key, None)


def generate_password_hash(password):
    return hashlib.sha256(password.encode()).hexdigest()


def check_password_hash(hash, password):
    return hash == hashlib.sha256(password.encode()).hexdigest()


def _gspread_client():
    global _client
    if _client is None:
        creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if creds_json:
            creds_dict = json.loads(creds_json)
            _client = gspread.service_account_from_dict(creds_dict)
        else:
            _client = gspread.service_account(filename=GOOGLE_SERVICE_ACCOUNT_FILE)
    return _client


def _spreadsheet_handle():
    global _spreadsheet
    if _spreadsheet is None:
        _spreadsheet = _gspread_client().open_by_key(GOOGLE_SHEETS_ID)
    return _spreadsheet


def _get_or_create_tab(name: str, headers: list[str]):
    ss = _spreadsheet_handle()
    try:
        ws = ss.worksheet(name)
    except gspread.WorksheetNotFound:
        try:
            ws = ss.add_worksheet(title=name, rows=1000, cols=max(len(headers), 10))
        except Exception:
            ws = ss.worksheet(name)
        else:
            ws.append_row(headers, value_input_option="USER_ENTERED")
            return ws
    if not ws.row_values(1):
        ws.append_row(headers, value_input_option="USER_ENTERED")
    return ws


def users_tab():
    return _get_or_create_tab(USERS_TAB, USERS_HEADERS)


def prospects_tab():
    return _get_or_create_tab(PROSPECTS_TAB, PROSPECTS_HEADERS)


def ensure_bootstrap():
    """Run once per process — ensure tabs exist and an admin user exists."""
    global _bootstrapped
    if _bootstrapped:
        return
    users_tab()
    prospects_tab()
    if not list_users():
        if not GMAIL_ADDRESS:
            print("[bootstrap] GMAIL_ADDRESS empty; cannot auto-create admin user")
        else:
            create_user(
                email=GMAIL_ADDRESS,
                password=ADMIN_PASSWORD,
                role="admin",
                name="Admin",
            )
            print(
                f"[bootstrap] Created admin user: {GMAIL_ADDRESS} "
                f"(password from ADMIN_PASSWORD env var)"
            )
    _bootstrapped = True


def list_users() -> list[dict]:
    cached = _cache_get("users", USERS_CACHE_TTL)
    if cached is not None:
        return cached
    ws = users_tab()
    users = ws.get_all_records()
    _cache_set("users", users)
    return users


def find_user(email: str) -> dict | None:
    email = email.strip().lower()
    for u in list_users():
        if str(u.get("Email", "")).strip().lower() == email:
            return u
    return None


def verify_password(email: str, password: str) -> dict | None:
    user = find_user(email)
    if not user:
        return None
    if check_password_hash(user.get("Password Hash", ""), password):
        return user
    return None


def create_user(email: str, password: str, role: str = "client", name: str = "") -> None:
    ws = users_tab()
    ws.append_row(
        [
            email.strip().lower(),
            generate_password_hash(password),
            role,
            name,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ],
        value_input_option="USER_ENTERED",
    )
    _cache_invalidate("users")


def list_prospects(owner_email: str | None = None) -> list[dict]:
    all_rows = _cache_get("prospects", PROSPECTS_CACHE_TTL)
    if all_rows is None:
        ws = prospects_tab()
        rows = ws.get_all_records()
        all_rows = []
        for i, row in enumerate(rows, start=2):
            row["_row"] = i
            all_rows.append(row)
        _cache_set("prospects", all_rows)
    if not owner_email:
        return list(all_rows)
    target = owner_email.strip().lower()
    return [r for r in all_rows if str(r.get("Owner Email", "")).strip().lower() == target]


def find_prospect_by_name(name: str, owner_email: str | None = None) -> dict | None:
    target = name.strip().lower()
    for p in list_prospects(owner_email=owner_email):
        if str(p.get("Business Name", "")).strip().lower() == target:
            return p
    return None


def existing_prospect_names(owner_email: str | None = None) -> set[str]:
    return {
        str(p.get("Business Name", "")).strip().lower()
        for p in list_prospects(owner_email=owner_email)
        if p.get("Business Name")
    }


def append_prospects(prospects: list[dict], owner_email: str) -> tuple[int, int]:
    """Append new prospect dicts. Returns (added, skipped_dupes)."""
    ws = prospects_tab()
    seen = existing_prospect_names()
    added = 0
    skipped = 0
    rows_to_add = []
    for p in prospects:
        name = (p.get("name") or "").strip()
        if not name or name.lower() in seen:
            skipped += 1
            continue
        seen.add(name.lower())
        rows_to_add.append(
            [
                name,
                p.get("address", ""),
                p.get("phone", ""),
                p.get("website", ""),
                p.get("email", ""),
                p.get("rating", ""),
                p.get("review_count", 0),
                p.get("lead_score", 0),
                p.get("query", ""),
                "New",
                "",
                "",
                owner_email,
                "",
            ]
        )
        added += 1
    if rows_to_add:
        ws.append_rows(rows_to_add, value_input_option="USER_ENTERED")
        _cache_invalidate("prospects")
    return added, skipped


def update_prospect(row_index: int, fields: dict) -> None:
    """Patch specific columns on a prospect row (1-based row_index, header is row 1)."""
    ws = prospects_tab()
    updates = []
    for key, value in fields.items():
        try:
            col = PROSPECTS_HEADERS.index(key) + 1
        except ValueError:
            continue
        if key == "Deck Generated":
            print(f"[sheets] writing deck URL to column {col} ({gspread.utils.rowcol_to_a1(row_index, col)})")
        updates.append({"range": gspread.utils.rowcol_to_a1(row_index, col), "values": [[value]]})
    if updates:
        ws.batch_update(updates, value_input_option="USER_ENTERED")
        _cache_invalidate("prospects")


def stats(owner_email: str | None = None) -> dict:
    rows = list_prospects(owner_email=owner_email)
    total = len(rows)
    emails_sent = sum(1 for r in rows if str(r.get("Status", "")).lower() in {"contacted", "replied"})
    decks_generated = sum(1 for r in rows if r.get("Deck Generated"))
    replied = sum(1 for r in rows if str(r.get("Status", "")).lower() == "replied")
    response_rate = (replied / emails_sent * 100) if emails_sent else 0.0
    return {
        "total_prospects": total,
        "emails_sent": emails_sent,
        "decks_generated": decks_generated,
        "response_rate": round(response_rate, 1),
    }
