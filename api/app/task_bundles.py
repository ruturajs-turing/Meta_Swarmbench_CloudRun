import hashlib
import shutil
import tarfile
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from .models import ParentSandbox, Quota, TaskBundle, User
from .parent_runtime import workspace_path
from .settings import settings
from .toml_validator import validate_task_toml


def bundle_storage(bundle_id: str) -> Path:
    return Path(settings.storage_root).resolve() / "bundles" / bundle_id


def create_task_bundle(db: Session, user: User, parent: ParentSandbox, upload: UploadFile) -> TaskBundle:
    quota = db.query(Quota).filter(Quota.user_id == user.id).first()
    bundle = TaskBundle(
        user_id=user.id,
        parent_sandbox_id=parent.id,
        name=upload.filename or "task-bundle.tar.gz",
        task_name="pending",
        uri="pending",
        workspace_uri="pending",
        task_toml="",
        state="UPLOADING",
    )
    db.add(bundle)
    db.commit()

    dest_dir = bundle_storage(bundle.id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    archive = dest_dir / "task-bundle.tar.gz"
    size = 0
    digest = hashlib.sha256()
    max_bytes = (quota.max_upload_mb if quota else 2048) * 1024 * 1024
    with archive.open("wb") as fh:
        while chunk := upload.file.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                bundle.state = "REJECTED"
                db.commit()
                raise HTTPException(status_code=413, detail="Task bundle exceeds upload quota")
            digest.update(chunk)
            fh.write(chunk)

    extract_dir = dest_dir / "task"
    extract_dir.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(archive, "r:gz") as tar:
            _safe_extract(tar, extract_dir)
    except (tarfile.TarError, HTTPException) as exc:
        bundle.state = "REJECTED"
        db.commit()
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=400, detail=f"Invalid task bundle archive: {exc}") from exc

    task_toml_path = _find_task_toml(extract_dir)
    task_toml = task_toml_path.read_text()
    normalized = validate_task_toml(task_toml, quota.max_runtime_seconds if quota else 7200)
    task_root = task_toml_path.parent
    parent_task_dir = workspace_path(user.id) / "tasks" / bundle.id
    if parent_task_dir.exists():
        shutil.rmtree(parent_task_dir)
    shutil.copytree(task_root, parent_task_dir)

    bundle.uri = str(archive)
    bundle.workspace_uri = str(parent_task_dir)
    bundle.size_bytes = size
    bundle.sha256 = digest.hexdigest()
    bundle.task_toml = task_toml
    bundle.task_name = normalized.task_name
    bundle.state = "READY"
    db.commit()
    return bundle


def import_staged_task(db: Session, user: User, parent: ParentSandbox, relative_path: str) -> TaskBundle:
    incoming = (workspace_path(user.id) / "incoming").resolve()
    source = (incoming / relative_path).resolve()
    if not str(source).startswith(str(incoming)) or not source.exists():
        raise HTTPException(status_code=404, detail="Staged task was not found")
    if source.is_file() and source.name.endswith((".tar.gz", ".tgz")):
        with source.open("rb") as fh:
            upload = UploadFile(filename=source.name, file=fh)
            return create_task_bundle(db, user, parent, upload)
    if not source.is_dir():
        raise HTTPException(status_code=400, detail="Staged task must be a directory or tar.gz archive")
    tmp = bundle_storage("staging") / f"{user.id}.tar.gz"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tmp, "w:gz") as tar:
        for item in source.rglob("*"):
            tar.add(item, arcname=item.relative_to(source))
    with tmp.open("rb") as fh:
        upload = UploadFile(filename=f"{source.name}.tar.gz", file=fh)
        bundle = create_task_bundle(db, user, parent, upload)
    tmp.unlink(missing_ok=True)
    return bundle


def materialize_task_bundle(bundle: TaskBundle, task_dir: Path) -> None:
    src = Path(bundle.workspace_uri)
    if not src.exists():
        raise FileNotFoundError(f"Task bundle files not found for {bundle.id}")
    shutil.copytree(src, task_dir, dirs_exist_ok=True)


def _find_task_toml(root: Path) -> Path:
    direct = root / "task.toml"
    if direct.exists():
        return direct
    matches = list(root.rglob("task.toml"))
    if len(matches) != 1:
        raise HTTPException(status_code=400, detail="Task bundle must contain exactly one task.toml")
    return matches[0]


def _safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
    dest_resolved = dest.resolve()
    for member in tar.getmembers():
        if member.issym() or member.islnk():
            raise HTTPException(status_code=400, detail="Task bundle cannot contain links")
        target = (dest / member.name).resolve()
        if not str(target).startswith(str(dest_resolved)):
            raise HTTPException(status_code=400, detail="Task bundle contains unsafe paths")
    tar.extractall(dest)
