"""Create the first owner from CLI.

Usage:
    python scripts/create_owner.py <username> <password>

If a user with that username already exists, this is a no-op. If an owner
already exists, refuses to create another via this script (use create_user.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow `python scripts/create_owner.py` from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select  # noqa: E402

from app.auth import hash_password  # noqa: E402
from app.db import create_db_and_tables, get_engine  # noqa: E402
from app.models import User, UserRole  # noqa: E402


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: create_owner.py <username> <password>", file=sys.stderr)
        return 2
    username, password = sys.argv[1], sys.argv[2]
    if len(password) < 4:
        print("password must be at least 4 characters", file=sys.stderr)
        return 2
    create_db_and_tables()
    with Session(get_engine()) as s:
        existing = s.exec(select(User).where(User.username == username)).first()
        if existing:
            if existing.role == UserRole.OWNER:
                print(f"owner '{username}' already exists; nothing to do")
                return 0
            existing.role = UserRole.OWNER
            existing.password_hash = hash_password(password)
            s.add(existing)
            s.commit()
            print(f"promoted user '{username}' to owner")
            return 0
        user = User(username=username, password_hash=hash_password(password), role=UserRole.OWNER)
        s.add(user)
        s.commit()
        print(f"created owner '{username}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
