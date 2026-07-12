# Release Checklist

Use this checklist before tagging or deploying a revision.

## Source and secrets

- [ ] `git status --short` contains only intended changes.
- [ ] Runtime data under `storage/`, frontend dependencies, build output, databases, archives, keys, and `.env` files are ignored.
- [ ] Secret scan finds no provider keys, passwords, tokens, private keys, or task data.
- [ ] `.env.example` contains placeholders only.
- [ ] Demo credentials are not used outside an isolated local environment.

## Build and tests

- [ ] Python source compiles with Python 3.12.
- [ ] API unit tests pass in the API container.
- [ ] Frontend production build passes with `npm ci && npm run build`.
- [ ] `docker compose config --quiet` passes.
- [ ] API health and interactive docs respond.
- [ ] Admin E2E smoke passes.
- [ ] Trainer login creates or resumes a real parent container.
- [ ] Probe run resolves TOML resources, creates a child, streams events, finalizes an artifact, copies it to the parent, and removes the child.
- [ ] Parent pause/resume/refresh and cleanup reconciliation affect the real container state.

## Real Harbor gate

- [ ] Managed Harbor/OpenCode image is built from the expected patched Harbor source.
- [ ] Fireworks key is provided only through process environment or a secrets manager.
- [ ] Runtime readiness reports Harbor and Fireworks as configured without returning secret values.
- [ ] One real task completes both model runs and produces expected execution logs.
- [ ] Child container is destroyed only after artifact finalization.

## Deployment gate

- [ ] Review `docs/implementation-audit.md` and accept every residual limitation.
- [ ] Replace local-only storage, ingress, credentials, and provider controls before external exposure.
- [ ] Pin images by digest and record the template/image version.
- [ ] Verify backup, restore, retention, alerting, budget, and emergency-stop procedures.
