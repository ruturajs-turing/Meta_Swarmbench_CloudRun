# Test Plan

## Test Scope

The platform must be tested across:

- TOML validation
- Auth/session
- Parent lifecycle
- Execution lifecycle
- Provider adapters
- Queue/concurrency
- Logs/events
- Artifact collection
- Cleanup/reconciler
- Admin operations
- Cost accounting
- Security boundaries
- UX-critical flows

## Functional Test Matrix

| ID | Case | Expected result |
| --- | --- | --- |
| F-001 | Submit valid `task.toml` | Run enters `QUEUED` or `PROVISIONING` |
| F-002 | Submit TOML missing `[outputs]` | Rejected before sandbox creation |
| F-003 | Submit TOML with raw secret | Rejected and audit event created |
| F-004 | Submit TOML requesting unsupported profile | Rejected with provider/profile explanation |
| F-005 | User has two active runs and submits third | Third run queues or rejects by plan |
| F-006 | Run completes with exit code 0 and passed true | `SUCCEEDED`, artifact bundle available |
| F-007 | Run completes with exit code 0 and passed false | `SUCCEEDED`, `passed=false`, not infra failure |
| F-008 | Command exits non-zero | `FAILED`, logs preserved |
| F-009 | Run exceeds timeout | `TIMED_OUT`, sandbox cleanup scheduled |
| F-010 | User cancels run | `CANCELLED`, sandbox destroyed |

## Parent Sandbox Tests

| ID | Case | Expected result |
| --- | --- | --- |
| P-001 | Create parent for new user | Parent row created and reachable |
| P-002 | Idle parent reaches pause threshold | Parent pauses/stops by provider policy |
| P-003 | Parent reaches 24h while no active run | Refresh drains, syncs, recreates |
| P-004 | Parent reaches 24h while child run active | Parent marked `REFRESH_PENDING`; child continues |
| P-005 | Parent dies during active run | Run continues; parent can be recreated |

## Provider Adapter Tests

| ID | Case | Expected result |
| --- | --- | --- |
| A-001 | E2B create execution sandbox | Provider ID stored with metadata |
| A-002 | E2B metrics polling | Metrics normalized to `usage_samples` |
| A-003 | E2B list by metadata | Reconciler finds platform sandboxes |
| A-004 | Daytona SSH token creation | Token expires and can be revoked |
| A-005 | Daytona 429 | Adapter honors retry headers/backoff |
| A-006 | Provider create fails | Run marked `INFRA_FAILED` if unrecoverable |

## Cleanup Tests

| ID | Case | Expected result |
| --- | --- | --- |
| C-001 | Normal completion | Execution sandbox destroyed |
| C-002 | Artifact upload fails once | Retry before destroy |
| C-003 | Destroy API fails | `CLEANUP_FAILED`; reconciler retries |
| C-004 | Orphan sandbox exists without active run | Reconciler kills it |
| C-005 | Stuck `RUNNING` beyond hard TTL | Mark timeout/infra failed and kill |

## Security Tests

| ID | Case | Expected result |
| --- | --- | --- |
| S-001 | Parent tries to access provider key | No key exists in parent |
| S-002 | User includes `.git/**` without allow | Input policy rejects or excludes |
| S-003 | Output exceeds max size | Collection stops and run flags limit exceeded |
| S-004 | Secret appears in stdout | Log masker redacts and security event recorded |
| S-005 | Network domain not allowlisted | Request blocked or run killed by policy |
| S-006 | Admin kills another user's run | Allowed only with RBAC and audit reason |

## Admin UX Tests

| ID | Case | Expected result |
| --- | --- | --- |
| U-001 | Fleet overview with active runs | Counts match DB and provider reconciliation |
| U-002 | Run detail while streaming | Logs update without refresh |
| U-003 | Force cleanup action | Confirm modal, audit reason, cleanup job |
| U-004 | Quota edit | New quota applies to next submission |
| U-005 | Provider disable | New runs stop routing to provider |

## Performance And Reliability Tests

| ID | Case | Expected result |
| --- | --- | --- |
| R-001 | 100 queued runs across users | Queue ordering stable |
| R-002 | 1,000 log events/sec burst | No event loss; backpressure visible |
| R-003 | Object storage latency spike | Run remains active; upload retries |
| R-004 | Control plane restart | Reconciler resumes from DB state |
| R-005 | Provider outage | Runs fail/queue cleanly; admin health shows degraded |
