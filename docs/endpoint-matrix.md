# Endpoint Matrix

All protected endpoints use `Authorization: Bearer <session_token>`. Admin endpoints require `admin` or `platform_admin`.

## Trainer and shared endpoints

| Method | Path | Purpose | Mutation/audit |
| --- | --- | --- | --- |
| `GET` | `/health` | Liveness for Docker health checks | no |
| `POST` | `/v1/sessions` | Login by username or email; provision/resume trainer parent | session/login only |
| `DELETE` | `/v1/sessions/current` | End current session shape | no |
| `GET` | `/v1/me` | Current account, quota, parent and run summary | no |
| `GET` | `/v1/quota` | Current quota and usage | no |
| `GET` | `/v1/runtime` | Docker/image/Harbor readiness without secret values | no |
| `GET` | `/v1/terminal` | SSH and SFTP connection commands | no |
| `GET` | `/v1/workspace` | Parent, quota, bundles, runs and staged SFTP uploads | creates/repairs parent if needed |
| `POST` | `/v1/workspace/{resume|pause|refresh|destroy}` | Operate own parent workspace | yes |
| `POST` | `/v1/tasks/upload` | Upload a tar.gz task bundle from `runnerctl` | yes |
| `POST` | `/v1/tasks/submit` | Atomically upload, validate, resolve TOML resources, and queue a run | yes |
| `POST` | `/v1/tasks/import-staged` | Import one SFTP-staged folder/archive from `/incoming` | yes |
| `GET` | `/v1/tasks` | List own ready task bundles | no |
| `POST` | `/v1/runs` | Queue a child run from `task_bundle_id` and mode | yes |
| `GET` | `/v1/runs` | List own runs | no |
| `GET` | `/v1/runs/{run_id}` | Run detail and normalized spec | no |
| `POST` | `/v1/runs/{run_id}/cancel` | Stop an owned active child | yes |
| `POST` | `/v1/runs/{run_id}/retry` | Queue a new run from a terminal run | yes |
| `GET` | `/v1/runs/{run_id}/events` | Ordered lifecycle and log events | no |
| `GET` | `/v1/runs/{run_id}/logs` | Stdout log records | no |
| `GET` | `/v1/runs/{run_id}/artifacts` | Result package metadata | no |
| `GET` | `/v1/runs/{run_id}/artifacts/{artifact_id}/download` | Authenticated package download | no |
| `GET` | `/v1/runs/{run_id}/stream` | SSE run events until terminal state | no |

## Operator endpoints

| Method | Path | Purpose | Mutation/audit |
| --- | --- | --- | --- |
| `GET` | `/admin/overview` | Fleet counts, lineage, attention runs, recent runs, runtime health | no |
| `GET` | `/admin/users` | Filter/list accounts with quotas and parent summary | no |
| `POST` | `/admin/users` | Create trainer/reviewer/admin account | yes |
| `PATCH` | `/admin/users/{user_id}` | Change display name, email, role or state | yes |
| `POST` | `/admin/users/{user_id}/reset-password` | Replace hash and revoke sessions | yes |
| `PATCH` | `/admin/users/{user_id}/quota` | Change run limits and parent capacity | yes |
| `GET` | `/admin/parents` | Filter/list real parent containers | no |
| `POST` | `/admin/parents` | Provision one trainer parent | yes |
| `POST` | `/admin/parents/{parent_id}/{resume|pause|refresh|destroy}` | Operate real provider parent | yes |
| `GET` | `/admin/parents/{parent_id}/stats` | Live CPU, memory, PID and provider state | no |
| `GET` | `/admin/runs` | Filter/list all child runs | no |
| `POST` | `/admin/runs/{run_id}/force-cleanup` | Stop if needed and remove orphan child | yes |
| `GET` | `/admin/providers` | Provider capabilities and runtime/image readiness | no |
| `GET` | `/admin/audit` | Query operator audit stream | no |
| `GET` | `/admin/costs` | Recorded child cost and active-parent hourly estimate | no |
| `POST` | `/admin/cleanup/reconcile` | Cleanup children; pause, refresh or repair parents | yes |

## Required invariants

- A user can read or mutate only their own tasks, runs, events and artifacts unless they are an admin.
- One non-destroyed parent is allowed per trainer through the UI/API contract.
- Parent refresh/destroy returns `409` when active children exist.
- Harbor mode returns `409` when the operator has not enabled it.
- Child resource requests and timeout must pass TOML and quota validation before queueing.
- Download requests verify both run ownership and artifact membership.
- Provider keys never appear in any response.
