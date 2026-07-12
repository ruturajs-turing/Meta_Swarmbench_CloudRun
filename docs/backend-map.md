# Backend Map

| Module | Owned behavior |
| --- | --- |
| `main.py` | HTTP boundary, authorization, DTOs, admin/trainer routes, minute reconciler thread |
| `models.py` | SQLAlchemy system of record |
| `auth.py` | bearer session lookup, expiry and admin role gate |
| `security.py` | PBKDF2-SHA256 password storage |
| `parent_runtime.py` | actual Docker parent lifecycle and telemetry |
| `docker_runner.py` | run queue, child lifecycle, events, artifacts, cost and cleanup |
| `task_bundles.py` | safe archive/staged import and parent workspace copy |
| `toml_validator.py` | resource and SwarmBench task normalization |
| `audit.py` | append-only operator mutation records |

The local provider adapter uses Docker labels `managed_by=aegisrun`, `sandbox_role=parent|execution`, and lineage IDs for reconciliation. Cloud adapters should preserve the same internal contracts.
