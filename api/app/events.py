from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import RunEvent


def add_event(
    db: Session,
    run_id: str,
    event_type: str,
    message: str | None = None,
    stream: str | None = None,
    payload: dict | None = None,
) -> None:
    seq = (
        db.query(func.coalesce(func.max(RunEvent.sequence_number), 0))
        .filter(RunEvent.run_id == run_id)
        .scalar()
        + 1
    )
    db.add(
        RunEvent(
            run_id=run_id,
            sequence_number=seq,
            ts=datetime.now(timezone.utc),
            type=event_type,
            message=message,
            stream=stream,
            payload=payload or {},
        )
    )
    db.commit()
