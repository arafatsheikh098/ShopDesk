"""Create a cashier (or owner) from CLI.

Usage:
    python scripts/create_user.py <username> <password> [owner|cashier]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select  # noqa: E402

from app.auth import hash_password  # noqa: E402
from app.db import create_db_and_tables, get_engine  # noqa: E402
from app.models import User, UserRole  # noqa: E402


def main() -> int:
    if len(sys.argv) not in (3, 4):
        print("usage: create_user.py <username> <password> [owner|cashier]", file=sys.stderr)
        return 2
    username, password = sys.argv[1], sys.argv[2]
    role = UserRole(sys.argv[3]) if len(sys.argv) == 4 else UserRole.CASHIER
    if len(password) < 4:
        print("password must be at least 4 characters", file=sys.stderr)
        return 2
    create_db_and_tables()
    with Session(get_engine()) as s:
        existing = s.exec(select(User).where(User.username == username)).first()
        if existing:
            existing.password_hash = hash_password(password)
            existing.role = role
            existing.is_active = True
            s.add(existing)
            s.commit()
            print(f"updated user '{username}' (role={role.value})")
            return 0
        user = User(username=username, password_hash=hash_password(password), role=role)
        s.add(user)
        s.commit()
        print(f"created {role.value} '{username}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
