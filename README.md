# AegisRun Foundry

AegisRun Foundry is an internal remote-execution platform for SwarmBench trainers and platform operators.

Trainers use the local `runnerctl` terminal client against the managed endpoint. Raw SSH/SFTP remains a staged-file fallback. Operators use the web control plane. The web app does not accept trainer task submissions.

## Verified product flow

```text
Trainer runs runnerctl connect and enters credentials
  -> local terminal client authenticates against the control plane
  -> one real parent Docker workspace is created or resumed
  -> trainer enters a task-folder path visible on their computer
  -> runnerctl bundles and uploads that folder in the same terminal
  -> task.toml is validated and normalized
  -> resolved TOML resources are shown before child creation
  -> one short-lived child container is created with those exact CPU/RAM limits
  -> Harbor/probe logs stream into run events
  -> results are copied to the parent /runs and /downloads directories
  -> durable artifact package is registered in Postgres/storage
  -> child container is destroyed
```

The control plane owns provider credentials, quotas, lifecycle actions, audit records, and cleanup. Parent containers never receive Docker control or admin credentials. Fireworks credentials are injected only into Harbor child runs.

## Local endpoints

| Surface | Endpoint | Audience |
| --- | --- | --- |
| Operator console | `http://localhost:5177` | platform admins |
| Control-plane API | `http://localhost:18080` | CLI, gateway, admin UI |
| Interactive API docs | `http://localhost:18080/docs` | developers/operators |
| Trainer SSH | `ssh -p 2222 trainer@localhost` | trainers |
| Trainer SFTP | `sftp -P 2222 trainer@localhost` | trainers |

Seeded local accounts:

| Role | Username | Password |
| --- | --- | --- |
| Platform admin | `admin` | `aegisrun` |
| Demo trainer | `trainer` | `trainer123` |

These credentials are development-only.

> **Internal-test boundary:** this Compose stack mounts the Docker socket, seeds known demo credentials, and uses local filesystem storage. It is appropriate for isolated local validation only. Read [the implementation audit](docs/implementation-audit.md) and [security policy](SECURITY.md) before any shared deployment.

## Start

The managed parent image contains patched Harbor and OpenCode. From the AegisRun repository root, prepare the pinned Harbor checkout and apply the included patch once:

```bash
git clone https://github.com/harbor-framework/harbor.git ../harbor
git -C ../harbor checkout e70d5f060ffeb4525f320669d50b290925b55425
git -C ../harbor apply "$PWD/patches/swarmbench_harbor_changes.diff"

docker build \
  -f runtimes/harbor-runner/Dockerfile \
  -t aegisrun/harbor-runner:local \
  ../harbor

docker compose up -d --build
```

Open `http://localhost:5177` and sign in as `admin`.

## Trainer workflow

From the AegisRun repository root, launch the single-window client:

```bash
AEGISRUN_HOME=/tmp/aegisrun-trainer ./cli/runnerctl connect \
  --endpoint http://localhost:18080 \
  --user trainer
```

After the password prompt, select `Start a task from this computer` and enter the task folder path. The client performs this sequence without opening SSH or a second terminal:

```text
local path -> bundle/upload -> task.toml validation -> resource preview
           -> child creation -> live events/logs -> install/download result prompt
```

For automation, `./cli/runnerctl run /path/to/task --follow` uses the same atomic API. `./cli/runnerctl install <run_id> /path/to/task` safely replaces only generated output directories. Raw `ssh -p 2222 trainer@localhost` can manage tasks already staged in the parent workspace, but cannot read a laptop path because that path does not exist on the remote host.

## Operator console

The admin UI is organized around operational records:

| View | Operations |
| --- | --- |
| Overview | provider connectivity, fleet lineage, attention queue, recent runs, cost posture |
| Workspaces | filter parent containers, inspect telemetry, pause, resume, refresh, destroy, provision |
| Runs | filter child executions, inspect events/logs/artifacts, stop, retry, force cleanup |
| Users | issue credentials, edit roles/state, reset passwords, set quotas and parent capacity |
| Runtime | inspect images, Docker/Harbor/Fireworks readiness, terminal commands, run reconciler |
| Audit | inspect append-only operator mutations |

The signature view is the live lineage:

```text
trainer -> parent workspace -> active child execution -> result package
```

## Runtime modes

`probe` runs the task package in a short-lived local Docker child without model calls. It verifies the platform lifecycle and package shape.

`harbor` runs the patched Harbor/OpenCode workflow. Enable it only with the managed runner image and a valid Fireworks key:

```bash
AEGISRUN_HARBOR_RUNTIME_ENABLED=true \
AEGISRUN_HARBOR_RUNNER_IMAGE=aegisrun/harbor-runner:local \
AEGISRUN_PARENT_IMAGE=aegisrun/harbor-runner:local \
FIREWORKS_API_KEY=<valid-key> \
docker compose up -d --build api gateway web
```

SwarmBench execution uses:

```text
single: swarm-opencode-single -m fireworks_ai/accounts/fireworks/models/kimi-k2p6
multi : swarm-opencode-multi  -m fireworks_ai/accounts/fireworks/models/kimi-k2p6
```

The patched OpenCode agents keep thinking enabled.

## Storage layout

```text
storage/
  bundles/<bundle_id>/
  runs/<run_id>/task/
  artifacts/<run_id>/artifact-bundle.tar.gz
  workspaces/<user_id>/
    incoming/
    tasks/<bundle_id>/
    runs/<run_id>/
    downloads/<run_id>-result.tar.gz
    tmp/
```

Postgres is the system of record. Local filesystem storage stands in for S3 during internal testing.

## Lifecycle policies

| Policy | Default |
| --- | ---: |
| Parent workspaces per trainer | 1 |
| Active child runs per trainer | 2 |
| Queued runs per trainer | 10 |
| Parent capacity | 2 CPU, 6 GB RAM, 25 GB storage policy |
| Parent idle pause | 15 minutes |
| Parent refresh | 24 hours |
| Child cleanup | after result finalization |

Refresh and destroy are blocked while the parent has active child runs.

## Verification

```bash
docker compose ps
docker compose exec -T api python -m pytest -q
docker compose exec -T web npm run build
python3 scripts/e2e_admin_api.py
```

The E2E script logs in with the seeded local accounts and verifies user management, quota updates, parent pause/resume/refresh, run inventory, provider health, audit events, and cost reporting. Override `AEGISRUN_ENDPOINT`, `AEGISRUN_ADMIN_USER`, `AEGISRUN_ADMIN_PASSWORD`, `AEGISRUN_TRAINER_USER`, and `AEGISRUN_TRAINER_PASSWORD` when the local defaults have changed.

The full publication and deployment gates are tracked in [`docs/release-checklist.md`](docs/release-checklist.md). The current capability-to-requirement assessment, including known gaps, is in [`docs/implementation-audit.md`](docs/implementation-audit.md).

## Repository map

| Path | Purpose |
| --- | --- |
| `api/app/main.py` | authenticated trainer and admin API |
| `api/app/parent_runtime.py` | real parent Docker lifecycle and reconciliation |
| `api/app/docker_runner.py` | child queue, execution, events, results, cleanup |
| `api/app/models.py` | Postgres entities and lifecycle states |
| `gateway/app.py` | password-authenticated SSH menu and SFTP chroot |
| `cli/runnerctl.py` | local trainer companion CLI/TUI |
| `web/src/pages/` | operator workflows |
| `specs/database.sql` | implementation-aligned SQL reference |
| `specs/openapi.yaml` | implementation-aligned API reference |
| `docs/endpoint-matrix.md` | role and endpoint matrix |
| `MANUAL.md` | operator and trainer runbook |

Architecture research and future E2B/Daytona adapters remain under `docs/`. Those documents describe the cloud target; this README describes the runnable local implementation.
