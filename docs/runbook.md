# Operations Runbook

## Daily Checks

| Check | Command/source | Action if bad |
| --- | --- | --- |
| Orphan execution sandboxes | Reconciler dashboard | Force cleanup |
| Cleanup failures | Cleanup Center | Retry or escalate provider |
| Provider 429 rate | Provider health | Reduce concurrency or backoff |
| Active parent age > 24h | Fleet overview | Drain/refresh |
| Cost burn > budget | Cost Center | Suspend org/user or lower quotas |
| Artifact upload failures | Artifact service metrics | Check object storage |

## Incident: Provider API Rate Limit

Symptoms:

- Runs stuck in `PROVISIONING`
- Provider adapter logs 429
- Queue wait increases

Actions:

1. Enable provider degraded state.
2. Reduce new run dispatch concurrency.
3. Honor `Retry-After` or exponential backoff.
4. Keep queued runs in platform queue.
5. Notify admins if p95 wait exceeds threshold.

## Incident: Cleanup Failure

Symptoms:

- `CLEANUP_FAILED` runs
- Provider sandboxes still running after terminal status
- Cost burn higher than active run count suggests

Actions:

1. Confirm artifacts were finalized.
2. Run force cleanup on affected sandbox IDs.
3. If provider kill fails, mark provider degraded.
4. Open incident if sandbox survives two cleanup retries.

## Incident: Parent Workspace Lost

Symptoms:

- User terminal disconnects.
- Parent sandbox deleted or errored.
- Active child run continues.

Actions:

1. Confirm active run is attached to control plane, not parent.
2. Recreate parent from latest template.
3. Rehydrate workspace metadata from object storage if available.
4. Tell user to reconnect.

## Incident: Secret Leak In Logs

Actions:

1. Stop the run if secret exposure is live.
2. Rotate the affected secret.
3. Mask stored log lines.
4. Mark artifact bundle as restricted until review.
5. Audit how secret entered runtime.

## Incident: Artifact Upload Failure

Actions:

1. Keep execution sandbox alive until retry budget is exhausted.
2. Retry upload with exponential backoff.
3. If still failing, upload minimal logs and mark `ARTIFACT_UPLOAD_FAILED`.
4. Destroy sandbox after hard finalization timeout.
