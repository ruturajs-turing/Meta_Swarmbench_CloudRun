# Research Notes

Verified on 2026-07-10.

## Provider Capability Findings

| Topic | E2B finding | Daytona finding | Design implication |
| --- | --- | --- | --- |
| Custom environments | E2B templates define base image, env vars, files, commands, and start commands captured into a snapshot. Build scripts can set CPU and memory. Source: https://e2b.dev/docs/template/quickstart | Daytona supports snapshots and sandbox lifecycle operations. Source: https://www.daytona.io/docs/en/sandboxes/ | Build parent and execution environments as versioned templates/snapshots. Do not mutate live sandboxes manually. |
| Lifecycle | E2B supports running, paused, snapshotting, and killed states; pause preserves filesystem and memory, kill releases resources. Source: https://e2b.dev/docs/sandbox/persistence | Daytona supports stop/archive for containers and pause/resume for VM sandboxes; VM pause preserves filesystem and memory. Source: https://www.daytona.io/docs/en/sandboxes/ | Parent lifecycle should support pause/resume/refresh, but execution sandboxes should be killed after finalization. |
| Metrics | E2B exposes timestamped CPU, memory, and disk metrics collected every 5 seconds. Source: https://e2b.dev/docs/sandbox/metrics | Daytona docs expose resource configuration and limits; metrics should be normalized through the provider adapter when available. | Store provider metrics as `usage_samples`; do not build dashboard directly against provider-specific payloads. |
| SSH/IDE | E2B has terminal and SSH-related docs, but its strongest fit is programmatic sandbox orchestration. | Daytona supports token-based SSH access and VS Code/JetBrains remote development workflows. Source: https://www.daytona.io/docs/en/ssh-access/ | Daytona maps well to SSH-first parent workspaces; E2B maps well to execution orchestration. |
| Listing and reconciliation | E2B supports listing sandboxes with pagination, state filters, and metadata filters. Source: https://e2b.dev/docs/sandbox/list | Daytona has lifecycle APIs and rate-limit headers. Source: https://www.daytona.io/docs/en/limits/ | Every sandbox created by the platform must carry metadata for reconciler lookup. |
| Streaming logs | E2B command execution supports stdout/stderr callbacks for streaming. Source: https://e2b.dev/docs/commands/streaming | Daytona adapter should stream logs through either process API, SSH agent, or run-agent callback depending on implementation. | The platform event stream must be provider-neutral. |
| Docker in sandbox | E2B documents Docker and Docker Compose examples inside templates. Source: https://e2b.dev/docs/template/examples/docker | Daytona supports container/VM sandbox types. | Docker-in-sandbox is a tool option, not the primary multi-tenant security boundary. |
| Rate limits | E2B has plan/build/runtime limits; higher resources may require support/Enterprise. Source: https://e2b.dev/docs/template/quickstart | Daytona exposes rate-limit headers and recommends exponential backoff; tiers define compute/memory/storage/API limits. Source: https://www.daytona.io/docs/en/limits/ | Build provider rate-limit handling and resource-profile routing from day one. |

## Design Decisions From Research

1. **Use provider-neutral adapters.** Provider APIs differ enough that platform internals should not depend directly on E2B or Daytona payloads.
2. **Use metadata tags everywhere.** Reconciliation depends on finding provider sandboxes by `managed_by`, `org_id`, `user_id`, `run_id`, and `sandbox_role`.
3. **Do not rely on parent sandbox storage.** Provider pause/archive behavior differs; durable logs/artifacts belong in object storage.
4. **Do not let TOML request raw resources without policy.** Provider limits vary by tier; resource profiles let the control plane normalize and reject safely.
5. **Treat Docker-in-sandbox as optional.** It is documented, but it should not be the primary isolation boundary for untrusted multi-tenant execution.
6. **Make log streaming provider-neutral.** E2B has command callbacks; other providers may require a run-agent side channel.
7. **Implement backoff.** Daytona documents `429` behavior and rate-limit headers; provider adapters should expose retry hints.

## Source Index

| Source | Used for |
| --- | --- |
| https://e2b.dev/docs/template/quickstart | Templates, build resources, custom environments |
| https://e2b.dev/docs/sandbox/persistence | Pause/resume/kill semantics, auto-pause, runtime limit |
| https://e2b.dev/docs/sandbox/metrics | CPU/RAM/disk metrics |
| https://e2b.dev/docs/sandbox/list | Sandbox listing, state/metadata filters |
| https://e2b.dev/docs/commands/streaming | stdout/stderr streaming callbacks |
| https://e2b.dev/docs/template/examples/docker | Docker and Docker Compose inside templates |
| https://www.daytona.io/docs/en/ssh-access/ | Token-based SSH, VS Code, JetBrains |
| https://www.daytona.io/docs/en/sandboxes/ | Archive, pause/resume, resize lifecycle |
| https://www.daytona.io/docs/en/limits/ | Rate-limit headers, tiers, backoff guidance |
