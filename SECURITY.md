# Security Policy

## Scope

AegisRun Foundry executes untrusted task bundles and controls Docker containers. Security reports should include the affected endpoint or component, reproduction steps, impact, and whether credentials or tenant data may have been exposed.

Do not include live provider keys, passwords, session tokens, task data, or private artifacts in a public issue. Report sensitive findings directly to the repository owner through a private GitHub security advisory.

## Local-build warning

The checked-in Compose stack is for internal development. It includes known demo credentials, mounts the Docker socket into the control-plane container, serves HTTP/SSH without production ingress, and uses local filesystem storage. Do not expose it to an untrusted network as-is.

Before any shared or production deployment:

- remove or replace seeded demo accounts and rotate every credential;
- terminate TLS at a trusted ingress and restrict API, SSH, and database ports;
- use a secrets manager instead of `.env` files;
- replace direct Docker-socket access with a hardened execution-provider boundary;
- enforce tenant isolation, egress policy, artifact scanning, retention, and backups;
- configure centralized logs, alerts, audit export, and incident response;
- run the security and abuse cases in `docs/test-plan.md`.

## Supported status

This repository is an internal proof of concept. No production security support window is currently declared.
