import hashlib
import json
import os
import shutil
import tarfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import docker
from docker.errors import DockerException
from sqlalchemy.orm import Session

from .db import SessionLocal
from .events import add_event
from .models import ACTIVE_RUN_STATES, TERMINAL_RUN_STATES, Artifact, ParentSandbox, Quota, Run, RunState, TaskBundle
from .parent_runtime import parent_action, workspace_path
from .settings import settings
from .task_bundles import materialize_task_bundle


_runner_lock = threading.Lock()


def run_storage(run_id: str) -> Path:
    return Path(settings.storage_root) / "runs" / run_id


def artifact_storage(run_id: str) -> Path:
    return Path(settings.storage_root) / "artifacts" / run_id


def start_queue_drain() -> None:
    with _runner_lock:
        db = SessionLocal()
        try:
            users = {row.user_id for row in db.query(Run.user_id).filter(Run.state == RunState.QUEUED).all()}
            for user_id in users:
                _drain_user_queue(db, user_id)
        finally:
            db.close()


def _drain_user_queue(db: Session, user_id: str) -> None:
    quota = db.query(Quota).filter(Quota.user_id == user_id).first()
    max_active = quota.max_active_runs if quota else 2
    active = (
        db.query(Run)
        .filter(Run.user_id == user_id, Run.state.in_(ACTIVE_RUN_STATES))
        .count()
    )
    available = max_active - active
    if available <= 0:
        return
    queued = (
        db.query(Run)
        .filter(Run.user_id == user_id, Run.state == RunState.QUEUED)
        .order_by(Run.queued_at.asc())
        .limit(available)
        .all()
    )
    for run in queued:
        run.state = RunState.PROVISIONING
        db.commit()
        thread = threading.Thread(target=_execute_run_thread, args=(run.id,), daemon=True)
        thread.start()


def _execute_run_thread(run_id: str) -> None:
    db = SessionLocal()
    container = None
    started = time.time()
    try:
        run = db.get(Run, run_id)
        if not run:
            return
        execution_mode = run.execution_mode
        if execution_mode == "harbor" and not settings.harbor_runtime_enabled:
            raise RuntimeError("Real Harbor/OpenCode execution requested, but harbor_runtime_enabled is false")
        parent = db.get(ParentSandbox, run.parent_sandbox_id)
        if not parent:
            raise RuntimeError("Parent workspace is missing")
        if parent.state == "PAUSED":
            parent = parent_action(db, parent, "resume")
        if parent.state != "RUNNING":
            raise RuntimeError(f"Parent workspace is not ready: {parent.state}")
        if execution_mode == "probe":
            add_event(
                db,
                run.id,
                "RUN_STARTED",
                "Run accepted by local Docker adapter in SwarmBench structure-probe mode; no Fireworks/Harbor model calls will be made",
            )
        else:
            add_event(db, run.id, "RUN_STARTED", f"Run accepted by local Docker adapter in {execution_mode} mode")
        run.started_at = datetime.now(timezone.utc)
        run.state = RunState.STAGING_INPUTS
        db.commit()

        workdir = run_storage(run.id)
        task_dir = workdir / "task"
        task_dir.mkdir(parents=True, exist_ok=True)
        bundle = db.get(TaskBundle, run.task_bundle_id)
        if not bundle or bundle.user_id != run.user_id:
            raise FileNotFoundError(f"Task bundle not found: {run.task_bundle_id}")
        materialize_task_bundle(bundle, task_dir)
        (task_dir / "task.toml").write_text(run.task_toml)
        _write_default_task_files(task_dir, run.normalized_spec)
        add_event(db, run.id, "INPUTS_STAGED", f"Task staged at {task_dir}")

        run.state = RunState.RUNNING
        db.commit()

        client = docker.from_env()
        command = run.normalized_spec["run"]["command"]
        timeout = int(run.normalized_spec["run"]["timeout_seconds"])
        runner_image = settings.harbor_runner_image if execution_mode == "harbor" else settings.runner_image
        resource_source = run.normalized_spec.get("_aegisrun", {}).get("resource_source", {})
        source_section = resource_source.get("section", "resources")
        add_event(
            db,
            run.id,
            "TASK_CONFIG_RESOLVED",
            (
                f"task.toml [{source_section}] resolved to {run.cpu} CPU / "
                f"{run.memory_mb} MB / {run.disk_gb} GB, timeout {timeout}s"
            ),
            payload={
                "source": "task.toml",
                "source_fields": resource_source,
                "cpu": run.cpu,
                "memory_mb": run.memory_mb,
                "disk_gb": run.disk_gb,
                "timeout_seconds": timeout,
                "network_egress": run.normalized_spec.get("network", {}).get("egress", "deny"),
            },
        )
        add_event(
            db,
            run.id,
            "SANDBOX_CREATING",
            f"Starting {run.cpu} CPU / {run.memory_mb} MB child from {runner_image}",
            payload={"cpu": run.cpu, "memory_mb": run.memory_mb, "disk_gb": run.disk_gb, "image": runner_image},
        )
        volumes = {str(task_dir.resolve()): {"bind": "/run/task", "mode": "rw"}}
        if execution_mode == "harbor":
            volumes["/var/run/docker.sock"] = {"bind": "/var/run/docker.sock", "mode": "rw"}
        container = client.containers.run(
            runner_image,
            name=f"aegisrun-execution-{run.id}",
            command=["bash", "-lc", command],
            working_dir="/run/task",
            volumes=volumes,
            detach=True,
            mem_limit=f"{run.memory_mb}m",
            nano_cpus=int(run.cpu * 1_000_000_000),
            network_disabled=(
                execution_mode != "harbor"
                and run.normalized_spec.get("network", {}).get("egress", "deny") == "deny"
            ),
            environment=_container_environment(run.normalized_spec),
            labels={
                "managed_by": "aegisrun",
                "run_id": run.id,
                "parent_id": run.parent_sandbox_id,
                "user_id": run.user_id,
                "sandbox_role": "execution",
                "resource_source": "task.toml",
            },
        )
        run.container_id = container.id[:12]
        db.commit()
        container.reload()
        host_config = container.attrs.get("HostConfig", {})
        effective_memory_mb = int(host_config.get("Memory", 0)) // (1024 * 1024)
        effective_cpu = float(host_config.get("NanoCpus", 0)) / 1_000_000_000
        add_event(
            db,
            run.id,
            "SANDBOX_CREATED",
            (
                f"Container {run.container_id} started with Docker limits "
                f"{effective_cpu:g} CPU / {effective_memory_mb} MB"
            ),
            payload={
                "container_id": run.container_id,
                "effective_cpu": effective_cpu,
                "effective_memory_mb": effective_memory_mb,
                "requested_disk_gb": run.disk_gb,
            },
        )

        exit_code = _stream_until_done(db, run, container, timeout)
        run = db.get(Run, run_id)
        if run.state == RunState.CANCELLED:
            add_event(db, run.id, "RUN_CANCELLED", "Run cancelled")
        else:
            run.exit_code = exit_code
            run.passed = _read_passed(task_dir, run.normalized_spec, exit_code)
            run.state = RunState.COLLECTING_OUTPUTS
            db.commit()
            _collect_artifacts(db, run, task_dir)
            run.state = RunState.SUCCEEDED if exit_code == 0 and run.passed else RunState.FAILED
            add_event(db, run.id, "RUN_COMPLETED", f"Run exited with code {exit_code}", payload={"passed": run.passed})
        run.finished_at = datetime.now(timezone.utc)
        run.duration_seconds = int(time.time() - started)
        run.cost_estimate = round((run.duration_seconds / 60) * settings.run_cost_per_minute, 4)
        parent.last_active_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:  # noqa: BLE001 - run finalizer must catch all
        run = db.get(Run, run_id)
        if run:
            run.state = RunState.INFRA_FAILED
            run.failure_reason = str(exc)
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
            add_event(db, run.id, "INFRA_FAILED", str(exc))
    finally:
        try:
            if container is not None:
                container.remove(force=True)
        except DockerException as exc:
            run = db.get(Run, run_id)
            if run:
                run.cleanup_state = "FAILED"
                db.commit()
                add_event(db, run.id, "CLEANUP_FAILED", str(exc))
        else:
            run = db.get(Run, run_id)
            if run:
                run.cleanup_state = "DESTROYED"
                db.commit()
                add_event(db, run.id, "SANDBOX_DESTROYED", "Execution container destroyed")
        user_id = db.get(Run, run_id).user_id if db.get(Run, run_id) else None
        db.close()
        if user_id:
            start_queue_drain()


def _stream_until_done(db: Session, run: Run, container, timeout: int) -> int:
    deadline = time.time() + timeout
    logs = container.logs(stream=True, follow=True)
    for raw in logs:
        if time.time() > deadline:
            container.kill()
            run.state = RunState.TIMED_OUT
            db.commit()
            add_event(db, run.id, "RUN_TIMED_OUT", f"Run exceeded {timeout}s")
            return 124
        line = raw.decode("utf-8", errors="replace").rstrip()
        if line:
            add_event(db, run.id, "LOG", line, stream="stdout")
    result = container.wait()
    return int(result.get("StatusCode", 1))


def _container_environment(spec: dict) -> dict[str, str]:
    env = {str(key): str(value) for key, value in spec.get("env", {}).items()}
    if spec.get("_aegisrun", {}).get("task_type") == "swarmbench-harbor":
        fireworks_key = os.environ.get("FIREWORKS_API_KEY")
        if fireworks_key:
            env["FIREWORKS_API_KEY"] = fireworks_key
            env.setdefault("OPENAI_API_KEY", fireworks_key)
    secret_map = {
        "vault://local/fireworks_api_key": "FIREWORKS_API_KEY",
        "vault://env/FIREWORKS_API_KEY": "FIREWORKS_API_KEY",
    }
    for target_name, secret_ref in spec.get("secrets", {}).items():
        env_name = secret_map.get(str(secret_ref))
        if not env_name:
            continue
        value = os.environ.get(env_name)
        if value:
            env[str(target_name)] = value
    if os.environ.get("FIREWORKS_MODEL"):
        env.setdefault("FIREWORKS_MODEL", os.environ["FIREWORKS_MODEL"])
    return env


def _write_default_task_files(task_dir: Path, spec: dict) -> None:
    (task_dir / "results").mkdir(exist_ok=True)
    (task_dir / "artifacts").mkdir(exist_ok=True)
    if spec.get("_aegisrun", {}).get("task_type") == "swarmbench-harbor":
        (task_dir / ".aegisrun_harbor_commands.json").write_text(
            json.dumps(spec.get("_aegisrun", {}).get("harbor_commands", {}), indent=2)
        )
        if spec.get("_aegisrun", {}).get("execution_mode") == "harbor":
            (task_dir / ".aegisrun_harbor_run.sh").write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "mkdir -p results artifacts execution_logs\n"
                "if [ -z \"${FIREWORKS_API_KEY:-}\" ]; then\n"
                "  echo 'FIREWORKS_API_KEY was not injected into the execution sandbox' >&2\n"
                "  exit 64\n"
                "fi\n"
                "python - <<'PY'\n"
                "from pathlib import Path\n"
                "import json, time\n"
                "Path('results').mkdir(exist_ok=True)\n"
                "Path('artifacts').mkdir(exist_ok=True)\n"
                "Path('artifacts/harbor_commands.json').write_text(Path('.aegisrun_harbor_commands.json').read_text())\n"
                "Path('results/summary.json').write_text(json.dumps({'passed': False, 'mode': 'swarmbench-harbor', 'stage': 'preflight', 'started_at_epoch': time.time()}, indent=2))\n"
                "PY\n"
                "python - <<'PY'\n"
                "import json\n"
                "import os\n"
                "import urllib.error\n"
                "import urllib.request\n"
                "payload = {\n"
                "    'model': 'accounts/fireworks/models/kimi-k2p6',\n"
                "    'messages': [{'role': 'user', 'content': 'Return exactly ok'}],\n"
                "    'max_tokens': 4,\n"
                "    'temperature': 0,\n"
                "}\n"
                "req = urllib.request.Request(\n"
                "    'https://api.fireworks.ai/inference/v1/chat/completions',\n"
                "    data=json.dumps(payload).encode('utf-8'),\n"
                "    headers={\n"
                "        'Authorization': 'Bearer ' + os.environ['FIREWORKS_API_KEY'],\n"
                "        'Content-Type': 'application/json',\n"
                "    },\n"
                "    method='POST',\n"
                ")\n"
                "try:\n"
                "    with urllib.request.urlopen(req, timeout=30) as response:\n"
                "        response.read(256)\n"
                "except urllib.error.HTTPError as exc:\n"
                "    body = exc.read(300).decode('utf-8', errors='replace').replace('\\n', ' ')\n"
                "    raise SystemExit(f'Fireworks preflight failed before Harbor launch: HTTP {exc.code}: {body}') from exc\n"
                "except Exception as exc:\n"
                "    raise SystemExit(f'Fireworks preflight failed before Harbor launch: {type(exc).__name__}: {exc}') from exc\n"
                "print('Fireworks preflight passed for accounts/fireworks/models/kimi-k2p6')\n"
                "PY\n"
                "check_harbor_result() {\n"
                "  local label=\"$1\"\n"
                "  local path=\"$2\"\n"
                "  python - \"$label\" \"$path\" <<'PY'\n"
                "from pathlib import Path\n"
                "import json, sys\n"
                "label, path = sys.argv[1], Path(sys.argv[2])\n"
                "if not path.exists():\n"
                "    raise SystemExit(f'{label}: missing Harbor result file: {path}')\n"
                "data = json.loads(path.read_text())\n"
                "stats = data.get('stats') or {}\n"
                "errors = int(stats.get('n_errored_trials') or 0)\n"
                "eval_errors = 0\n"
                "eval_trials = 0\n"
                "for item in (stats.get('evals') or {}).values():\n"
                "    eval_errors += int(item.get('n_errors') or 0)\n"
                "    eval_trials += int(item.get('n_trials') or 0)\n"
                "if errors or eval_errors or eval_trials == 0:\n"
                "    raise SystemExit(f'{label}: Harbor reported errors={errors}, eval_errors={eval_errors}, eval_trials={eval_trials}')\n"
                "print(f'{label}: Harbor result passed with eval_trials={eval_trials}')\n"
                "PY\n"
                "}\n"
                "python - <<'PY'\n"
                "from pathlib import Path\n"
                "import json, time\n"
                "Path('results').mkdir(exist_ok=True)\n"
                "Path('artifacts').mkdir(exist_ok=True)\n"
                "Path('artifacts/harbor_commands.json').write_text(Path('.aegisrun_harbor_commands.json').read_text())\n"
                "Path('results/summary.json').write_text(json.dumps({'passed': False, 'mode': 'swarmbench-harbor', 'started_at_epoch': time.time()}, indent=2))\n"
                "PY\n"
                "echo 'Starting real SwarmBench Harbor/OpenCode model-log run'\n"
                "if [ -f /run/task/solution/solve.sh ]; then\n"
                "  harbor run -p /run/task -a oracle --job-name oracle --jobs-dir /run/task/execution_logs --ve FIREWORKS_API_KEY=\"$FIREWORKS_API_KEY\"\n"
                "  check_harbor_result oracle /run/task/execution_logs/oracle/result.json\n"
                "else\n"
                "  echo 'Skipping oracle: /run/task/solution/solve.sh is not present in this task package'\n"
                "fi\n"
                "harbor run -p /run/task -a swarm-opencode-single -m fireworks_ai/accounts/fireworks/models/kimi-k2p6 -k 1 -n 1 --job-name single-opencode-agent --jobs-dir /run/task/execution_logs --ve FIREWORKS_API_KEY=\"$FIREWORKS_API_KEY\" --ae FIREWORKS_API_KEY=\"$FIREWORKS_API_KEY\" --quiet\n"
                "check_harbor_result single /run/task/execution_logs/single-opencode-agent/result.json\n"
                "harbor run -p /run/task -a swarm-opencode-multi -m fireworks_ai/accounts/fireworks/models/kimi-k2p6 -k 1 -n 1 --job-name multi-opencode-agent --jobs-dir /run/task/execution_logs --ve FIREWORKS_API_KEY=\"$FIREWORKS_API_KEY\" --ae FIREWORKS_API_KEY=\"$FIREWORKS_API_KEY\" --quiet\n"
                "check_harbor_result multi /run/task/execution_logs/multi-opencode-agent/result.json\n"
                "python - <<'PY'\n"
                "from pathlib import Path\n"
                "import json, time\n"
                "summary = {'passed': True, 'mode': 'swarmbench-harbor', 'completed_at_epoch': time.time(), 'execution_logs_present': Path('execution_logs').exists()}\n"
                "Path('results/summary.json').write_text(json.dumps(summary, indent=2))\n"
                "PY\n"
            )
            return
        (task_dir / ".aegisrun_swarmbench_probe.py").write_text(
            "from pathlib import Path\n"
            "import json\n"
            "required = ['instruction.md', 'task.toml', 'decomposition.yaml', 'environment', 'tests']\n"
            "missing = [item for item in required if not (Path(item).exists())]\n"
            "summary = {\n"
            "    'passed': not missing,\n"
            "    'mode': 'swarmbench-structure-probe',\n"
            "    'missing': missing,\n"
            "    'has_execution_logs': Path('execution_logs').exists(),\n"
            "    'note': 'No Fireworks/Harbor model calls were made. This local adapter only validated Harbor task bundle shape. Use --mode harbor with a configured Harbor runner image/provider for real model logs.',\n"
            "}\n"
            "Path('results').mkdir(exist_ok=True)\n"
            "Path('artifacts').mkdir(exist_ok=True)\n"
            "Path('results/summary.json').write_text(json.dumps(summary, indent=2))\n"
            "commands_path = Path('.aegisrun_harbor_commands.json')\n"
            "Path('artifacts/harbor_commands.json').write_text(commands_path.read_text() if commands_path.exists() else '{}')\n"
            "print('SwarmBench Harbor task structure probe:', 'PASS' if not missing else 'FAIL', missing)\n"
            "print('MODE: structure probe only; no Fireworks/Harbor model calls were made')\n"
            "raise SystemExit(0 if not missing else 2)\n"
        )
        return
    if spec.get("run", {}).get("command") == "python real_fireworks_eval.py":
        (task_dir / "real_fireworks_eval.py").write_text(
            "from pathlib import Path\n"
            "import json\n"
            "import os\n"
            "import urllib.error\n"
            "import urllib.request\n\n"
            "api_key = os.environ.get('FIREWORKS_API_KEY')\n"
            "model = os.environ.get('FIREWORKS_MODEL', 'accounts/fireworks/models/kimi-k2p5')\n"
            "if not api_key:\n"
            "    raise SystemExit('FIREWORKS_API_KEY was not injected')\n\n"
            "payload = {\n"
            "    'model': model,\n"
            "    'max_tokens': 220,\n"
            "    'temperature': 0,\n"
            "    'messages': [\n"
            "        {'role': 'system', 'content': 'Return only valid JSON. No markdown.'},\n"
            "        {'role': 'user', 'content': 'You are testing a remote execution platform. Return JSON with keys task, verdict, risk_controls, and next_check. risk_controls must be a list of exactly three short strings.'},\n"
            "    ],\n"
            "}\n"
            "request = urllib.request.Request(\n"
            "    'https://api.fireworks.ai/inference/v1/chat/completions',\n"
            "    data=json.dumps(payload).encode('utf-8'),\n"
            "    headers={\n"
            "        'Authorization': 'Bearer ' + api_key,\n"
            "        'Content-Type': 'application/json',\n"
            "    },\n"
            "    method='POST',\n"
            ")\n"
            "try:\n"
            "    with urllib.request.urlopen(request, timeout=60) as response:\n"
            "        raw = response.read().decode('utf-8')\n"
            "except urllib.error.HTTPError as exc:\n"
            "    body = exc.read().decode('utf-8', errors='replace')\n"
            "    raise SystemExit(f'Fireworks HTTP {exc.code}: {body[:500]}') from exc\n"
            "data = json.loads(raw)\n"
            "content = data['choices'][0]['message']['content'].strip()\n"
            "try:\n"
            "    parsed = json.loads(content)\n"
            "except json.JSONDecodeError:\n"
            "    start = content.find('{')\n"
            "    end = content.rfind('}') + 1\n"
            "    parsed = json.loads(content[start:end])\n"
            "if not isinstance(parsed.get('risk_controls'), list) or len(parsed['risk_controls']) != 3:\n"
            "    raise SystemExit('Model response failed risk_controls validation')\n"
            "Path('results').mkdir(exist_ok=True)\n"
            "Path('artifacts').mkdir(exist_ok=True)\n"
            "Path('results/summary.json').write_text(json.dumps({'passed': True, 'model': model, 'validated_keys': sorted(parsed.keys())}, indent=2))\n"
            "Path('artifacts/model_response.json').write_text(json.dumps({'raw': data, 'parsed': parsed}, indent=2))\n"
            "print('Fireworks real model task completed')\n"
        )
        return
    sample = task_dir / "eval.py"
    if not sample.exists():
        sample.write_text(
            "from pathlib import Path\n"
            "import json, time\n"
            "print('AegisRun sample task starting')\n"
            "time.sleep(1)\n"
            "Path('results').mkdir(exist_ok=True)\n"
            "Path('artifacts').mkdir(exist_ok=True)\n"
            "Path('results/summary.json').write_text(json.dumps({'passed': True, 'score': 1.0}, indent=2))\n"
            "Path('artifacts/report.txt').write_text('sample artifact generated by local-docker adapter\\n')\n"
            "print('AegisRun sample task completed')\n"
        )


def _collect_artifacts(db: Session, run: Run, task_dir: Path) -> None:
    dest = artifact_storage(run.id)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    include_dirs = ["logs", "results", "artifacts", "execution_logs"]
    for rel in include_dirs:
        src = task_dir / rel
        if src.exists():
            shutil.copytree(src, dest / rel, dirs_exist_ok=True)
    archive = dest / "artifact-bundle.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for rel in include_dirs:
            src = dest / rel
            if src.exists():
                tar.add(src, arcname=rel)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    parent_result = workspace_path(run.user_id) / "runs" / run.id
    if parent_result.exists():
        shutil.rmtree(parent_result)
    shutil.copytree(dest, parent_result)
    download_copy = workspace_path(run.user_id) / "downloads" / f"{run.id}-result.tar.gz"
    shutil.copy2(archive, download_copy)
    db.add(
        Artifact(
            run_id=run.id,
            kind="result-package",
            path=f"{run.id}-result.tar.gz",
            uri=str(archive),
            size_bytes=archive.stat().st_size,
            sha256=digest,
        )
    )
    run.artifact_uri = str(archive)
    add_event(
        db,
        run.id,
        "RESULT_COPIED_TO_PARENT",
        f"Result package copied to parent workspace at {parent_result}",
        payload={"sha256": digest, "size_bytes": archive.stat().st_size, "workspace_path": str(parent_result)},
    )


def cancel_run(run_id: str) -> bool:
    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        if not run:
            return False
        if run.state in TERMINAL_RUN_STATES:
            return False
        run.state = RunState.CANCELLED
        db.commit()
        if run.container_id:
            client = docker.from_env()
            for container in client.containers.list(all=True, filters={"label": f"run_id={run.id}"}):
                container.remove(force=True)
        add_event(db, run.id, "RUN_CANCELLED", "Cancellation requested")
        return True
    finally:
        db.close()


def cleanup_orphans() -> int:
    client = docker.from_env()
    count = 0
    for container in client.containers.list(all=True, filters={"label": ["managed_by=aegisrun", "sandbox_role=execution"]}):
        run_id = container.labels.get("run_id")
        db = SessionLocal()
        try:
            run = db.get(Run, run_id) if run_id else None
            if not run or run.state in TERMINAL_RUN_STATES:
                container.remove(force=True)
                count += 1
        finally:
            db.close()
    return count


def _read_passed(task_dir: Path, spec: dict, exit_code: int) -> bool:
    if exit_code != 0:
        return False
    result_path = task_dir / str(spec.get("run", {}).get("result_file", "results/summary.json"))
    if not result_path.exists():
        return True
    try:
        payload = json.loads(result_path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return bool(payload.get("passed", True))
