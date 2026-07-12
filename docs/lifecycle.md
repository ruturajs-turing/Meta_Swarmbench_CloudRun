# Sandbox Lifecycle

## Parent Sandbox

The parent sandbox is a replaceable user workspace. It should not hold provider API keys or admin secrets.

### Parent Contents

```text
/opt/platform/
  runnerctl
  terminal-agent
  sync-agent
  log-viewer
  config/
  diagnostics/

/workspace/
  tasks/
  cache/
  downloads/
  tmp/
```

### Parent Lifecycle

```text
NONE
  -> CREATING
  -> RUNNING
  -> IDLE
  -> PAUSED
  -> RESUMING
  -> REFRESH_PENDING
  -> DRAINING
  -> DESTROYED
  -> RECREATED_FROM_LATEST_TEMPLATE
```

### 24-Hour Refresh

```text
if parent.age > 24h:
    mark REFRESH_PENDING
    block new run submissions for this parent
    allow active terminal session to finish or warn user
    sync required workspace state to object storage
    pause or destroy old parent
    create new parent from latest template
    rehydrate workspace metadata
```

Do not destroy a parent while it has active child runs. Child runs continue independently through the control plane.

## Execution Sandbox

The execution sandbox is single-use and exists only for one run.

### Execution Contents

```text
/run/
  task/
  task.toml
  run-agent
  logs/
  artifacts/
  results/
  metrics/
```

### Execution Lifecycle

```text
REQUESTED
  -> VALIDATING
  -> QUEUED
  -> PROVISIONING
  -> STAGING_INPUTS
  -> STARTING
  -> RUNNING
  -> COLLECTING_OUTPUTS
  -> FINALIZING
  -> SUCCEEDED / FAILED / TIMED_OUT / CANCELLED / INFRA_FAILED
  -> CLEANING_UP
  -> DESTROYED
```

### Result Semantics

| State | Meaning |
| --- | --- |
| `SUCCEEDED + passed=true` | Run completed and model-log test passed |
| `SUCCEEDED + passed=false` | Run completed but model-log test failed |
| `FAILED` | Command crashed or invalid output |
| `TIMED_OUT` | Run exceeded time limit |
| `CANCELLED` | User/admin stopped it |
| `INFRA_FAILED` | Provider, network, quota, upload, or sandbox error |
| `CLEANUP_FAILED` | Result finalized but cleanup needs retry |

## Run Agent Responsibilities

The run agent should:

1. validate normalized TOML;
2. print a run header;
3. start the command;
4. stream stdout/stderr;
5. collect CPU/RAM/disk/network samples;
6. enforce timeout;
7. detect pass/fail;
8. package artifacts;
9. upload result bundle;
10. signal final status;
11. exit with a meaningful code.
