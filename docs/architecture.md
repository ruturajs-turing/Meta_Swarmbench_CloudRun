# Architecture

AegisRun Foundry is a multi-tenant remote execution platform with a user-facing workspace and isolated per-run execution sandboxes.

The authoritative trainer-facing design is in `docs/cloud-terminal-architecture-plan.md`. The important correction is that trainers should receive a terminal/SSH endpoint and `runnerctl`, not the internal admin web UI. The web UI is for platform operators managing sandboxes, runs, costs, users, templates, and cleanup.

## Recommended Architecture

The platform should not let the parent sandbox own orchestration, provider credentials, billing, cleanup, or admin controls. The parent sandbox is a user workspace. The control plane is the authority.

```text
User Terminal / IDE / CLI
  -> Access Gateway / Terminal Broker
  -> Parent Sandbox
  -> runnerctl run task.toml
  -> Control Plane API
  -> Run Orchestrator
  -> Provider Adapter
  -> Execution Sandbox
  -> Object Store + DB
```

## Plane Split

| Plane | Responsibility | Lifetime | Controlled by |
| --- | --- | ---: | --- |
| Access | Login, terminal routing, SSH/Web sessions | Minutes/hours | Control plane |
| Workspace | User workspace, task staging, terminal UX | Up to 24h, pause when idle | Control plane |
| Execution | Actual task/model-log run | One run only | Orchestrator |
| Control | Auth, quotas, billing, providers, logs, admin API | Always on | Platform backend |
| Durable storage | Logs, artifacts, manifests, costs | Retention-based | Platform backend |
| Admin | Fleet, runs, users, cost, templates, sandboxes | Always on | Platform backend |

## Main Flow

```text
User in parent sandbox
  -> runnerctl run ./task/task.toml
  -> Control Plane validates TOML, quota, user, image, secrets, limits
  -> Run Orchestrator creates execution sandbox through provider adapter
  -> run-agent executes command and streams logs/metrics/artifacts
  -> Control Plane finalizes result and uploads bundle
  -> Execution sandbox is destroyed
```

## Provider Strategy

Use a provider-neutral internal interface:

```ts
interface SandboxProvider {
  createParentSandbox(spec): Promise<ParentSandboxRef>
  resumeParentSandbox(parentId): Promise<void>
  pauseParentSandbox(parentId): Promise<void>
  destroyParentSandbox(parentId): Promise<void>

  createExecutionSandbox(runSpec): Promise<ExecutionSandboxRef>
  uploadFiles(sandboxId, bundle): Promise<void>
  execRun(sandboxId, command, env): Promise<RunProcessRef>
  streamLogs(sandboxId, processId): AsyncIterable<LogEvent>
  getMetrics(sandboxId): Promise<MetricsSample[]>
  killExecutionSandbox(sandboxId): Promise<void>
}
```

### E2B Fit

E2B is a strong first adapter when programmatic sandbox orchestration, PTY streaming, custom templates, metrics, file operations, and pause/resume/kill lifecycle matter most.

### Daytona Fit

Daytona is a strong first adapter when SSH and IDE workflows are the highest priority. Its documented default org resource limits may require a custom arrangement for large CPU/RAM profiles.

### Future Adapter

Keep a self-hosted adapter path open for Kubernetes, Firecracker, Kata, or gVisor when higher resource ceilings, GPUs, custom networking, or lower unit economics become important.

## Local Task Copying Caveat

If the user is inside SSH connected to a remote parent sandbox, that sandbox cannot automatically read files from the user's local machine.

Supported modes:

- Remote-first workspace: user clones/uploads into parent sandbox.
- Local-first CLI: local `runnerctl` packages and uploads the task.
- SFTP/rsync bridge: user syncs task into `/workspace/tasks`.
- IDE remote workspace: user edits directly in parent sandbox.

Recommended MVP: local-first CLI plus IDE remote workspace.
