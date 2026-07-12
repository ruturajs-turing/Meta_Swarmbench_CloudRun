# Security, Cost, And Cleanup

Treat all user-provided TOML, commands, files, and task packages as untrusted.

## Security Rules

| Area | Policy |
| --- | --- |
| Parent sandbox | User workspace only; no provider keys |
| Execution sandbox | One fresh sandbox per run |
| Secrets | Vault references only; no raw values in TOML |
| Images | Allowlist and pin by digest |
| Network | Default deny or allowlist |
| Inputs | Upload only declared paths |
| Outputs | Collect only declared paths |
| Logs | Mask secrets and isolate by tenant |
| Admin | RBAC, MFA, and audit logs |
| Docker-in-Docker | Avoid for untrusted isolation unless explicitly hardened |

## Secret Handling

Use references:

```toml
[secrets]
HF_TOKEN = "vault://tenant/project/hf_token"
```

Runtime flow:

```text
Control plane validates secret access
  -> injects short-lived secret into execution sandbox only
  -> masks secret in logs
  -> revokes or rotates as needed
```

## Cost Controls

| Control | Why |
| --- | --- |
| Per-user active run limit | Prevent runaway concurrency |
| Per-org budget | Prevent surprise bills |
| Per-run timeout | Kill stuck jobs |
| Idle parent pause | Save cost |
| 24h parent refresh | Control disk drift |
| Execution hard TTL | Prevent orphan spend |
| Artifact size limit | Prevent storage blowup |
| Queue instead of reject | Better UX |
| Provider rate-limit backoff | Avoid API failure storms |
| Reconciler | Clean leaked resources |
| Admin kill switch | Emergency control |

## Cleanup Finalizer

```text
try:
    run task
    collect logs
    upload artifacts
    update DB
finally:
    destroy execution sandbox
```

## Reconciler

```text
every 1 minute:
    list provider sandboxes where metadata.managed_by = "aegisrun"
    find execution sandboxes older than allowed TTL
    if no active run or run is terminal:
        kill sandbox
    if run is stuck too long:
        mark INFRA_FAILED or TIMED_OUT
        kill sandbox
```

## Failure Cases

| Failure | Required behavior |
| --- | --- |
| User disconnects | Run continues; user can reconnect |
| Parent sandbox dies | Run continues; parent can be recreated |
| Execution sandbox dies | Mark `INFRA_FAILED`; preserve collected logs |
| Artifact upload fails | Retry; delay destroy until final attempt or timeout |
| Backend crashes | Reconciler resumes from DB state |
| Provider rate limits | Queue/backoff; do not spam provider |
| TOML requests too many resources | Reject with clear error |
| User exceeds active run limit | Queue or reject by plan |
| Parent reaches 24h while active | Mark refresh pending; drain first |
| Cleanup fails | Mark `CLEANUP_FAILED`; reconciler retries |
| Image vulnerability found | Block from allowlist |
| Secret appears in logs | Mask and flag event |
| Output too large | Stop collecting; mark artifact limit exceeded |
| Network abuse | Deny/allowlist and kill if violated |
