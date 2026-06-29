"""Dev bootstrap: create a ready-to-use, verified account with credits.

Skips the email-verification step (dev only) so you can log in and generate
immediately without a GPU. Idempotent — safe to run repeatedly.

Usage (from backend/, or inside the api container):
    python -m app.db.bootstrap --email dev@local --password Str0ngPassw0rd \
        --credits 100 --admin
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.logging import configure_logging, get_logger
from app.core.security import hash_password
from app.db.sync_session import session_scope
from app.modules.credits.models import CreditBalance, CreditTransaction, TxnType
from app.modules.users.models import Role, User, UserStatus

logger = get_logger("bootstrap")


def _ensure_role(db: Session, name: str) -> Role:
    role = db.execute(select(Role).where(Role.name == name)).scalar_one_or_none()
    if role is None:
        role = Role(name=name, description=name)
        db.add(role)
        db.flush()
    return role


def _grant(db: Session, user_id, amount: int, idem: str) -> None:
    if db.execute(
        select(CreditTransaction).where(
            CreditTransaction.user_id == user_id,
            CreditTransaction.idempotency_key == idem,
        )
    ).scalar_one_or_none():
        return
    bal = db.execute(
        select(CreditBalance).where(CreditBalance.user_id == user_id).with_for_update()
    ).scalar_one_or_none()
    if bal is None:
        bal = CreditBalance(user_id=user_id, balance=0, held=0, version=0)
        db.add(bal)
        db.flush()
    db.add(CreditTransaction(
        user_id=user_id, type=TxnType.GRANT, amount=amount,
        reason="dev_bootstrap", idempotency_key=idem,
    ))
    bal.balance += amount
    bal.version += 1
    db.flush()


def run(email: str, password: str, credits: int, admin: bool) -> None:
    configure_logging(json_logs=False)
    with session_scope() as db:
        user = db.execute(
            select(User).where(func.lower(User.email) == email.lower())
        ).scalar_one_or_none()
        if user is None:
            user = User(
                email=email,
                password_hash=hash_password(password),
                display_name="Dev User",
                status=UserStatus.ACTIVE,
                email_verified_at=datetime.now(timezone.utc),  # skip email in dev
            )
            user.roles.append(_ensure_role(db, "user"))
            db.add(user)
            db.flush()
            logger.info("dev_user_created", email=email)
        else:
            user.password_hash = hash_password(password)
            user.email_verified_at = user.email_verified_at or datetime.now(timezone.utc)
            logger.info("dev_user_updated", email=email)

        if admin:
            role = _ensure_role(db, "admin")
            if role not in user.roles:
                user.roles.append(role)

        if credits > 0:
            # Unique key per run so re-running tops up (dev convenience).
            from app.core.ids import uuid7

            _grant(db, user.id, credits, idem=f"bootstrap:{user.id}:{uuid7()}")

        print(f"Ready: {email} (password: {password}) "
              f"credits={credits} admin={admin}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", default="dev@local")
    ap.add_argument("--password", default="Str0ngPassw0rd")
    ap.add_argument("--credits", type=int, default=100)
    ap.add_argument("--admin", action="store_true")
    args = ap.parse_args()
    run(args.email, args.password, args.credits, args.admin)


if __name__ == "__main__":
    main()
