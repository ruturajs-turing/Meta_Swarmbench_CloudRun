import asyncio
import json
import os
from pathlib import Path

import asyncssh
import httpx


API_URL = os.environ.get("AEGISRUN_API_URL", "http://api:8000").rstrip("/")
STORAGE_ROOT = Path(os.environ.get("AEGISRUN_GATEWAY_STORAGE", "/data"))
SSH_PORT = int(os.environ.get("AEGISRUN_SSH_PORT", "8022"))
TERMINAL_STATES = {"SUCCEEDED", "FAILED", "TIMED_OUT", "CANCELLED", "INFRA_FAILED"}
AUTH_BY_USERNAME: dict[str, dict] = {}


class GatewayServer(asyncssh.SSHServer):
    def begin_auth(self, username):
        return True

    def password_auth_supported(self):
        return True

    async def validate_password(self, username, password):
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{API_URL}/v1/sessions",
                json={"identifier": username, "password": password},
            )
        if response.status_code != 200:
            return False
        payload = response.json()
        if payload["user"]["role"] not in {"trainer", "reviewer"}:
            return False
        AUTH_BY_USERNAME[username] = payload
        return True


class WorkspaceSFTPServer(asyncssh.SFTPServer):
    def __init__(self, channel):
        username = channel.get_extra_info("username")
        auth = AUTH_BY_USERNAME.get(username)
        if not auth:
            raise asyncssh.PermissionDenied("Authentication context is missing")
        root = STORAGE_ROOT / "workspaces" / auth["user"]["id"]
        for name in ("incoming", "tasks", "runs", "downloads", "tmp"):
            (root / name).mkdir(parents=True, exist_ok=True)
        super().__init__(channel, chroot=str(root))


async def api(auth: dict, method: str, path: str, body: dict | None = None):
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.request(
            method,
            f"{API_URL}{path}",
            headers={"Authorization": f"Bearer {auth['token']}"},
            json=body,
        )
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except json.JSONDecodeError:
            detail = response.text
        raise RuntimeError(f"{response.status_code}: {detail}")
    return response.json() if response.content else {}


def clear(process):
    process.stdout.write("\x1b[2J\x1b[H")


def duration(value):
    if value is None:
        return "-"
    minutes, seconds = divmod(int(value), 60)
    return f"{minutes}m {seconds:02d}s" if minutes else f"{seconds}s"


async def read_choice(process, prompt="Select: "):
    process.stdout.write(prompt)
    value = await process.stdin.readline()
    return value.strip()


async def render_home(process, auth):
    workspace = await api(auth, "GET", "/v1/workspace")
    runtime = await api(auth, "GET", "/v1/runtime")
    parent = workspace["parent"]
    quota = workspace["quota"]
    clear(process)
    process.stdout.write("+--------------------------------------------------------------------+\n")
    process.stdout.write("| AEGISRUN  Managed trainer terminal                                 |\n")
    process.stdout.write("+--------------------------------------------------------------------+\n")
    process.stdout.write(f"  {auth['user']['display_name']}  @{auth['user']['username']}\n")
    process.stdout.write(
        f"  Parent {parent['id']}  {parent['state']}  "
        f"{parent['cpu']} CPU / {parent['memory_mb']} MB\n"
    )
    process.stdout.write(
        f"  Runs {quota['active_runs']}/{quota['max_active_runs']} active  |  "
        f"Harbor {'ready' if runtime['modes']['harbor']['enabled'] else 'disabled'}\n\n"
    )
    return workspace, runtime


async def run_staged(process, auth, workspace, runtime):
    staged = workspace.get("staged_uploads", [])
    if not staged:
        process.stdout.write(
            "\nNo tasks are staged in this parent workspace.\n"
            "A raw SSH process cannot read a path from your computer. Exit and run\n"
            "`runnerctl connect` in this same terminal for the local-path workflow.\n"
        )
        await read_choice(process, "\nPress Enter to return...")
        return
    process.stdout.write("\nStaged task folders\n")
    for index, name in enumerate(staged, 1):
        process.stdout.write(f"  {index}. {name}\n")
    choice = await read_choice(process, "Select task: ")
    if not choice.isdigit() or not 1 <= int(choice) <= len(staged):
        process.stdout.write("Invalid selection.\n")
        await read_choice(process, "Press Enter to return...")
        return
    mode = "harbor"
    if not runtime["modes"]["harbor"]["enabled"]:
        process.stdout.write("Harbor is disabled; this endpoint can only run a structure check.\n")
        mode = "probe"
    elif (await read_choice(process, "Run [H]arbor model logs or [P]ackage check? [H]: ")).lower() == "p":
        mode = "probe"
    try:
        imported = await api(auth, "POST", "/v1/tasks/import-staged", {"relative_path": staged[int(choice) - 1]})
        run = await api(
            auth,
            "POST",
            "/v1/runs",
            {"task_bundle_id": imported["bundle"]["id"], "execution_mode": mode},
        )
    except RuntimeError as exc:
        process.stdout.write(f"\nCould not start run: {exc}\n")
        await read_choice(process, "Press Enter to return...")
        return
    process.stdout.write(
        f"\nRun {run['id']} queued with {run['cpu']} CPU / {run['memory_mb']} MB.\n"
    )
    await follow_run(process, auth, run["id"])


async def list_runs(process, auth, *, choose=False):
    rows = (await api(auth, "GET", "/v1/runs"))["runs"]
    process.stdout.write("\nRuns\n")
    if not rows:
        process.stdout.write("  No runs yet.\n")
        return None
    for index, row in enumerate(rows[:20], 1):
        result = "PASS" if row["passed"] else "FAIL" if row["passed"] is False else "-"
        process.stdout.write(
            f"  {index:>2}. {row['state']:<18} {result:<4} {duration(row['duration_seconds']):>7}  "
            f"{row['task_name'][:48]}\n"
        )
    if not choose:
        return None
    value = await read_choice(process, "\nSelect run: ")
    if value.isdigit() and 1 <= int(value) <= min(20, len(rows)):
        return rows[int(value) - 1]
    return None


async def follow_run(process, auth, run_id):
    seen = 0
    while True:
        events = (await api(auth, "GET", f"/v1/runs/{run_id}/events"))["events"]
        for event in events:
            if event["sequence_number"] <= seen:
                continue
            seen = event["sequence_number"]
            process.stdout.write(
                f"{event['sequence_number']:03d}  {event['type']:<24} {event.get('message') or ''}\n"
            )
        current = await api(auth, "GET", f"/v1/runs/{run_id}")
        if current["state"] in TERMINAL_STATES:
            process.stdout.write(
                f"\n{current['state']}  result={'PASS' if current['passed'] else 'FAIL'}  "
                f"elapsed={duration(current['duration_seconds'])}\n"
            )
            if current["artifact_count"]:
                process.stdout.write(f"Result is available in /downloads/{run_id}-result.tar.gz\n")
            await read_choice(process, "\nPress Enter to return...")
            return
        await asyncio.sleep(1)


async def inspect_run(process, auth):
    selected = await list_runs(process, auth, choose=True)
    if not selected:
        await read_choice(process, "Press Enter to return...")
        return
    current = await api(auth, "GET", f"/v1/runs/{selected['id']}")
    process.stdout.write(
        f"\n{current['task_name']}\n"
        f"Run       {current['id']}\n"
        f"State     {current['state']}\n"
        f"Parent    {current['parent_sandbox_id']}\n"
        f"Child     {current['container_id'] or '-'}\n"
        f"Resources {current['cpu']} CPU / {current['memory_mb']} MB / {current['disk_gb']} GB\n"
        f"Elapsed   {duration(current['duration_seconds'])}\n"
        f"Cleanup   {current['cleanup_state']}\n"
    )
    if current["state"] not in TERMINAL_STATES:
        choice = await read_choice(process, "\n[F]ollow or [S]top this run? [F]: ")
        if choice.lower() == "s":
            await api(auth, "POST", f"/v1/runs/{current['id']}/cancel")
            process.stdout.write("Cancellation requested.\n")
        else:
            await follow_run(process, auth, current["id"])
    else:
        process.stdout.write(
            f"\nDownload with SFTP from /downloads/{current['id']}-result.tar.gz\n"
        )
        await read_choice(process, "Press Enter to return...")


async def terminal_session(process):
    username = process.get_extra_info("username")
    auth = AUTH_BY_USERNAME.get(username)
    if not auth:
        process.stderr.write("Authentication context missing. Reconnect.\n")
        process.exit(1)
        return
    try:
        while True:
            workspace, runtime = await render_home(process, auth)
            process.stdout.write("1. Run a task already staged in this parent workspace\n")
            process.stdout.write("2. My runs\n")
            process.stdout.write("3. Inspect, stop, or download a result\n")
            process.stdout.write("4. Local-path connection help\n")
            process.stdout.write("0. Exit\n\n")
            choice = await read_choice(process)
            if choice == "1":
                await run_staged(process, auth, workspace, runtime)
            elif choice == "2":
                await list_runs(process, auth)
                await read_choice(process, "\nPress Enter to return...")
            elif choice == "3":
                await inspect_run(process, auth)
            elif choice == "4":
                process.stdout.write(
                    "\nUse the local companion from your current terminal:\n"
                    "  runnerctl connect --endpoint http://HOST:18080 "
                    f"--user {username}\n"
                    "It prompts for a local task path, uploads it, reads task.toml, starts the child,\n"
                    "streams logs, and downloads the result without opening another window.\n"
                )
                await read_choice(process, "\nPress Enter to return...")
            elif choice == "0":
                process.stdout.write("Session closed.\n")
                process.exit(0)
                return
    except (asyncssh.BreakReceived, asyncssh.TerminalSizeChanged):
        pass
    except Exception as exc:
        process.stderr.write(f"Terminal error: {exc}\n")
        process.exit(1)


async def main():
    await asyncssh.create_server(
        GatewayServer,
        "0.0.0.0",
        SSH_PORT,
        server_host_keys=[str(STORAGE_ROOT / "ssh_host_ed25519_key")],
        process_factory=terminal_session,
        sftp_factory=WorkspaceSFTPServer,
        encoding="utf-8",
    )
    print(f"AegisRun SSH gateway listening on {SSH_PORT}", flush=True)
    await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (OSError, asyncssh.Error) as exc:
        raise SystemExit(f"SSH gateway failed: {exc}") from exc
