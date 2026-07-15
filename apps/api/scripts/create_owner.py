from __future__ import annotations

import argparse
import getpass

from sqlalchemy import func, select

from app.database import Base, SessionLocal, engine
from app.models import User
from app.security import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the single Xiaobai OWNER account")
    parser.add_argument("--email", required=True)
    parser.add_argument("--phone", default=None)
    args = parser.parse_args()
    password = getpass.getpass("OWNER password (12+ chars): ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("Passwords do not match")
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if (db.scalar(select(func.count(User.id))) or 0) > 0:
            raise SystemExit("An OWNER already exists; public registration is intentionally unavailable.")
        db.add(User(email=args.email.lower(), phone=args.phone, password_hash=hash_password(password), role="OWNER"))
        db.commit()
    print("OWNER created. Sign in and bind TOTP immediately.")


if __name__ == "__main__":
    main()

