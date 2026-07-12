---
name: aegisrun-foundry
description: Use when planning, reviewing, or implementing a multi-tenant remote execution platform with parent workspaces, per-run execution sandboxes, TOML validation, logs/artifacts, cleanup, cost controls, admin dashboard, and provider adapters.
---

# AegisRun Foundry Skill

Use this skill to ground architecture and implementation discussions in the packaged AegisRun Foundry docs.

## Read Order

1. `README.md`
2. `MANUAL.md`
3. `docs/research-notes.md`
4. `docs/architecture.md`
5. `docs/lifecycle.md`
6. `docs/security-cost-cleanup.md`
7. `docs/admin-panel.md`
8. `docs/ux-design-system.md`
9. `docs/test-plan.md`
10. `docs/runbook.md`
11. `specs/api.md`
12. `specs/openapi.yaml`
13. `specs/database.sql`
14. `examples/task.toml`
15. `schemas/task.schema.json`

## Core Architecture Rule

The parent sandbox is a user workspace, not the system owner. The control plane owns orchestration, provider keys, quotas, billing, logs, cleanup, and admin controls.

## Default Recommendation

Build in this order:

1. Control Plane API
2. Postgres schema
3. Object storage artifact service
4. One provider adapter
5. Parent sandbox template
6. `runnerctl` CLI
7. Run orchestrator
8. Execution sandbox lifecycle
9. Live logs and final artifact bundle
10. Cleanup reconciler
