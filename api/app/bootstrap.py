from sqlalchemy.orm import Session

from .db import Base, engine
from .models import Quota, User
from .security import hash_password


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def seed(db: Session) -> None:
    if db.query(User).count():
        return

    admin = User(
        username="admin",
        email="admin@aegisrun.local",
        display_name="Platform Admin",
        password_hash=hash_password("aegisrun"),
        role="platform_admin",
    )
    trainer = User(
        username="trainer",
        email="trainer@aegisrun.local",
        display_name="Demo Trainer",
        password_hash=hash_password("trainer123"),
        role="trainer",
    )
    db.add_all([admin, trainer])
    db.flush()
    db.add_all(
        [
            Quota(user_id=admin.id, max_active_runs=2, max_queued_runs=10),
            Quota(user_id=trainer.id, max_active_runs=2, max_queued_runs=10),
        ]
    )
    db.commit()
