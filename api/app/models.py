from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


class RunState(StrEnum):
    QUEUED = "QUEUED"
    PROVISIONING = "PROVISIONING"
    STAGING_INPUTS = "STAGING_INPUTS"
    RUNNING = "RUNNING"
    COLLECTING_OUTPUTS = "COLLECTING_OUTPUTS"
    FINALIZING = "FINALIZING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"
    INFRA_FAILED = "INFRA_FAILED"


ACTIVE_RUN_STATES = (
    RunState.PROVISIONING,
    RunState.STAGING_INPUTS,
    RunState.RUNNING,
    RunState.COLLECTING_OUTPUTS,
    RunState.FINALIZING,
)

TERMINAL_RUN_STATES = (
    RunState.SUCCEEDED,
    RunState.FAILED,
    RunState.TIMED_OUT,
    RunState.CANCELLED,
    RunState.INFRA_FAILED,
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("usr"))
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String, default="trainer")
    state: Mapped[str] = mapped_column(String, default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    runs: Mapped[list["Run"]] = relationship(back_populates="user")


class SessionToken(Base):
    __tablename__ = "session_tokens"

    token: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("tok"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Quota(Base):
    __tablename__ = "quotas"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("quo"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True)
    max_active_runs: Mapped[int] = mapped_column(Integer, default=2)
    max_queued_runs: Mapped[int] = mapped_column(Integer, default=10)
    max_runtime_seconds: Mapped[int] = mapped_column(Integer, default=7200)
    max_upload_mb: Mapped[int] = mapped_column(Integer, default=2048)
    max_output_mb: Mapped[int] = mapped_column(Integer, default=4096)
    max_monthly_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    parent_cpu: Mapped[int] = mapped_column(Integer, default=2)
    parent_memory_mb: Mapped[int] = mapped_column(Integer, default=6144)
    parent_disk_gb: Mapped[int] = mapped_column(Integer, default=25)


class ParentSandbox(Base):
    __tablename__ = "parent_sandboxes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("par"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String, default="local-docker")
    state: Mapped[str] = mapped_column(String, default="PROVISIONING", index=True)
    template_version: Mapped[str] = mapped_column(String, default="harbor-opencode-2026.07.10")
    container_id: Mapped[str | None] = mapped_column(String, nullable=True)
    cpu: Mapped[int] = mapped_column(Integer, default=2)
    memory_mb: Mapped[int] = mapped_column(Integer, default=6144)
    disk_gb: Mapped[int] = mapped_column(Integer, default=25)
    workspace_uri: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    refresh_after_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class TaskBundle(Base):
    __tablename__ = "task_bundles"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("bun"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    parent_sandbox_id: Mapped[str] = mapped_column(ForeignKey("parent_sandboxes.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    task_name: Mapped[str] = mapped_column(String)
    uri: Mapped[str] = mapped_column(Text)
    workspace_uri: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str | None] = mapped_column(String, nullable=True)
    task_toml: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String, default="READY")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("run"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    parent_sandbox_id: Mapped[str] = mapped_column(ForeignKey("parent_sandboxes.id"), index=True)
    task_bundle_id: Mapped[str] = mapped_column(ForeignKey("task_bundles.id"), index=True)
    state: Mapped[str] = mapped_column(String, index=True, default=RunState.QUEUED)
    task_name: Mapped[str] = mapped_column(String)
    task_toml: Mapped[str] = mapped_column(Text)
    normalized_spec: Mapped[dict] = mapped_column(JSON)
    execution_mode: Mapped[str] = mapped_column(String, default="harbor")
    resource_profile: Mapped[str] = mapped_column(String)
    cpu: Mapped[int] = mapped_column(Integer)
    memory_mb: Mapped[int] = mapped_column(Integer)
    disk_gb: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String, default="local-docker")
    container_id: Mapped[str | None] = mapped_column(String, nullable=True)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_estimate: Mapped[float] = mapped_column(Float, default=0.0)
    artifact_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    cleanup_state: Mapped[str] = mapped_column(String, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    user: Mapped[User] = relationship(back_populates="runs")
    events: Mapped[list["RunEvent"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class RunEvent(Base):
    __tablename__ = "run_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    sequence_number: Mapped[int] = mapped_column(Integer)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    type: Mapped[str] = mapped_column(String)
    stream: Mapped[str | None] = mapped_column(String, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)

    run: Mapped[Run] = relationship(back_populates="events")


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("art"))
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    kind: Mapped[str] = mapped_column(String, default="result-package")
    path: Mapped[str] = mapped_column(String)
    uri: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    run: Mapped[Run] = relationship(back_populates="artifacts")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String, index=True)
    target_type: Mapped[str] = mapped_column(String, index=True)
    target_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String, default="SUCCESS")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
