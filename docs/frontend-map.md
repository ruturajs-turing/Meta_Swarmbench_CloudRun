# Frontend Map

The React app is an operator console only. Hash navigation keeps the local implementation dependency-light.

| Hash | Page | Main data | Mutations |
| --- | --- | --- | --- |
| `#overview` | Fleet Overview | `/admin/overview`, `/admin/costs` | none |
| `#parents` | Parent Workspaces | `/admin/parents`, `/admin/parents/{id}/stats` | create, pause, resume, refresh, destroy |
| `#runs` | Execution Runs | `/admin/runs`, `/v1/runs/{id}/events`, artifacts | cancel, retry, force cleanup, download |
| `#users` | Users and Access | `/admin/users` | create, patch, reset password, update quota, create parent |
| `#runtime` | Runtime and Access | `/admin/providers`, `/v1/terminal`, `/admin/costs` | reconcile |
| `#audit` | Operator Audit | `/admin/audit` | none |

Every inventory uses a filter toolbar, selectable table, and contextual inspector. Destructive actions require a modal confirmation. Polling intervals are 1.8 to 10 seconds based on volatility.
