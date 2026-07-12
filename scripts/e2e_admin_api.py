#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


ENDPOINT = os.environ.get("AEGISRUN_ENDPOINT", "http://localhost:18080").rstrip("/")
TOKEN = ""


def login(identifier: str, password: str) -> dict:
    payload = json.dumps({"identifier": identifier, "password": password}).encode()
    req = urllib.request.Request(
        ENDPOINT + "/v1/sessions",
        data=payload,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"Login failed ({exc.code}): {detail}") from exc


def request(method: str, path: str, body: dict | None = None) -> dict:
    payload = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(ENDPOINT + path, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            raw = response.read()
            return json.loads(raw.decode()) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"{method} {path} failed ({exc.code}): {detail}") from exc


def main() -> None:
    global TOKEN
    admin_identifier = os.environ.get("AEGISRUN_ADMIN_USER", "admin")
    admin_password = os.environ.get("AEGISRUN_ADMIN_PASSWORD", "aegisrun")
    trainer_identifier = os.environ.get("AEGISRUN_TRAINER_USER", "trainer")
    trainer_password = os.environ.get("AEGISRUN_TRAINER_PASSWORD", "trainer123")

    TOKEN = login(admin_identifier, admin_password)["token"]
    login(trainer_identifier, trainer_password)

    overview = request("GET", "/admin/overview")
    users = request("GET", "/admin/users")["users"]
    trainer = next(user for user in users if user["username"] == "trainer")
    parent_id = trainer["parent_id"]
    assert parent_id, "Seeded trainer parent was not provisioned"

    paused = request("POST", f"/admin/parents/{parent_id}/pause")
    assert paused["state"] == "PAUSED"
    resumed = request("POST", f"/admin/parents/{parent_id}/resume")
    assert resumed["state"] == "RUNNING"
    old_container = resumed["container_id"]
    refreshed = request("POST", f"/admin/parents/{parent_id}/refresh")
    assert refreshed["state"] == "RUNNING"
    assert refreshed["container_id"] != old_container

    existing = next((user for user in users if user["username"] == "ops-smoke"), None)
    if existing:
        smoke_user = existing
    else:
        smoke_user = request(
            "POST",
            "/admin/users",
            {
                "username": "ops-smoke",
                "email": "ops-smoke@aegisrun.local",
                "display_name": "Operations Smoke Test",
                "password": "smoke-test-123",
                "role": "trainer",
            },
        )
    quota = request(
        "PATCH",
        f"/admin/users/{smoke_user['id']}/quota",
        {"max_active_runs": 3, "parent_cpu": 4, "parent_memory_mb": 8192, "parent_disk_gb": 40},
    )
    assert quota["max_active_runs"] == 3
    assert quota["parent_cpu"] == 4
    request("POST", f"/admin/users/{smoke_user['id']}/reset-password", {"password": "smoke-reset-123"})
    request("PATCH", f"/admin/users/{smoke_user['id']}", {"state": "disabled"})

    runs = request("GET", "/admin/runs")["runs"]
    providers = request("GET", "/admin/providers")
    audit = request("GET", "/admin/audit")["events"]
    costs = request("GET", "/admin/costs")
    result = {
        "overview_users": overview["counts"]["users"],
        "trainer_parent": parent_id,
        "parent_container_replaced": refreshed["container_id"] != old_container,
        "runs_visible": len(runs),
        "docker_connected": providers["runtime"]["docker"],
        "audit_events": len(audit),
        "recorded_run_cost": costs["run_cost"],
        "user_create_update_reset": "passed",
        "parent_pause_resume_refresh": "passed",
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
