"""
Seed the profiles table from a JSON file.

Usage:
    python seed.py                          # reads profiles_seed.json by default
    python seed.py path/to/profiles.json    # custom file path

Re-running is safe — duplicate names are silently skipped via ON CONFLICT DO NOTHING.
"""

import json
import sys
import os
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert
from database import engine, SessionLocal, Base
from models import Profile
from utils import generate_uuid7


def seed(file_path: str = "profiles_seed.json") -> None:
    if not os.path.exists(file_path):
        print(f"[seed] ERROR: File not found — {file_path}")
        sys.exit(1)

    print(f"[seed] Reading profiles from {file_path} ...")
    with open(file_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # Accept either a plain list or {"data": [...]} or {"profiles": [...]}
    if isinstance(raw, list):
        profiles_data = raw
    elif isinstance(raw, dict):
        profiles_data = raw.get("data") or raw.get("profiles") or []
    else:
        print("[seed] ERROR: Unexpected JSON structure.")
        sys.exit(1)

    print(f"[seed] {len(profiles_data)} records found. Creating tables if needed ...")
    Base.metadata.create_all(bind=engine)

    now = datetime.now(timezone.utc)
    records = []
    for p in profiles_data:
        records.append(
            {
                "id": generate_uuid7(),
                "name": p["name"],
                "gender": p["gender"],
                "gender_probability": float(p["gender_probability"]),
                "age": int(p["age"]),
                "age_group": p["age_group"],
                "country_id": p["country_id"],
                "country_name": p["country_name"],
                "country_probability": float(p["country_probability"]),
                "created_at": now,
            }
        )

    if not records:
        print("[seed] Nothing to insert.")
        return

    # Bulk upsert — skip on name conflict
    stmt = (
        pg_insert(Profile.__table__)
        .values(records)
        .on_conflict_do_nothing(index_elements=["name"])
    )

    with engine.connect() as conn:
        result = conn.execute(stmt)
        conn.commit()

    inserted = result.rowcount if result.rowcount >= 0 else len(records)
    skipped = len(records) - (result.rowcount if result.rowcount >= 0 else 0)
    print(f"[seed] Done. ~{inserted} inserted, ~{skipped} skipped (duplicates).")


if __name__ == "__main__":
    file_arg = sys.argv[1] if len(sys.argv) > 1 else "profiles_seed.json"
    seed(file_arg)
