# Test Workflow Map

This maps product workflows to test files in the style of the CUArena project map.

## Proposed Backend Tests

| File | Covers |
| --- | --- |
| `test_auth.py` | Login, token expiry, role enforcement |
| `test_parent.py` | Parent create/resume/pause/refresh/drain |
| `test_toml_validation.py` | Valid/invalid TOML, resource profiles, image digest, secrets |
| `test_runs.py` | Submit/list/detail/cancel/retry |
| `test_queue.py` | Per-user active limit, queued run ordering |
| `test_orchestrator.py` | State transitions, staging, finalization |
| `test_e2b_adapter.py` | Create, stream logs, metrics, metadata list, kill |
| `test_daytona_adapter.py` | SSH token, lifecycle, resource-limit mapping |
| `test_artifacts.py` | Upload, manifest, signed URL, size limits |
| `test_metrics.py` | Provider metric normalization |
| `test_costs.py` | Runtime/storage/cost estimates |
| `test_cleanup_reconciler.py` | Orphan kill, stuck run repair, cleanup failure retry |
| `test_admin.py` | User quota, force cleanup, template rollout |
| `test_security.py` | Secret masking, network deny, unauthorized access |

## Proposed Frontend E2E Tests

| File | Scenario |
| --- | --- |
| `login.spec.js` | Login, expired session banner, logout |
| `workspace.spec.js` | Parent status, quota, submit run from workspace |
| `fleet.spec.js` | Fleet overview counts and filters |
| `run-detail.spec.js` | Timeline, live logs, metrics, artifacts |
| `queue.spec.js` | Active-run limit and queued state |
| `cleanup.spec.js` | Cleanup center, force cleanup confirm |
| `templates.spec.js` | Promote/rollback template with audit reason |
| `costs.spec.js` | Cost table, user/org filters |
| `admin-user.spec.js` | User detail, quota edit, suspend |
| `full-workflow.spec.js` | Login -> submit run -> stream logs -> artifact -> cleanup |

## End-To-End Critical Paths

| ID | Path | Must prove |
| --- | --- | --- |
| E2E-001 | User submits valid task | Run completes, logs/artifacts durable, sandbox destroyed |
| E2E-002 | User submits third run | Third run queues behind two active runs |
| E2E-003 | Parent disconnects mid-run | Run continues and user can reconnect |
| E2E-004 | Admin cancels stuck run | Run cancels, cleanup triggers, audit written |
| E2E-005 | Provider create fails | Run marks `INFRA_FAILED`, no orphan remains |
| E2E-006 | Artifact upload fails | Retry happens, final state is visible |
| E2E-007 | Secret printed in logs | Secret is masked and security event exists |
