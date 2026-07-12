# API Surface

The live interactive specification is `http://localhost:18080/docs`. The checked-in OpenAPI reference is `specs/openapi.yaml`.

## Authentication and trainer

```text
POST   /v1/sessions
GET    /v1/me
GET    /v1/quota
GET    /v1/runtime
GET    /v1/terminal
GET    /v1/workspace
POST   /v1/workspace/{resume|pause|refresh|destroy}
POST   /v1/tasks/upload
POST   /v1/tasks/submit
POST   /v1/tasks/import-staged
GET    /v1/tasks
POST   /v1/runs
GET    /v1/runs
GET    /v1/runs/{run_id}
POST   /v1/runs/{run_id}/cancel
POST   /v1/runs/{run_id}/retry
GET    /v1/runs/{run_id}/events
GET    /v1/runs/{run_id}/logs
GET    /v1/runs/{run_id}/artifacts
GET    /v1/runs/{run_id}/artifacts/{artifact_id}/download
GET    /v1/runs/{run_id}/stream
```

Run creation accepts a ready task bundle, not raw admin-page TOML:

```json
{
  "task_bundle_id": "bun_...",
  "execution_mode": "probe"
}
```

## Operator

```text
GET    /admin/overview
GET    /admin/users
POST   /admin/users
PATCH  /admin/users/{user_id}
POST   /admin/users/{user_id}/reset-password
PATCH  /admin/users/{user_id}/quota
GET    /admin/parents
POST   /admin/parents
POST   /admin/parents/{parent_id}/{resume|pause|refresh|destroy}
GET    /admin/parents/{parent_id}/stats
GET    /admin/runs
POST   /admin/runs/{run_id}/force-cleanup
GET    /admin/providers
GET    /admin/audit
GET    /admin/costs
POST   /admin/cleanup/reconcile
```

See `docs/endpoint-matrix.md` for purpose, role, and invariant details.
