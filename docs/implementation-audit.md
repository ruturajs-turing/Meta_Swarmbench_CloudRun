# Implementation Audit

Audit date: 2026-07-12

## Decision

AegisRun Foundry is suitable for isolated internal testing of the local Docker workflow. It is not yet suitable for exposure to trainers over a shared or public network, and it is not yet an E2B/Daytona cloud deployment.

The implemented product boundary is correct: trainers submit through `runnerctl` or operate already-staged files through SSH; operators manage users, parent workspaces, child runs, artifacts, runtime readiness, cost estimates, and audit events through the admin console. The control plane, rather than the parent workspace, owns Docker orchestration and provider credentials.

## Requirement traceability

| Requirement | Status | Evidence | Remaining work |
| --- | --- | --- | --- |
| Username/password trainer entry | Implemented for local testing | `gateway/app.py`, `POST /v1/sessions`, `runnerctl connect` | Replace static password model with SSO or short-lived SSH certificates for production. |
| One parent workspace per trainer | Implemented | `ParentSandbox`, user workspace endpoint, parent lifecycle service | Enforce with a database uniqueness constraint, not only application behavior. |
| Local task path upload in one terminal | Implemented | `runnerctl connect`, atomic `POST /v1/tasks/submit` | Large-bundle resumability is not implemented. |
| TOML-driven child resources | Implemented for CPU/RAM and policy metadata | validator tests and `TASK_CONFIG_RESOLVED`/`SANDBOX_CREATED` events | Local Docker does not enforce a per-container disk quota. |
| Ephemeral child per run | Implemented | `docker_runner.py` finalizer and reconciler | Provider-level hard TTL is still required for cloud deployment. |
| Harbor/OpenCode model execution | Implemented behind an explicit runtime flag | managed runner Dockerfile and Harbor execution mode | Requires the patched Harbor source, managed image, valid Fireworks account, and a completed real-task release gate. |
| Live logs, states, pass/fail and artifacts | Implemented | SSE events, run inspector, authenticated artifact download | Log-volume backpressure and external object storage are not implemented. |
| Copy results back to parent | Implemented | parent `/runs` and `/downloads` handoff | Cloud object-store synchronization is not implemented. |
| Two concurrent child runs per trainer | Implemented as configurable quota | queue drain and `Quota.max_active_runs` | Multi-process/distributed dispatch needs a database lock or queue service. |
| Parent pause and 24-hour refresh | Implemented for local Docker | parent runtime and reconciler | Production provider semantics must be verified separately. |
| Admin fleet management | Implemented | Overview, Workspaces, Runs, Users, Runtime, Audit | Reviewer workflow is intentionally out of scope for this revision. |
| Cost visibility | Partial | configured runtime estimates and cost summary | Values are estimates, not provider invoices or token-level model billing. |
| Durable S3 storage | Not implemented | local S3-shaped filesystem only | Add object storage, signed downloads, retention, encryption, scanning, and recovery. |
| E2B/Daytona adapters | Designed, not implemented | provider interface and architecture documents | Build and integration-test provider adapters. |
| Production tenant/network security | Not implemented | development warning in `SECURITY.md` | Add hardened ingress, secret manager, true egress enforcement, tenant isolation, rate limits, and abuse controls. |

## Known technical limitations

- The API container mounts the host Docker socket. This is acceptable only for isolated internal development and is not a production security boundary.
- Parent and child execution currently use one local Docker daemon. Cloud provider adapters are architecture targets, not runnable integrations.
- The `allowlist` network value is metadata in the local adapter; domain-level egress filtering is not enforced. Probe mode can disable networking, while Harbor mode requires network and nested Docker access.
- Parent disk capacity and child `disk_gb` are recorded policies, not hard local Docker quotas.
- The queue uses in-process threads and a process-local lock. A horizontally scaled control plane requires a durable queue and transactional lease.
- The bundled web container runs Vite's development server. A production deployment needs a compiled static image and hardened reverse proxy.
- Compose seeds known local credentials on an empty database. Those credentials must never be used on a shared deployment.
- Cost figures are configurable estimates. They do not include exact Fireworks token billing, storage, egress, or provider invoice reconciliation.
- The checked-in OpenAPI and SQL files are reference artifacts; SQLAlchemy models and the live FastAPI schema remain authoritative.

## Verification record

Validation completed on 2026-07-12 before the initial GitHub publication:

| Check | Result |
| --- | --- |
| API unit suite in Python 3.12 container | PASS, 9 tests |
| Python source compilation | PASS |
| Frontend clean install and production build | PASS, 0 npm vulnerabilities reported |
| Compose configuration and four-service startup | PASS, API and Postgres healthy |
| API health and live OpenAPI | PASS, 36 paths |
| Admin E2E | PASS: users, quotas, parent pause/resume/refresh, providers, runs, audit, costs |
| Trainer CLI probe run | PASS: run `run_ef9585933c0a40a2`, exact 2 CPU / 4096 MB limits, artifact finalized, child destroyed |
| Published `make runner-smoke` workflow | PASS: run `run_58ae68e54afe4112` |
| Password-authenticated SSH menu | PASS |
| HTTP authorization boundaries | PASS: trainer-to-admin `403`, invalid login `401`, missing auth `401` |
| Archive traversal/link rejection tests | PASS |
| Managed runtime build | PASS: Harbor `0.6.4`, OpenCode `1.17.18`, Node `22.23.1`, Docker `27.5.1`, Compose `2.32.4` |
| Harbor patch application and checksum | PASS against base `e70d5f0`; SHA-256 matches `5c60e8ec...72d6` |
| Plugin manifest validation | PASS |
| Secret, large-file, absolute-path, and Markdown-link scans | PASS |
| Rendered architecture assets | PASS, 18 PNG/SVG files |

The admin console's production build passed, but interactive browser visual QA was not executed because no in-app browser target was available in the validation session. Real Fireworks model execution was not repeated for this publication because no provider key was placed into the release environment; it remains a separate release gate in `docs/release-checklist.md`.
