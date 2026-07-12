# AegisRun Foundry Project Map

## Runtime topology

```text
trainer SSH/SFTP (:2222)
  -> gateway/app.py
  -> FastAPI control plane (:18080)
  -> Postgres + storage/
  -> parent Docker container per trainer
  -> child Docker container per run

operator browser (:5177)
  -> React operator console
  -> /admin/* and authorized /v1/runs/* endpoints
```

## Code map

| Path | Responsibility |
| --- | --- |
| `api/app/main.py` | API schemas, auth/session routes, trainer routes, operator routes, serializers |
| `api/app/models.py` | users, sessions, quotas, parents, task bundles, runs, events, artifacts, audit |
| `api/app/parent_runtime.py` | provision, pause, resume, refresh, destroy, stats, parent reconciler |
| `api/app/docker_runner.py` | per-user queue, child creation, log streaming, artifact handoff, cleanup |
| `api/app/task_bundles.py` | archive safety, TOML discovery/validation, parent task staging |
| `api/app/toml_validator.py` | generic and SwarmBench TOML normalization and resource policy |
| `api/app/security.py` | PBKDF2 password hash and verification |
| `gateway/app.py` | dynamic password auth, SSH menu, SFTP chroot |
| `cli/runnerctl.py` | local upload/run companion and trainer TUI |
| `web/src/App.jsx` | operator authentication and page routing |
| `web/src/Shell.jsx` | sticky operator navigation and connectivity state |
| `web/src/pages/OverviewPage.jsx` | fleet lineage, health, attention and cost |
| `web/src/pages/ParentsPage.jsx` | parent inventory, telemetry and lifecycle actions |
| `web/src/pages/RunsPage.jsx` | child inventory, events, logs, artifacts and actions |
| `web/src/pages/UsersPage.jsx` | credentials, role/state, quota and capacity controls |
| `web/src/pages/RuntimePage.jsx` | runtime readiness, terminal commands and reconciler |
| `web/src/pages/AuditPage.jsx` | operator mutation ledger |
| `scripts/e2e_admin_api.py` | live operator workflow smoke test |
| `docs/implementation-audit.md` | requirement traceability and residual limitations |
| `docs/release-checklist.md` | source, test, Harbor, and deployment release gates |
| `SECURITY.md` | vulnerability reporting and local-build security boundary |

## Core invariants

1. Trainers never receive the admin web interface or provider keys.
2. One trainer owns one non-destroyed parent workspace.
3. Every run references a trainer, parent, and validated task bundle.
4. Child CPU/memory come from normalized TOML and quota policy.
5. Result collection completes before child destruction.
6. Result packages are available through authenticated API and parent SFTP.
7. Refresh/destroy are blocked while children are active.
8. Password resets revoke existing sessions.
9. Every operator mutation creates an audit record.
10. The reconciler handles orphan children and idle/due/error parents.

## Quick verification

```bash
docker compose ps
docker compose exec -T api python -m pytest -q
docker compose exec -T web npm run build
python3 scripts/e2e_admin_api.py
```
