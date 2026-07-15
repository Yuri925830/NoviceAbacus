from __future__ import annotations

from sqlalchemy import select

from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.models import RefreshSession, User
from app.security import hash_password


settings = get_settings()


def main() -> None:
    identifier = (settings.owner_id or settings.owner_email).strip()
    password = settings.owner_password
    if not identifier or not password:
        raise SystemExit("OWNER_ID (or OWNER_EMAIL) and OWNER_PASSWORD must be configured.")

    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        users = list(db.scalars(select(User)))
        if len(users) > 1:
            raise SystemExit("Refusing to continue: more than one OWNER record exists.")

        if users:
            owner = users[0]
            owner.email = identifier.lower()
            owner.phone = settings.owner_phone or None
            owner.password_hash = hash_password(password)
            owner.failed_login_count = 0
            owner.locked_until = None
            db.query(RefreshSession).filter(RefreshSession.user_id == owner.id).delete()
            action = "updated"
        else:
            owner = User(
                email=identifier.lower(),
                phone=settings.owner_phone or None,
                password_hash=hash_password(password),
                role="OWNER",
            )
            db.add(owner)
            action = "created"

        db.commit()
        print(f"OWNER {action}; existing trusted sessions revoked.")


if __name__ == "__main__":
    main()
