import shutil
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import docker
from docker.errors import DockerException, ImageNotFound, NotFound
from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import ACTIVE_RUN_STATES, ParentSandbox, Quota, Run, User
from .settings import settings


_parent_provision_lock = threading.RLock()


def workspace_path(user_id: str) -> Path:
    root = Path(settings.storage_root).resolve() / "workspaces" / user_id
    for name in ("incoming", "tasks", "runs", "downloads", "tmp"):
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def current_parent(db: Session, user_id: str) -> ParentSandbox | None:
    return (
        db.query(ParentSandbox)
        .filter(ParentSandbox.user_id == user_id, ParentSandbox.state != "DESTROYED")
        .order_by(ParentSandbox.created_at.desc())
        .first()
    )


def ensure_parent(db: Session, user: User) -> ParentSandbox:
    parent = current_parent(db, user.id)
    if parent and parent.state not in {"ERROR", "DESTROYED"}:
        _sync_parent_state(db, parent)
        if parent.state == "PAUSED":
            return parent_action(db, parent, "resume")
        if parent.state == "RUNNING":
            parent.last_active_at = datetime.now(timezone.utc)
            db.commit()
            return parent
    return provision_parent(db, user, replace=parent)


def provision_parent(
    db: Session,
    user: User,
    *,
    replace: ParentSandbox | None = None,
    provider: str = "local-docker",
) -> ParentSandbox:
    with _parent_provision_lock:
        quota = db.query(Quota).filter(Quota.user_id == user.id).first() or Quota(user_id=user.id)
        if quota.id is None:
            db.add(quota)
            db.flush()
        root = workspace_path(user.id)
        parent = replace or ParentSandbox(
            user_id=user.id,
            provider=provider,
            workspace_uri=str(root),
            cpu=quota.parent_cpu,
            memory_mb=quota.parent_memory_mb,
            disk_gb=quota.parent_disk_gb,
            template_version=settings.parent_template_version,
        )
        if replace is None:
            db.add(parent)
            db.flush()
        parent.state = "PROVISIONING"
        parent.error = None
        parent.workspace_uri = str(root)
        parent.cpu = quota.parent_cpu
        parent.memory_mb = quota.parent_memory_mb
        parent.disk_gb = quota.parent_disk_gb
        parent.template_version = settings.parent_template_version
        db.commit()

        try:
            client = docker.from_env()
            container = _create_or_reuse_parent_container(client, parent, user, root)
        except (DockerException, ImageNotFound) as exc:
            parent.state = "ERROR"
            parent.error = str(exc)
            db.commit()
            return parent

        now = datetime.now(timezone.utc)
        parent.container_id = container.id[:12]
        parent.state = "RUNNING"
        parent.started_at = now
        parent.last_active_at = now
        parent.paused_at = None
        parent.refresh_after_at = now + timedelta(hours=settings.parent_refresh_hours)
        db.commit()
        return parent


def _create_or_reuse_parent_container(client, parent: ParentSandbox, user: User, root: Path):
    name = f"aegisrun-parent-{parent.id}"
    try:
        container = client.containers.get(name)
    except NotFound:
        return client.containers.run(
            settings.parent_image,
            name=name,
            command=[
                "bash",
                "-lc",
                "mkdir -p /workspace/{incoming,tasks,runs,downloads,tmp}; "
                "echo ready > /workspace/.aegisrun-ready; "
                "trap 'exit 0' TERM INT; while true; do sleep 300; done",
            ],
            working_dir="/workspace",
            volumes={str(root): {"bind": "/workspace", "mode": "rw"}},
            detach=True,
            mem_limit=f"{parent.memory_mb}m",
            nano_cpus=int(parent.cpu * 1_000_000_000),
            labels={
                "managed_by": "aegisrun",
                "sandbox_role": "parent",
                "parent_id": parent.id,
                "user_id": user.id,
                "template_version": parent.template_version,
            },
        )

    labels = container.labels or {}
    if labels.get("managed_by") != "aegisrun" or labels.get("parent_id") != parent.id:
        raise DockerException(f"Container name {name} is owned by another workload")
    container.reload()
    if container.status == "paused":
        container.unpause()
    elif container.status != "running":
        container.start()
    return container


def parent_action(db: Session, parent: ParentSandbox, action: str) -> ParentSandbox:
    if action not in {"resume", "pause", "refresh", "destroy"}:
        raise HTTPException(status_code=404, detail="Unknown parent action")
    active = db.query(Run).filter(Run.parent_sandbox_id == parent.id, Run.state.in_(ACTIVE_RUN_STATES)).count()
    if action in {"refresh", "destroy"} and active:
        raise HTTPException(status_code=409, detail=f"Parent has {active} active execution(s)")

    client = docker.from_env()
    try:
        container = _find_container(client, parent)
        if action == "pause":
            if container and container.status == "running":
                container.pause()
            parent.state = "PAUSED"
            parent.paused_at = datetime.now(timezone.utc)
        elif action == "resume":
            if not container:
                user = db.get(User, parent.user_id)
                return provision_parent(db, user, replace=parent)
            container.reload()
            if container.status == "paused":
                container.unpause()
            elif container.status != "running":
                container.start()
            parent.state = "RUNNING"
            parent.paused_at = None
            parent.last_active_at = datetime.now(timezone.utc)
        elif action == "refresh":
            parent.state = "REFRESHING"
            db.commit()
            if container:
                container.remove(force=True)
            user = db.get(User, parent.user_id)
            return provision_parent(db, user, replace=parent)
        elif action == "destroy":
            if container:
                container.remove(force=True)
            parent.state = "DESTROYED"
            parent.container_id = None
            parent.paused_at = None
    except DockerException as exc:
        parent.state = "ERROR"
        parent.error = str(exc)
        db.commit()
        raise HTTPException(status_code=502, detail=f"Docker lifecycle action failed: {exc}") from exc
    db.commit()
    return parent


def parent_stats(parent: ParentSandbox) -> dict:
    if not parent.container_id:
        return {"available": False, "state": parent.state}
    try:
        container = docker.from_env().containers.get(parent.container_id)
        raw = container.stats(stream=False)
        memory = raw.get("memory_stats", {})
        usage = int(memory.get("usage", 0))
        cache = int(memory.get("stats", {}).get("cache", 0))
        limit = int(memory.get("limit", 0))
        cpu = raw.get("cpu_stats", {})
        pre = raw.get("precpu_stats", {})
        cpu_delta = int(cpu.get("cpu_usage", {}).get("total_usage", 0)) - int(pre.get("cpu_usage", {}).get("total_usage", 0))
        system_delta = int(cpu.get("system_cpu_usage", 0)) - int(pre.get("system_cpu_usage", 0))
        online = int(cpu.get("online_cpus") or len(cpu.get("cpu_usage", {}).get("percpu_usage", [])) or 1)
        cpu_pct = (cpu_delta / system_delta * online * 100) if system_delta > 0 and cpu_delta > 0 else 0
        return {
            "available": True,
            "state": container.status.upper(),
            "cpu_percent": round(cpu_pct, 2),
            "memory_used_bytes": max(0, usage - cache),
            "memory_limit_bytes": limit,
            "pids": int(raw.get("pids_stats", {}).get("current", 0)),
        }
    except (DockerException, NotFound) as exc:
        return {"available": False, "state": parent.state, "error": str(exc)}


def reconcile_parents(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    paused = 0
    refreshed = 0
    repaired = 0
    for parent in db.query(ParentSandbox).filter(ParentSandbox.state != "DESTROYED").all():
        _sync_parent_state(db, parent)
        active = db.query(Run).filter(Run.parent_sandbox_id == parent.id, Run.state.in_(ACTIVE_RUN_STATES)).count()
        if parent.state == "RUNNING" and not active and parent.last_active_at <= now - timedelta(minutes=settings.parent_idle_minutes):
            parent_action(db, parent, "pause")
            paused += 1
        elif parent.refresh_after_at and parent.refresh_after_at <= now and not active:
            parent_action(db, parent, "refresh")
            refreshed += 1
        elif parent.state == "ERROR" and not active:
            user = db.get(User, parent.user_id)
            provision_parent(db, user, replace=parent)
            repaired += 1
    return {"paused": paused, "refreshed": refreshed, "repaired": repaired}


def delete_workspace(parent: ParentSandbox) -> None:
    if parent.state != "DESTROYED":
        raise RuntimeError("Parent must be destroyed before deleting its workspace")
    shutil.rmtree(parent.workspace_uri, ignore_errors=True)


def _sync_parent_state(db: Session, parent: ParentSandbox) -> None:
    if not parent.container_id or parent.state in {"DESTROYED", "ERROR"}:
        return
    try:
        container = docker.from_env().containers.get(parent.container_id)
        container.reload()
    except (DockerException, NotFound):
        parent.state = "ERROR"
        parent.error = "Parent container is missing from the provider"
    else:
        parent.state = {"running": "RUNNING", "paused": "PAUSED", "created": "PROVISIONING"}.get(
            container.status, "ERROR"
        )
    db.commit()


def _find_container(client, parent: ParentSandbox):
    if parent.container_id:
        try:
            return client.containers.get(parent.container_id)
        except NotFound:
            pass
    rows = client.containers.list(all=True, filters={"label": f"parent_id={parent.id}"})
    return rows[0] if rows else None
