"""
VisaHoBe OS - Dual-mode storage layer
------------------------------------
- CLOUD MODE (default when SUPABASE_URL + SUPABASE_SERVICE_KEY are set):
    all collections live in a Supabase Postgres table `app_data`
    (key TEXT PK, value JSONB, updated_at timestamptz).
    Server-side only: service key never reaches the browser.
    On first cloud start, existing local data/*.json collections are
    uploaded automatically (one-time migration, cloud wins if row exists).
- LOCAL MODE (no env): identical to the old behaviour (data/*.json files).

load(name) / save(name, data) keep the exact same signatures used by app.py.
"""
import os
import json
import requests

SB_URL = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
SB_KEY = (os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY") or "").strip()
CLOUD_MODE = bool(SB_URL and SB_KEY)

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
os.makedirs(DATA_DIR, exist_ok=True)

COLLECTIONS = ["candidates", "leads", "jobs", "transactions", "agencies",
               "settings", "conversations", "knowledge_base"]

COLLECTION_TIMEOUT = 25


def _headers(prefer="resolution=merge-duplicates"):
    return {
        "apikey": SB_KEY,
        "Authorization": "Bearer " + SB_KEY,
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


# ---------------- cloud helpers ----------------

def sb_load(name):
    r = requests.get(
        SB_URL + "/rest/v1/app_data",
        params={"key": "eq." + name, "select": "value"},
        headers=_headers("return=representation"),
        timeout=COLLECTION_TIMEOUT,
    )
    if r.status_code != 200:
        raise RuntimeError("Supabase load %s failed: %s %s" % (name, r.status_code, r.text[:200]))
    rows = r.json()
    return rows[0]["value"] if rows else None


def sb_save(name, data):
    # explicit updated_at (no DB trigger needed)
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    r = requests.post(
        SB_URL + "/rest/v1/app_data",
        json={"key": name, "value": data, "updated_at": ts},
        headers=_headers(),
        timeout=COLLECTION_TIMEOUT,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError("Supabase save %s failed: %s %s" % (name, r.status_code, r.text[:200]))


def sb_last_updated():
    r = requests.get(
        SB_URL + "/rest/v1/app_data",
        params={"select": "updated_at", "order": "updated_at.desc", "limit": "1"},
        headers=_headers("return=representation"),
        timeout=10,
    )
    rows = r.json()
    return rows[0]["updated_at"] if rows else ""


# ---------------- local helpers ----------------

def _local_read(name):
    p = os.path.join(DATA_DIR, name + ".json")
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def _local_write(name, data):
    with open(os.path.join(DATA_DIR, name + ".json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def _local_last_updated():
    newest = 0
    if os.path.isdir(DATA_DIR):
        for f in os.listdir(DATA_DIR):
            if f.endswith(".json"):
                try:
                    newest = max(newest, os.path.getmtime(os.path.join(DATA_DIR, f)))
                except OSError:
                    pass
    return str(newest)


# ---------------- public API ----------------

def _empty(name):
    return {} if name == "settings" else []


def load(name):
    if CLOUD_MODE:
        try:
            v = sb_load(name)
            if v is not None:
                return v
        except Exception as e:
            print("[storage] cloud load error (%s), using local shadow: %s" % (name, e))
            v = _local_read(name)
            if v is not None:
                return v
        return _empty(name)
    v = _local_read(name)
    if v is None:
        return _empty(name)
    if name == "settings" and isinstance(v, list):
        return {}
    return v


def save(name, data):
    if CLOUD_MODE:
        sb_save(name, data)          # raises loudly on failure (data safety)
        try:
            _local_write(name, data)  # local shadow copy = offline backup
        except Exception:
            pass
    else:
        _local_write(name, data)


def data_exists(name):
    if CLOUD_MODE:
        try:
            return sb_load(name) is not None
        except Exception:
            pass
    return os.path.exists(os.path.join(DATA_DIR, name + ".json"))


def last_updated():
    """Timestamp of the most recent data change (used by the live-sync poller)."""
    if CLOUD_MODE:
        try:
            return sb_last_updated()
        except Exception:
            pass
    return _local_last_updated()


# ---------------- one-time migration ----------------

def migrate_local_to_cloud():
    """Upload existing local JSON data to Supabase on first cloud-mode start.
    A collection is skipped if it already has a cloud row (cloud wins)."""
    moved = []
    for name in COLLECTIONS:
        local = _local_read(name)
        if local is None:
            continue
        try:
            if sb_load(name) is None:
                sb_save(name, local)
                moved.append(name)
        except Exception as e:
            print("[storage] migration skipped %s: %s" % (name, e))
    if moved:
        print("[storage] migrated to cloud: " + ", ".join(moved))


if CLOUD_MODE:
    print("[storage] CLOUD MODE: Supabase " + SB_URL)
    try:
        migrate_local_to_cloud()
    except Exception as e:
        print("[storage] migration problem: %s" % e)
else:
    print("[storage] LOCAL MODE: data/*.json")
