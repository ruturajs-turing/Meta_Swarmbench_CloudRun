# AegisRun Foundry Operator Manual

## 1. Product boundary

AegisRun has two separate interfaces:

- Trainers primarily use the local `runnerctl` terminal client; SSH/SFTP is the staged-file fallback.
- Platform operators use the web admin console.

The admin console is not a trainer task form. The parent workspace is not the orchestrator. The control plane creates child containers, injects secrets, enforces quotas, stores events, finalizes artifacts, and destroys execution containers.

## 2. Components

| Component | Local implementation | Responsibility |
| --- | --- | --- |
| Access gateway | AsyncSSH on port `2222` | password auth, terminal menu, SFTP chroot |
| Parent workspace | managed Docker container | durable trainer workspace with maintained Harbor/OpenCode image |
| Control plane | FastAPI + Postgres | auth, users, quotas, task bundles, runs, audit, costs |
| Child execution | one Docker container per run | execute validated TOML resources and stream output |
| Durable results | local storage, S3-shaped layout | preserve bundles, run outputs, result packages |
| Operator console | React/Vite | manage the whole fleet without entering a sandbox |

## 3. Trainer workflow

1. Operator creates a trainer account and shares the control-plane endpoint.
2. Trainer runs `runnerctl connect --endpoint <url> --user <username>` in one local terminal.
3. Password authentication creates, resumes, or repairs the trainer's single parent workspace.
4. Trainer selects `Start a task from this computer` and enters a local task-folder path.
5. `runnerctl` excludes old execution logs, creates a bundle, and streams it to `POST /v1/tasks/submit`.
6. The control plane validates `task.toml`, records the bundle in the parent workspace, and atomically queues the run.
7. The terminal displays the exact TOML section, CPU, RAM, disk policy, and timeout resolved by the server.
8. The run waits in the trainer queue if the active-child limit is already reached.
9. A child container starts with the resolved CPU and memory limits; `SANDBOX_CREATED` records Docker's effective limits.
10. Run events and stdout stream back into the same terminal.
11. Result directories are packaged and copied to parent `/runs` and `/downloads`.
12. The child is destroyed, and the trainer can install generated outputs into the original task folder, download only the archive, or leave it in the parent workspace before returning to the same menu. Installation replaces only `execution_logs`, `logs`, `results`, and `artifacts`.

Raw SSH cannot read arbitrary files from a trainer's local computer. Its menu therefore operates only on files already staged under `/incoming`; it no longer presents SFTP as a required second-window step.

## 4. Operator workflows

### Create a trainer

Open `Users`, select `Create user`, issue a username, email, temporary password, and `trainer` role. The default quota allows two active child runs.

### Provision a parent

Parent creation normally happens on first trainer login. Operators can provision it manually from `Users` or `Workspaces`.

A successful parent has:

- a provider container ID;
- state `RUNNING`;
- maintained template version;
- CPU, RAM, and storage policy;
- a mounted workspace path;
- refresh and last-active timestamps.

### Pause, resume, refresh, destroy

- `pause`: pauses the real Docker parent and preserves workspace state.
- `resume`: unpauses or starts the existing container; missing containers are repaired.
- `refresh`: removes the old container and recreates it from the current managed image while preserving mounted files.
- `destroy`: removes the container but leaves durable task and result files.

Refresh and destroy return `409` while child executions are active.

### Inspect and operate a run

Select a row in `Runs`. The inspector shows trainer, parent, child, resources, state, times, exit code, cleanup state, cost, result packages, event timeline, and model stdout.

- Active runs can be stopped.
- Terminal runs can be retried with the same bundle/resources/mode.
- Force cleanup reconciles any remaining child container.
- Artifacts download with authenticated API access.

### Disable a trainer

Set account state to `disabled`. Future API and SSH authentication fails. Resetting a password revokes existing API sessions.

## 5. State models

Parent states:

```text
PROVISIONING -> RUNNING -> PAUSED -> RUNNING
RUNNING -> REFRESHING -> RUNNING
RUNNING/PAUSED -> DESTROYED
any provider failure -> ERROR -> repair/provision -> RUNNING
```

Run states:

```text
QUEUED -> PROVISIONING -> STAGING_INPUTS -> RUNNING
        -> COLLECTING_OUTPUTS -> SUCCEEDED | FAILED
active -> CANCELLED
running -> TIMED_OUT
provider/platform error -> INFRA_FAILED
terminal -> cleanup_state DESTROYED
```

## 6. Resource and quota behavior

The parent default is 2 CPU, 6144 MB memory, and a 25 GB storage policy. Docker enforces CPU and memory for local testing. Storage size is tracked as policy; production providers must enforce it natively.

SwarmBench child CPU and memory come from `[environment]` in `task.toml`. Generic child resources come from `[resources]`. Exact requests up to the local adapter limit of 16 CPU and 32 GB RAM are retained; unsupported requests fail validation rather than falling back to defaults. Run timeout cannot exceed the trainer quota.

## 7. Secrets

Provider keys live only in control-plane environment configuration. Parent containers do not receive Fireworks credentials. Harbor child containers receive `FIREWORKS_API_KEY` and the same value as `OPENAI_API_KEY` only for the duration of the run.

The UI reports whether a credential is configured but never returns or displays the value.

## 8. Cleanup and reconciliation

The normal child finalizer:

1. collects `logs`, `results`, `artifacts`, and `execution_logs`;
2. writes the artifact archive;
3. copies it into the parent workspace;
4. updates Postgres;
5. removes the child container;
6. records `SANDBOX_DESTROYED`.

The reconciler runs every minute and is also available in `Runtime`. It removes orphaned terminal child containers, pauses idle parents, refreshes due parents, and retries errored parents.

## 9. Incident checks

| Symptom | Check | Corrective action |
| --- | --- | --- |
| SSH password rejected | API `/v1/sessions`, gateway logs, account state | reset password or restore gateway/API connectivity |
| Parent `ERROR` | parent inspector error and Docker image availability | build/pull image, then resume or refresh |
| Run stays `QUEUED` | trainer active-run quota | wait, stop another run, or change quota |
| Child missing after terminal run | expected | children are intentionally destroyed after finalization |
| No result package | event timeline and `failure_reason` | repair artifact collection and force cleanup |
| Harbor blocked | Runtime readiness | enable runtime and provide valid Fireworks key |
| Fireworks 401 | exact child preflight log | replace invalid provider key before retrying |

## 10. Internal test checklist

- API test suite passes in Python 3.12 container.
- Admin login succeeds; trainer cannot open admin UI.
- Trainer login creates a real labeled parent container.
- `runnerctl connect` accepts a local path and stays in one terminal through upload, execution, and result handling.
- Atomic task submission returns the authoritative TOML resource resolution.
- SFTP chroot exposes only the trainer's workspace, and staged uploads remain available in raw SSH.
- A run creates a labeled child with requested and effective Docker resource events.
- Events appear while the child runs.
- Result package appears in parent `/runs` and `/downloads`.
- Child is absent from Docker after completion.
- Parent pause/resume changes actual provider state.
- Parent refresh changes the container ID and preserves workspace files.
- User create/update/password reset and quota mutation are audited.
- Run stop/retry/cleanup actions return visible state changes.
- Web production build passes.
