"""
SQLite persistence layer for Starr Menu Organiser.

Dual-mode:
  - Local dev:  standard sqlite3 with a file at data/menus.db
  - Production: Turso (hosted SQLite) via HTTP API

Menus are stored as JSON blobs (serialized Pydantic Restaurant models).
Set TURSO_DB_URL + TURSO_AUTH_TOKEN env vars to enable Turso mode.
"""

import json
import os
import sqlite3
import threading
import urllib.request
import urllib.error
from datetime import datetime, timezone

# Load .env for local dev (Turso credentials)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Also try Streamlit secrets as fallback
try:
    import streamlit as st
    _secrets = st.secrets
except Exception:
    _secrets = {}

TURSO_DB_URL = (
    os.getenv('TURSO_DB_URL', '')
    or _secrets.get('TURSO_DB_URL', '')
)
TURSO_AUTH_TOKEN = (
    os.getenv('TURSO_AUTH_TOKEN', '')
    or _secrets.get('TURSO_AUTH_TOKEN', '')
)
USE_TURSO = bool(TURSO_DB_URL)

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
DB_PATH = os.path.join(DB_DIR, 'menus.db')

_local = threading.local()


# ---------------------------------------------------------------------------
# Turso HTTP API client (no native deps)
# ---------------------------------------------------------------------------

def _turso_execute(sql: str, args: list | None = None) -> list[dict]:
    """Execute a query against Turso HTTP API. Returns rows as list of dicts."""
    db_url = TURSO_DB_URL.replace("libsql://", "https://")
    url = f"{db_url}/v3/pipeline"

    stmt = {"sql": sql}
    if args:
        stmt["args"] = [{"type": "text", "value": str(a)} for a in args]

    payload = {
        "requests": [
            {"type": "execute", "stmt": stmt},
            {"type": "close"},
        ]
    }

    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {TURSO_AUTH_TOKEN}",
            "Content-Type": "application/json",
        },
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())

    # Parse response — Turso returns "error" instead of "response" on failure
    resp_obj = data["results"][0]
    if "error" in resp_obj:
        raise RuntimeError(resp_obj["error"].get("message", str(resp_obj["error"])))
    result = resp_obj["response"]["result"]
    cols = [c["name"] for c in result["cols"]]
    rows = []
    for row in result["rows"]:
        record = {}
        for i, col in enumerate(cols):
            cell = row[i]
            if isinstance(cell, dict):
                if cell.get("type") == "null":
                    record[col] = None
                else:
                    record[col] = cell.get("value")
            else:
                record[col] = cell
        rows.append(record)
    return rows


# ---------------------------------------------------------------------------
# Local SQLite helpers
# ---------------------------------------------------------------------------

def _get_local_conn():
    conn = getattr(_local, 'conn', None)
    if conn is not None:
        return conn
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    _local.conn = conn
    return conn


def _local_query(sql: str, args: list | None = None) -> list[dict]:
    conn = _get_local_conn()
    cur = conn.execute(sql, args or [])
    if cur.description is None:
        conn.commit()
        return []
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _local_execute(sql: str, args: list | None = None):
    conn = _get_local_conn()
    conn.execute(sql, args or [])
    conn.commit()


# ---------------------------------------------------------------------------
# Unified query interface
# ---------------------------------------------------------------------------

def _query(sql: str, args: list | None = None) -> list[dict]:
    if USE_TURSO:
        return _turso_execute(sql, args)
    return _local_query(sql, args)


def _execute(sql: str, args: list | None = None):
    if USE_TURSO:
        _turso_execute(sql, args)
    else:
        _local_execute(sql, args)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def init_db():
    """Create menus table if it doesn't exist."""
    _execute("""
        CREATE TABLE IF NOT EXISTS menus (
            restaurant TEXT PRIMARY KEY,
            menu_json TEXT NOT NULL,
            push_data INTEGER DEFAULT 0,
            updated_at TEXT NOT NULL
        )
    """)
    # Migration: add menu_url column for live-site review feature
    try:
        _execute("ALTER TABLE menus ADD COLUMN menu_url TEXT")
    except Exception as e:
        # Ignore "column already exists" (SQLite: "duplicate column", Turso: similar)
        if "duplicate" in str(e).lower() or "already exists" in str(e).lower():
            pass
        else:
            raise


# ---------------------------------------------------------------------------
# Menu CRUD
# ---------------------------------------------------------------------------

def save_menu(restaurant_name, restaurant_model):
    """Save a parsed Restaurant model to the database as JSON."""
    now = datetime.now(timezone.utc).isoformat()
    menu_json = restaurant_model.model_dump_json()
    _execute("""
        INSERT INTO menus (restaurant, menu_json, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(restaurant) DO UPDATE SET
            menu_json = excluded.menu_json,
            updated_at = excluded.updated_at
    """, [restaurant_name, menu_json, now])


def load_menu(restaurant_name):
    """Load a Restaurant model from the database. Returns model or None."""
    from src.models import Restaurant

    rows = _query("SELECT menu_json FROM menus WHERE restaurant = ?", [restaurant_name])
    if rows and rows[0].get('menu_json'):
        return Restaurant.model_validate_json(rows[0]['menu_json'])
    return None


def list_menus():
    """Return list of dicts with restaurant, push_data, menu_url, updated_at."""
    return _query(
        "SELECT restaurant, push_data, menu_url, updated_at,"
        " json_array_length(menu_json, '$.tabs') as tab_count"
        " FROM menus ORDER BY restaurant"
    )


def delete_menu(restaurant_name):
    """Delete a menu from the database."""
    _execute("DELETE FROM menus WHERE restaurant = ?", [restaurant_name])


def set_push_data(restaurant_name, flag):
    """Set the push_data flag for a restaurant menu."""
    _execute("UPDATE menus SET push_data = ? WHERE restaurant = ?", [int(flag), restaurant_name])


def set_menu_url(restaurant_name, url):
    """Set the menu_url for a restaurant (used by live-site review)."""
    _execute("UPDATE menus SET menu_url = ? WHERE restaurant = ?", [url, restaurant_name])


# Initialize on import
init_db()
