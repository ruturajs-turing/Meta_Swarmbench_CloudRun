from sqlalchemy.orm import Session

from .models import AuditLog, User


def record_audit(
    db: Session,
    actor: User | None,
    action: str,
    target_type: str,
    target_id: str | None,
    *,
    status: str = "SUCCESS",
    detail: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_user_id=actor.id if actor else None,
            action=action,
            target_type=target_type,
            target_id=target_id,
            status=status,
            detail=detail or {},
        )
    )
    db.commit()
