# UX Design System

This product should feel like a serious operator console, not a marketing landing page.

## Visual Direction

Name: **AegisRun Foundry**

Style:

- Dense, legible, operator-grade.
- Dark graphite shell with light content panels for logs and tables.
- Avoid hero sections, decorative gradients, and floating marketing cards.
- Use tables, status chips, sparklines, timelines, and command panels.
- Make every screen answer an operational question.

## Palette

| Token | Hex | Use |
| --- | --- | --- |
| `bg.shell` | `#101214` | App frame |
| `bg.panel` | `#171A1F` | Primary panels |
| `bg.table` | `#F8FAFC` | Dense table surfaces |
| `text.primary` | `#E6EDF3` | Dark UI text |
| `text.inverse` | `#111827` | Light panel text |
| `accent.cyan` | `#00A7B5` | Active run, primary action |
| `accent.amber` | `#D99A00` | Warning, quota pressure |
| `accent.red` | `#D14343` | Failure, kill, blocked |
| `accent.green` | `#2E9D64` | Success, cleanup complete |
| `border.soft` | `#2B313A` | Panel separators |

## Core Screens

### Fleet Overview

Top row:

| Widget | Data |
| --- | --- |
| Active parents | Count, idle, refresh-pending |
| Active executions | Count, CPU/RAM, provider split |
| Queue pressure | Total queued, p95 wait |
| Cost burn | Current hour, day-to-date |
| Cleanup debt | Pending, failed, orphan suspected |

Main views:

- Active runs table
- Provider health table
- Cleanup queue
- Cost by user/org
- Recent audit events

### Run Detail

Layout:

```text
Header: run id, status, user, provider, profile, elapsed, cost
Left: timeline and state transitions
Center: live stdout/stderr with filters
Right: metrics, artifacts, TOML, actions
Bottom: event JSONL and cleanup state
```

Actions:

- Cancel run
- Retry run
- Force cleanup
- Download artifacts
- Copy run ID
- Open parent sandbox

### User Detail

Layout:

```text
User summary
Quota usage
Current parent sandbox
Active execution runs
Historical runs
Cost trend
Audit log
Admin actions
```

### Template Control

Shows:

- Parent template versions
- Run-agent versions
- Image allowlist and digest
- Vulnerability scan result
- Rollout percentage
- Rollback action

## Component Inventory

| Component | Required states |
| --- | --- |
| Status chip | queued, provisioning, running, collecting, succeeded, failed, timed_out, cleanup_failed |
| Run timeline | complete/current/future/failed/cancelled |
| Log viewer | follow, pause, search, stdout/stderr filter, copy |
| Metrics chart | CPU, memory, disk, network, cost |
| Quota meter | normal, warning, hard-blocked |
| Action button | normal, disabled, dangerous, loading |
| Artifact table | available, scanning, expired, blocked |
| Provider health | healthy, degraded, rate-limited, disabled |

## Design Rules

- Tables should be dense and scannable.
- Dangerous actions require confirm modal and audit reason.
- Logs should use monospace, sticky timestamps, and stream filter.
- Every admin action should show expected side effect before execution.
- Cost should be visible near every long-running action.
- Do not hide cleanup state behind status only.
