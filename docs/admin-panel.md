# Admin Panel

The admin panel talks only to the control plane. It should not depend on being inside a parent sandbox.

## Fleet Overview

Show:

| Metric | Meaning |
| --- | --- |
| Active parent sandboxes | Users connected or idle |
| Active execution sandboxes | Current cost-driving workers |
| Queued runs | Backlog |
| Failed runs | Debug target |
| Cleanup pending | Orphan risk |
| Current estimated cost/hour | Cost visibility |
| Provider errors | E2B/Daytona/K8s issues |
| Quota pressure | Users hitting limits |

## User Detail

```text
User
  - current parent sandbox
    - provider
    - sandbox id
    - template version
    - age
    - idle time
    - disk used
    - actions: pause, resume, refresh, destroy
  - active runs
    - run id
    - execution sandbox id
    - CPU/RAM/disk
    - elapsed time
    - logs
    - actions: stop, retry, download
  - historical runs
  - cost summary
  - quota settings
  - audit log
```

## Run Detail

```text
Run ID
Status
User / org / project
Parent sandbox ID
Execution sandbox ID
Provider
Template/image digest
TOML config
Live stdout/stderr
Metrics timeline
Artifacts
Pass/fail result
Cost estimate
Cleanup status
```

## Template And Image Management

| Item | Admin action |
| --- | --- |
| Parent template version | promote, rollback, deprecate |
| Runner image version | promote, rollback |
| Harbor image digest | allowlist/block |
| Security scan status | approve/block |
| Canary rollout | 5%, 25%, 100% |
| Parent refresh policy | immediate, idle-only, next login |

## User/Org Quotas

```text
max_active_runs_per_user
max_active_runs_per_org
max_parent_sandboxes_per_user
max_cpu_per_run
max_memory_per_run
max_disk_per_run
max_runtime_seconds
max_upload_mb
max_output_mb
max_monthly_cost
allowed_providers
allowed_images
allowed_network_mode
```

## Emergency Controls

```text
global kill switch for new runs
per-provider disable switch
per-tenant suspend switch
force cleanup all orphan sandboxes
block image digest
block network egress
```
