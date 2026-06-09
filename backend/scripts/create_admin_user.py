#!/usr/bin/env python3
"""Promote an existing user to admin by email."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.client import close_mongo_client, get_mongo_client
from app.config import get_settings
from app.auth.repository import set_user_role, get_user_by_email


async def main() -> int:
    parser = argparse.ArgumentParser(description="Promote user to admin role.")
    parser.add_argument("email", type=str, help="User email")
    args = parser.parse_args()

    settings = get_settings()
    client = get_mongo_client()
    db = client[settings.mongo_db_name]

    existing = await get_user_by_email(db, args.email)
    if not existing:
        print(f"User not found: {args.email}", file=sys.stderr)
        await close_mongo_client()
        return 1

    updated = await set_user_role(db, email=args.email, role="admin")
    await close_mongo_client()
    print(f"Promoted {updated['email']} to admin")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
