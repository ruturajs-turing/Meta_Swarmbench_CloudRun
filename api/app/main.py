import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import docker
from docker.errors import DockerException, ImageNotFound
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .audit import record_audit
from .auth import current_user, require_admin
from .bootstrap import init_db, seed
from .db import SessionLocal, get_db
from .docker_runner import cancel_run, cleanup_orphans, start_queue_drain
from .models import (
    ACTIVE_RUN_STATES,
    TERMINAL_RUN_STATES,
    Artifact,
    AuditLog,
    ParentSandbox,
    Quota,
    Run,
    RunEvent,
    RunState,
    SessionToken,
    TaskBundle,
    User,
    new_id,
)
from .parent_runtime import (
    current_parent,
    ensure_parent,
    parent_action,
    parent_stats,
    provision_parent,
    reconcile_parents,
    workspace_path,
)
from .providers import PROVIDER_CAPABILITIES
from .security import hash_password, verify_password
from .settings import settings
from .task_bundles import create_task_bundle, import_staged_task
from .toml_validator import validate_task_toml


app = FastAPI(title="AegisRun Control Plane", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[item.strip() for item in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoginRequest(BaseModel):
    identifier: str | None = None
    email: str | None = None
    password: str


class CreateRunRequest(BaseModel):
    task_bundle_id: str
    execution_mode: str = "harbor"


class StagedTaskRequest(BaseModel):
    relative_path: str


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=48, pattern=r"^[a-zA-Z0-9._-]+$")
    email: str
    display_name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=8, max_length=200)
    role: str = "trainer"


class UserPatchRequest(BaseModel):
    display_name: str | None = None
    email: str | None = None
    role: str | None = None
    state: str | None = None


class PasswordResetRequest(BaseModel):
    password: str = Field(min_length=8, max_length=200)


class QuotaPatch(BaseModel):
    max_active_runs: int | None = Field(default=None, ge=1, le=10)
    max_queued_runs: int | None = Field(default=None, ge=1, le=100)
    max_runtime_seconds: int | None = Field(default=None, ge=60, le=43200)
    max_upload_mb: int | None = Field(default=None, ge=32, le=10240)
    max_output_mb: int | None = Field(default=None, ge=32, le=20480)
    max_monthly_cost: float | None = Field(default=None, ge=0)
    parent_cpu: int | None = Field(default=None, ge=1, le=16)
    parent_memory_mb: int | None = Field(default=None, ge=1024, le=65536)
    parent_disk_gb: int | None = Field(default=None, ge=10, le=500)


class ParentCreateRequest(BaseModel):
    user_id: str
    provider: str = "local-docker"


@app.on_event("startup")
def startup() -> None:
    init_db()
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()
    start_queue_drain()
    _start_reconciler()


def iso(value):
    return value.isoformat() if value else None


def quota_for(db: Session, user_id: str) -> Quota:
    quota = db.query(Quota).filter(Quota.user_id == user_id).first()
    if quota:
        return quota
    quota = Quota(user_id=user_id)
    db.add(quota)
    db.commit()
    return quota


def quota_dict(quota: Quota, db: Session) -> dict:
    active = db.query(Run).filter(Run.user_id == quota.user_id, Run.state.in_(ACTIVE_RUN_STATES)).count()
    queued = db.query(Run).filter(Run.user_id == quota.user_id, Run.state == RunState.QUEUED).count()
    return {
        "max_active_runs": quota.max_active_runs,
        "max_queued_runs": quota.max_queued_runs,
        "max_runtime_seconds": quota.max_runtime_seconds,
        "max_upload_mb": quota.max_upload_mb,
        "max_output_mb": quota.max_output_mb,
        "max_monthly_cost": quota.max_monthly_cost,
        "parent_cpu": quota.parent_cpu,
        "parent_memory_mb": quota.parent_memory_mb,
        "parent_disk_gb": quota.parent_disk_gb,
        "active_runs": active,
        "queued_runs": queued,
    }


def user_dict(user: User, db: Session, *, include_quota: bool = True) -> dict:
    parent = current_parent(db, user.id)
    result = {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "state": user.state,
        "created_at": iso(user.created_at),
        "last_login_at": iso(user.last_login_at),
        "parent_id": parent.id if parent else None,
        "parent_state": parent.state if parent else "NOT_CREATED",
        "active_runs": db.query(Run).filter(Run.user_id == user.id, Run.state.in_(ACTIVE_RUN_STATES)).count(),
        "run_count": db.query(Run).filter(Run.user_id == user.id).count(),
    }
    if include_quota:
        result["quota"] = quota_dict(quota_for(db, user.id), db)
    return result


def parent_dict(parent: ParentSandbox, db: Session) -> dict:
    user = db.get(User, parent.user_id)
    active = db.query(Run).filter(Run.parent_sandbox_id == parent.id, Run.state.in_(ACTIVE_RUN_STATES)).count()
    bundle_count = db.query(TaskBundle).filter(TaskBundle.parent_sandbox_id == parent.id).count()
    return {
        "id": parent.id,
        "user_id": parent.user_id,
        "username": user.username if user else "unknown",
        "display_name": user.display_name if user else "Unknown user",
        "provider": parent.provider,
        "state": parent.state,
        "template_version": parent.template_version,
        "container_id": parent.container_id,
        "cpu": parent.cpu,
        "memory_mb": parent.memory_mb,
        "disk_gb": parent.disk_gb,
        "workspace_uri": parent.workspace_uri,
        "created_at": iso(parent.created_at),
        "started_at": iso(parent.started_at),
        "last_active_at": iso(parent.last_active_at),
        "refresh_after_at": iso(parent.refresh_after_at),
        "paused_at": iso(parent.paused_at),
        "error": parent.error,
        "active_runs": active,
        "task_count": bundle_count,
    }


def bundle_dict(bundle: TaskBundle) -> dict:
    return {
        "id": bundle.id,
        "parent_sandbox_id": bundle.parent_sandbox_id,
        "name": bundle.name,
        "task_name": bundle.task_name,
        "state": bundle.state,
        "size_bytes": bundle.size_bytes,
        "sha256": bundle.sha256,
        "workspace_uri": bundle.workspace_uri,
        "created_at": iso(bundle.created_at),
    }


def run_dict(run: Run, db: Session) -> dict:
    user = db.get(User, run.user_id)
    bundle = db.get(TaskBundle, run.task_bundle_id)
    return {
        "id": run.id,
        "user_id": run.user_id,
        "username": user.username if user else "unknown",
        "display_name": user.display_name if user else "Unknown user",
        "parent_sandbox_id": run.parent_sandbox_id,
        "task_bundle_id": run.task_bundle_id,
        "bundle_name": bundle.name if bundle else None,
        "state": run.state,
        "task_name": run.task_name,
        "execution_mode": run.execution_mode,
        "resource_profile": run.resource_profile,
        "cpu": run.cpu,
        "memory_mb": run.memory_mb,
        "disk_gb": run.disk_gb,
        "resource_resolution": resource_resolution(run),
        "provider": run.provider,
        "container_id": run.container_id,
        "queued_at": iso(run.queued_at),
        "started_at": iso(run.started_at),
        "finished_at": iso(run.finished_at),
        "duration_seconds": run.duration_seconds,
        "exit_code": run.exit_code,
        "passed": run.passed,
        "failure_reason": run.failure_reason,
        "cost_estimate": run.cost_estimate,
        "artifact_uri": run.artifact_uri,
        "cleanup_state": run.cleanup_state,
        "event_count": db.query(RunEvent).filter(RunEvent.run_id == run.id).count(),
        "artifact_count": db.query(Artifact).filter(Artifact.run_id == run.id).count(),
    }


def resource_resolution(run: Run) -> dict:
    spec = run.normalized_spec or {}
    source = spec.get("_aegisrun", {}).get("resource_source", {})
    return {
        "source": "task.toml",
        "format": source.get("format", "unknown"),
        "section": source.get("section", "resources"),
        "cpu_field": source.get("cpu_field", "cpu"),
        "memory_field": source.get("memory_field", "memory_gb"),
        "disk_field": source.get("disk_field", "disk_gb"),
        "profile": run.resource_profile,
        "cpu": run.cpu,
        "memory_mb": run.memory_mb,
        "disk_gb": run.disk_gb,
        "timeout_seconds": int(spec.get("run", {}).get("timeout_seconds", 0)),
        "network_egress": spec.get("network", {}).get("egress", "deny"),
    }


def runtime_health() -> dict:
    try:
        client = docker.from_env()
        docker_ok = bool(client.ping())
        images = {tag for image in client.images.list() for tag in image.tags}
    except DockerException as exc:
        return {"docker": False, "error": str(exc), "parent_image": False, "runner_image": False}
    return {
        "docker": docker_ok,
        "parent_image": settings.parent_image in images,
        "runner_image": settings.harbor_runner_image in images,
        "parent_image_name": settings.parent_image,
        "runner_image_name": settings.harbor_runner_image,
        "harbor_enabled": settings.harbor_runtime_enabled,
        "fireworks_configured": bool(os.environ.get("FIREWORKS_API_KEY")),
    }


@app.get("/health")
def health():
    return {"ok": True, "service": "aegisrun-control-plane", "version": "2.0.0"}


@app.post("/v1/sessions")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    identifier = (body.identifier or body.email or "").strip()
    user = db.query(User).filter(or_(User.username == identifier, User.email == identifier)).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if user.state != "active":
        raise HTTPException(status_code=403, detail="This account is disabled")
    now = datetime.now(timezone.utc)
    user.last_login_at = now
    session = SessionToken(user_id=user.id, expires_at=now + timedelta(hours=settings.session_hours))
    db.add(session)
    db.commit()
    parent = None
    if user.role == "trainer":
        parent = ensure_parent(db, user)
    return {
        "token": session.token,
        "expires_at": iso(session.expires_at),
        "user": user_dict(user, db, include_quota=False),
        "parent": parent_dict(parent, db) if parent else None,
    }


@app.delete("/v1/sessions/current")
def logout(
    authorization: str | None = Header(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    token = (authorization or "").removeprefix("Bearer ").strip()
    if token:
        db.query(SessionToken).filter(SessionToken.token == token, SessionToken.user_id == user.id).delete()
        db.commit()
    return {"ok": True}


@app.get("/v1/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return user_dict(user, db)


@app.get("/v1/quota")
def my_quota(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return quota_dict(quota_for(db, user.id), db)


@app.get("/v1/runtime")
def runtime(_: User = Depends(current_user)):
    return runtime_health() | {
        "modes": {
            "probe": {"enabled": True, "label": "Structure check"},
            "harbor": {"enabled": settings.harbor_runtime_enabled, "label": "Harbor model logs"},
        }
    }


@app.get("/v1/terminal")
def terminal_info(user: User = Depends(current_user)):
    terminal_username = user.username if user.role in {"trainer", "reviewer"} else "<trainer-username>"
    return {
        "ssh_host": settings.ssh_public_host,
        "ssh_port": settings.ssh_public_port,
        "ssh_command": f"ssh -p {settings.ssh_public_port} {terminal_username}@{settings.ssh_public_host}",
        "sftp_command": f"sftp -P {settings.ssh_public_port} {terminal_username}@{settings.ssh_public_host}",
        "upload_target": "/incoming",
    }


@app.get("/v1/workspace")
def workspace(user: User = Depends(current_user), db: Session = Depends(get_db)):
    parent = ensure_parent(db, user)
    bundles = db.query(TaskBundle).filter(TaskBundle.user_id == user.id).order_by(TaskBundle.created_at.desc()).limit(10).all()
    runs = db.query(Run).filter(Run.user_id == user.id).order_by(Run.created_at.desc()).limit(10).all()
    incoming = workspace_path(user.id) / "incoming"
    staged = sorted(item.name for item in incoming.iterdir() if not item.name.startswith("."))
    return {
        "parent": parent_dict(parent, db),
        "quota": quota_dict(quota_for(db, user.id), db),
        "bundles": [bundle_dict(bundle) for bundle in bundles],
        "runs": [run_dict(run, db) for run in runs],
        "staged_uploads": staged,
    }


@app.post("/v1/workspace/{action}")
def my_parent_action(action: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    parent = current_parent(db, user.id)
    if not parent:
        if action == "resume":
            parent = provision_parent(db, user)
        else:
            raise HTTPException(status_code=404, detail="Parent workspace does not exist")
    else:
        parent = parent_action(db, parent, action)
    record_audit(db, user, f"workspace.{action}", "parent", parent.id)
    return parent_dict(parent, db)


@app.post("/v1/tasks/upload")
def upload_task(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    parent = ensure_parent(db, user)
    if parent.state != "RUNNING":
        raise HTTPException(status_code=409, detail=f"Parent workspace is not ready: {parent.state}")
    bundle = create_task_bundle(db, user, parent, file)
    parent.last_active_at = datetime.now(timezone.utc)
    db.commit()
    record_audit(db, user, "task.upload", "task_bundle", bundle.id, detail={"task_name": bundle.task_name})
    return {"bundle": bundle_dict(bundle)}


@app.post("/v1/tasks/submit")
def submit_task(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    execution_mode: str = Form(default="harbor"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Upload, validate, and queue one task without a separate staging step."""
    _validate_execution_mode(execution_mode)
    parent = ensure_parent(db, user)
    if parent.state != "RUNNING":
        raise HTTPException(status_code=409, detail=f"Parent workspace is not ready: {parent.state}")
    bundle = create_task_bundle(db, user, parent, file)
    run = _create_run_record(db, user, bundle, execution_mode)
    parent.last_active_at = datetime.now(timezone.utc)
    db.commit()
    record_audit(
        db,
        user,
        "task.submit",
        "run",
        run.id,
        detail={"bundle_id": bundle.id, "task_name": bundle.task_name, "mode": execution_mode},
    )
    background.add_task(start_queue_drain)
    return {
        "bundle": bundle_dict(bundle),
        "run": run_dict(run, db),
        "resource_resolution": resource_resolution(run),
    }


@app.post("/v1/tasks/import-staged")
def import_staged(body: StagedTaskRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    parent = ensure_parent(db, user)
    bundle = import_staged_task(db, user, parent, body.relative_path)
    record_audit(db, user, "task.import_staged", "task_bundle", bundle.id)
    return {"bundle": bundle_dict(bundle)}


@app.get("/v1/tasks")
def list_tasks(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(TaskBundle).filter(TaskBundle.user_id == user.id).order_by(TaskBundle.created_at.desc()).limit(100).all()
    return {"bundles": [bundle_dict(row) for row in rows]}


@app.post("/v1/runs")
def create_run(body: CreateRunRequest, background: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _validate_execution_mode(body.execution_mode)
    bundle = db.get(TaskBundle, body.task_bundle_id)
    if not bundle or bundle.user_id != user.id or bundle.state != "READY":
        raise HTTPException(status_code=404, detail="Ready task bundle not found")
    run = _create_run_record(db, user, bundle, body.execution_mode)
    record_audit(db, user, "run.submit", "run", run.id, detail={"bundle_id": bundle.id, "mode": body.execution_mode})
    background.add_task(start_queue_drain)
    return run_dict(run, db)


def _validate_execution_mode(execution_mode: str) -> None:
    if execution_mode not in {"probe", "harbor"}:
        raise HTTPException(status_code=400, detail="execution_mode must be probe or harbor")
    if execution_mode == "harbor" and not settings.harbor_runtime_enabled:
        raise HTTPException(status_code=409, detail="Harbor runtime is disabled by the operator")


def _create_run_record(db: Session, user: User, bundle: TaskBundle, execution_mode: str) -> Run:
    _validate_execution_mode(execution_mode)
    quota = quota_for(db, user.id)
    queued = db.query(Run).filter(Run.user_id == user.id, Run.state == RunState.QUEUED).count()
    if queued >= quota.max_queued_runs:
        raise HTTPException(status_code=409, detail="Queued run limit reached")
    parent = ensure_parent(db, user)
    if parent.state != "RUNNING":
        raise HTTPException(status_code=409, detail=f"Parent workspace is not ready: {parent.state}")
    normalized = validate_task_toml(bundle.task_toml, quota.max_runtime_seconds)
    spec = normalized.spec
    task_type = spec.get("_aegisrun", {}).get("task_type")
    if execution_mode == "harbor":
        if task_type != "swarmbench-harbor":
            raise HTTPException(status_code=400, detail="Harbor mode requires a SwarmBench task.toml")
        spec["run"]["command"] = "bash .aegisrun_harbor_run.sh"
    spec.setdefault("_aegisrun", {})["execution_mode"] = execution_mode
    resources = spec["resources"]
    run = Run(
        user_id=user.id,
        parent_sandbox_id=parent.id,
        task_bundle_id=bundle.id,
        task_name=normalized.task_name,
        task_toml=bundle.task_toml,
        normalized_spec=spec,
        execution_mode=execution_mode,
        resource_profile=resources["profile"],
        cpu=int(resources["cpu"]),
        memory_mb=int(resources["memory_gb"]) * 1024,
        disk_gb=int(resources["disk_gb"]),
    )
    db.add(run)
    db.commit()
    return run


def owned_run(db: Session, user: User, run_id: str) -> Run:
    run = db.get(Run, run_id)
    if not run or (run.user_id != user.id and user.role not in {"admin", "platform_admin"}):
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.get("/v1/runs")
def list_runs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(Run).filter(Run.user_id == user.id).order_by(Run.created_at.desc()).limit(100).all()
    return {"runs": [run_dict(row, db) for row in rows]}


@app.get("/v1/runs/{run_id}")
def get_run(run_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    run = owned_run(db, user, run_id)
    return run_dict(run, db) | {"normalized_spec": run.normalized_spec}


@app.post("/v1/runs/{run_id}/cancel")
def cancel(run_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    run = owned_run(db, user, run_id)
    if not cancel_run(run.id):
        raise HTTPException(status_code=409, detail="Run is already terminal")
    record_audit(db, user, "run.cancel", "run", run.id)
    return {"ok": True}


@app.post("/v1/runs/{run_id}/retry")
def retry(run_id: str, background: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    old = owned_run(db, user, run_id)
    if old.state not in TERMINAL_RUN_STATES:
        raise HTTPException(status_code=409, detail="Run is not terminal")
    parent = db.get(ParentSandbox, old.parent_sandbox_id)
    if not parent or parent.state in {"DESTROYED", "ERROR"}:
        parent = ensure_parent(db, db.get(User, old.user_id))
    new = Run(
        user_id=old.user_id,
        parent_sandbox_id=parent.id,
        task_bundle_id=old.task_bundle_id,
        task_name=old.task_name,
        task_toml=old.task_toml,
        normalized_spec=old.normalized_spec,
        execution_mode=old.execution_mode,
        resource_profile=old.resource_profile,
        cpu=old.cpu,
        memory_mb=old.memory_mb,
        disk_gb=old.disk_gb,
    )
    db.add(new)
    db.commit()
    record_audit(db, user, "run.retry", "run", new.id, detail={"source_run_id": old.id})
    background.add_task(start_queue_drain)
    return run_dict(new, db)


@app.get("/v1/runs/{run_id}/events")
def run_events(run_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    owned_run(db, user, run_id)
    rows = db.query(RunEvent).filter(RunEvent.run_id == run_id).order_by(RunEvent.sequence_number).all()
    return {"events": [event_dict(row) for row in rows]}


@app.get("/v1/runs/{run_id}/logs")
def run_logs(run_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    owned_run(db, user, run_id)
    rows = db.query(RunEvent).filter(RunEvent.run_id == run_id, RunEvent.type == "LOG").order_by(RunEvent.sequence_number).all()
    return {"logs": [{"ts": iso(row.ts), "stream": row.stream, "line": row.message} for row in rows]}


@app.get("/v1/runs/{run_id}/artifacts")
def run_artifacts(run_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    owned_run(db, user, run_id)
    rows = db.query(Artifact).filter(Artifact.run_id == run_id).order_by(Artifact.created_at.desc()).all()
    return {"artifacts": [artifact_dict(row) for row in rows]}


@app.get("/v1/runs/{run_id}/artifacts/{artifact_id}/download")
def download_artifact(run_id: str, artifact_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    owned_run(db, user, run_id)
    artifact = db.get(Artifact, artifact_id)
    if not artifact or artifact.run_id != run_id:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(artifact.uri, filename=artifact.path)


@app.get("/v1/runs/{run_id}/stream")
def stream(run_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    owned_run(db, user, run_id)

    def generate():
        last_seq = 0
        while True:
            local = SessionLocal()
            try:
                rows = local.query(RunEvent).filter(RunEvent.run_id == run_id, RunEvent.sequence_number > last_seq).order_by(RunEvent.sequence_number).all()
                for row in rows:
                    last_seq = row.sequence_number
                    yield f"data: {json.dumps(event_dict(row))}\n\n"
                current = local.get(Run, run_id)
                if current and current.state in TERMINAL_RUN_STATES and not rows:
                    break
            finally:
                local.close()
            time.sleep(1)

    return StreamingResponse(generate(), media_type="text/event-stream")


def event_dict(row: RunEvent) -> dict:
    return {
        "sequence_number": row.sequence_number,
        "ts": iso(row.ts),
        "type": row.type,
        "stream": row.stream,
        "message": row.message,
        "payload": row.payload,
    }


def artifact_dict(row: Artifact) -> dict:
    return {
        "id": row.id,
        "kind": row.kind,
        "path": row.path,
        "size_bytes": row.size_bytes,
        "sha256": row.sha256,
        "created_at": iso(row.created_at),
        "download_url": f"/v1/runs/{row.run_id}/artifacts/{row.id}/download",
    }


@app.get("/admin/overview")
def admin_overview(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.display_name).all()
    trainer_count = sum(user.role == "trainer" for user in users)
    parents = db.query(ParentSandbox).filter(ParentSandbox.state != "DESTROYED").all()
    active_runs = db.query(Run).filter(Run.state.in_(ACTIVE_RUN_STATES)).all()
    failure_query = db.query(Run).filter(Run.state.in_([RunState.FAILED, RunState.TIMED_OUT, RunState.INFRA_FAILED]))
    failed = failure_query.order_by(Run.created_at.desc()).limit(8).all()
    recent = db.query(Run).order_by(Run.created_at.desc()).limit(12).all()
    return {
        "counts": {
            "users": trainer_count,
            "parents_running": sum(parent.state == "RUNNING" for parent in parents),
            "parents_attention": sum(parent.state in {"ERROR", "REFRESHING"} for parent in parents),
            "executions_active": len(active_runs),
            "runs_queued": db.query(Run).filter(Run.state == RunState.QUEUED).count(),
            "failures": failure_query.count(),
        },
        "topology": [
            {
                "user": user_dict(user, db, include_quota=False),
                "parent": parent_dict(parent, db) if (parent := current_parent(db, user.id)) else None,
                "executions": [run_dict(run, db) for run in active_runs if run.user_id == user.id],
            }
            for user in users
            if user.role == "trainer"
        ],
        "recent_runs": [run_dict(run, db) for run in recent],
        "attention_runs": [run_dict(run, db) for run in failed],
        "runtime": runtime_health(),
    }


@app.get("/admin/users")
def admin_users(q: str | None = None, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    query = db.query(User)
    if q:
        token = f"%{q}%"
        query = query.filter(or_(User.username.ilike(token), User.email.ilike(token), User.display_name.ilike(token)))
    rows = query.order_by(User.created_at.desc()).all()
    return {"users": [user_dict(row, db) for row in rows]}


@app.post("/admin/users")
def create_user(body: UserCreateRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if body.role not in {"trainer", "reviewer", "admin"}:
        raise HTTPException(status_code=400, detail="Unsupported role")
    if db.query(User).filter(or_(User.username == body.username, User.email == body.email)).first():
        raise HTTPException(status_code=409, detail="Username or email already exists")
    user = User(
        username=body.username,
        email=body.email,
        display_name=body.display_name,
        password_hash=hash_password(body.password),
        role=body.role,
    )
    db.add(user)
    db.flush()
    db.add(Quota(user_id=user.id))
    db.commit()
    record_audit(db, admin, "user.create", "user", user.id, detail={"username": user.username, "role": user.role})
    return user_dict(user, db)


@app.patch("/admin/users/{user_id}")
def patch_user(user_id: str, body: UserPatchRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    patch = body.model_dump(exclude_unset=True)
    if patch.get("role") not in {None, "trainer", "reviewer", "admin", "platform_admin"}:
        raise HTTPException(status_code=400, detail="Unsupported role")
    if patch.get("state") not in {None, "active", "disabled"}:
        raise HTTPException(status_code=400, detail="Unsupported user state")
    for key, value in patch.items():
        setattr(user, key, value)
    db.commit()
    record_audit(db, admin, "user.update", "user", user.id, detail=patch)
    return user_dict(user, db)


@app.post("/admin/users/{user_id}/reset-password")
def reset_password(user_id: str, body: PasswordResetRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.password_hash = hash_password(body.password)
    db.query(SessionToken).filter(SessionToken.user_id == user.id).delete()
    db.commit()
    record_audit(db, admin, "user.reset_password", "user", user.id)
    return {"ok": True}


@app.patch("/admin/users/{user_id}/quota")
def update_quota(user_id: str, body: QuotaPatch, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if not db.get(User, user_id):
        raise HTTPException(status_code=404, detail="User not found")
    quota = quota_for(db, user_id)
    patch = body.model_dump(exclude_unset=True)
    for key, value in patch.items():
        setattr(quota, key, value)
    db.commit()
    record_audit(db, admin, "quota.update", "user", user_id, detail=patch)
    return quota_dict(quota, db)


@app.get("/admin/parents")
def admin_parents(
    state: str | None = None,
    user_id: str | None = None,
    q: str | None = None,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(ParentSandbox)
    if state and state != "ALL":
        query = query.filter(ParentSandbox.state == state)
    if user_id:
        query = query.filter(ParentSandbox.user_id == user_id)
    rows = query.order_by(ParentSandbox.created_at.desc()).all()
    payload = [parent_dict(row, db) for row in rows]
    if q:
        token = q.lower()
        payload = [row for row in payload if token in json.dumps(row).lower()]
    return {"parents": payload, "total": len(payload)}


@app.post("/admin/parents")
def create_parent(body: ParentCreateRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, body.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    existing = current_parent(db, user.id)
    if existing and existing.state != "ERROR":
        raise HTTPException(status_code=409, detail="User already has a parent workspace")
    parent = provision_parent(db, user, replace=existing, provider=body.provider)
    record_audit(db, admin, "parent.create", "parent", parent.id, status="SUCCESS" if parent.state == "RUNNING" else "FAILED")
    return parent_dict(parent, db)


@app.post("/admin/parents/{parent_id}/{action}")
def admin_parent_action(parent_id: str, action: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    parent = db.get(ParentSandbox, parent_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Parent workspace not found")
    parent = parent_action(db, parent, action)
    record_audit(db, admin, f"parent.{action}", "parent", parent.id)
    return parent_dict(parent, db)


@app.get("/admin/parents/{parent_id}/stats")
def admin_parent_stats(parent_id: str, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    parent = db.get(ParentSandbox, parent_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Parent workspace not found")
    return parent_stats(parent)


@app.get("/admin/runs")
def admin_runs(
    state: str | None = None,
    user_id: str | None = None,
    q: str | None = None,
    limit: int = Query(default=250, ge=1, le=1000),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(Run)
    if state and state != "ALL":
        query = query.filter(Run.state == state)
    if user_id:
        query = query.filter(Run.user_id == user_id)
    rows = query.order_by(Run.created_at.desc()).limit(limit).all()
    payload = [run_dict(row, db) for row in rows]
    if q:
        token = q.lower()
        payload = [row for row in payload if token in json.dumps(row).lower()]
    return {"runs": payload, "total": len(payload)}


@app.post("/admin/runs/{run_id}/force-cleanup")
def force_cleanup(run_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.state not in TERMINAL_RUN_STATES:
        cancel_run(run.id)
    destroyed = cleanup_orphans()
    record_audit(db, admin, "run.force_cleanup", "run", run.id, detail={"destroyed": destroyed})
    return {"ok": True, "destroyed": destroyed}


@app.get("/admin/providers")
def admin_providers(_: User = Depends(require_admin)):
    return {
        "providers": [capability.__dict__ for capability in PROVIDER_CAPABILITIES.values()],
        "runtime": runtime_health(),
    }


@app.get("/admin/audit")
def admin_audit(
    action: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    rows = query.order_by(AuditLog.created_at.desc()).limit(limit).all()
    users = {user.id: user for user in db.query(User).all()}
    return {
        "events": [
            {
                "id": row.id,
                "actor_user_id": row.actor_user_id,
                "actor": users.get(row.actor_user_id).username if row.actor_user_id in users else "system",
                "action": row.action,
                "target_type": row.target_type,
                "target_id": row.target_id,
                "status": row.status,
                "detail": row.detail,
                "created_at": iso(row.created_at),
            }
            for row in rows
        ]
    }


@app.get("/admin/costs")
def admin_costs(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    runs = db.query(Run).all()
    active_parents = db.query(ParentSandbox).filter(ParentSandbox.state == "RUNNING").count()
    return {
        "run_cost": round(sum(run.cost_estimate or 0 for run in runs), 4),
        "run_count": len(runs),
        "active_parent_hourly_estimate": round(active_parents * settings.parent_cost_per_hour, 4),
        "active_parents": active_parents,
    }


@app.post("/admin/cleanup/reconcile")
def reconcile(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    result = {"execution_containers_destroyed": cleanup_orphans()} | reconcile_parents(db)
    record_audit(db, admin, "system.reconcile", "system", None, detail=result)
    return result


_reconciler_started = False


def _start_reconciler() -> None:
    global _reconciler_started
    if _reconciler_started:
        return
    _reconciler_started = True

    def loop():
        while True:
            time.sleep(60)
            db = SessionLocal()
            try:
                cleanup_orphans()
                reconcile_parents(db)
            except Exception:
                pass
            finally:
                db.close()

    threading.Thread(target=loop, name="aegisrun-reconciler", daemon=True).start()
