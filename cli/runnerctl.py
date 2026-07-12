#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import getpass
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


TERMINAL_STATES = {"SUCCEEDED", "FAILED", "TIMED_OUT", "CANCELLED", "INFRA_FAILED"}
ACTIVE_STATES = {"QUEUED", "PROVISIONING", "STAGING_INPUTS", "RUNNING", "COLLECTING_OUTPUTS", "FINALIZING"}


def config_path() -> Path:
    root = Path(os.environ.get("AEGISRUN_HOME", Path.home() / ".aegisrun"))
    root.mkdir(parents=True, exist_ok=True)
    return root / "config.json"


def load_config() -> dict:
    path = config_path()
    return json.loads(path.read_text()) if path.exists() else {}


def save_config(config: dict) -> None:
    config_path().write_text(json.dumps(config, indent=2))


def api_request(method: str, path: str, *, body=None, endpoint=None, headers=None, raw=False):
    config = load_config()
    base = (endpoint or config.get("endpoint") or "http://localhost:18080").rstrip("/")
    request_headers = {"Accept": "application/json"}
    if config.get("token"):
        request_headers["Authorization"] = f"Bearer {config['token']}"
    if headers:
        request_headers.update(headers)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(base + path, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request) as response:
            payload = response.read()
            if raw:
                return payload
            return json.loads(payload.decode()) if payload else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        try:
            message = json.loads(detail).get("detail", detail)
        except json.JSONDecodeError:
            message = detail
        raise SystemExit(f"API {exc.code}: {message}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Cannot reach AegisRun: {exc.reason}") from exc


def login(args):
    password = args.password or getpass.getpass("Password: ")
    result = authenticate(args.endpoint, args.user, password)
    parent = result.get("parent")
    suffix = f"; parent {parent['state'].lower()}" if parent else ""
    print(f"Connected as {result['user']['username']}{suffix}.")


def authenticate(endpoint: str, user: str, password: str) -> dict:
    result = api_request(
        "POST",
        "/v1/sessions",
        endpoint=endpoint,
        body={"identifier": user, "password": password},
    )
    save_config(
        {
            "endpoint": endpoint.rstrip("/"),
            "token": result["token"],
            "expires_at": result["expires_at"],
            "user": result["user"],
        }
    )
    return result


def whoami(_args):
    print(json.dumps(api_request("GET", "/v1/me"), indent=2))


def workspace(_args):
    print(json.dumps(api_request("GET", "/v1/workspace"), indent=2))


def runtime(_args):
    print(json.dumps(api_request("GET", "/v1/runtime"), indent=2))


def terminal(_args):
    info = api_request("GET", "/v1/terminal")
    print(f"SSH : {info['ssh_command']}")
    print(f"SFTP: {info['sftp_command']}")
    print("Local-path workflow: runnerctl connect")
    print(f"Raw SSH can run folders already staged in {info['upload_target']}.")


def connect(args):
    config = load_config()
    endpoint = (args.endpoint or config.get("endpoint") or "http://localhost:18080").rstrip("/")
    user = args.user or config.get("user", {}).get("username")
    configured_endpoint = str(config.get("endpoint", "")).rstrip("/")
    configured_user = config.get("user", {}).get("username")
    needs_login = (
        args.reauth
        or not config.get("token")
        or configured_endpoint != endpoint
        or (args.user is not None and configured_user != args.user)
    )
    if needs_login:
        user = user or input("Username: ").strip()
        if not user:
            raise SystemExit("Username is required.")
        password = args.password or getpass.getpass("Password: ")
        result = authenticate(endpoint, user, password)
        print(f"Connected as {result['user']['username']}.")
    if args.ssh:
        info = api_request("GET", "/v1/terminal")
        subprocess.run(
            ["ssh", "-p", str(info["ssh_port"]), f"{load_config()['user']['username']}@{info['ssh_host']}"],
            check=False,
        )
        return
    tui(args)


def make_bundle(task_dir: Path) -> Path:
    if not task_dir.is_dir():
        raise SystemExit(f"Task folder does not exist: {task_dir}")
    if not (task_dir / "task.toml").exists():
        raise SystemExit(f"Task folder must contain task.toml: {task_dir}")
    tmp = Path(tempfile.mkdtemp(prefix="aegisrun-bundle-"))
    archive = tmp / f"{task_dir.name}.tar.gz"
    excluded_dirs = {".git", "__pycache__", "node_modules", "execution_logs"}
    excludes = ["*.pyc", ".DS_Store", "execution_logs_*", "execution_logs_*/**"]
    with tarfile.open(archive, "w:gz") as tar:
        for item in task_dir.rglob("*"):
            relative = item.relative_to(task_dir)
            if any(part in excluded_dirs or part.startswith("execution_logs_") for part in relative.parts):
                continue
            if any(fnmatch.fnmatch(str(relative), pattern) for pattern in excludes):
                continue
            tar.add(item, arcname=relative)
    return archive


def multipart_request(path: Path, route: str, *, fields: dict[str, str] | None = None) -> dict:
    config = load_config()
    if not config.get("token"):
        raise SystemExit("Run runnerctl login first.")
    boundary = "----aegisrun" + next(tempfile._get_candidate_names())
    content_type = mimetypes.guess_type(path.name)[0] or "application/gzip"
    field_parts = []
    for name, value in (fields or {}).items():
        field_parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode()
        )
    file_header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode()
    closing = f"\r\n--{boundary}--\r\n".encode()
    file_size = path.stat().st_size
    total = sum(len(part) for part in field_parts) + len(file_header) + file_size + len(closing)

    def body_chunks():
        for part in field_parts:
            yield part
        yield file_header
        sent = 0
        next_report = 10
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                sent += len(chunk)
                if sys.stderr.isatty() and file_size:
                    percent = int(sent * 100 / file_size)
                    if percent >= next_report and percent < 100:
                        print(f"\rUploading {path.name}: {percent:>3}%", end="", file=sys.stderr, flush=True)
                        next_report = min(100, percent + 10)
                yield chunk
        if sys.stderr.isatty():
            print(f"\rUploading {path.name}: 100%", file=sys.stderr)
        yield closing

    request = urllib.request.Request(
        config["endpoint"] + route,
        data=body_chunks(),
        headers={
            "Authorization": f"Bearer {config['token']}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(total),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise SystemExit(f"Upload failed ({exc.code}): {detail}") from exc


def multipart_upload(path: Path) -> dict:
    return multipart_request(path, "/v1/tasks/upload")


def multipart_submit(path: Path, execution_mode: str) -> dict:
    return multipart_request(
        path,
        "/v1/tasks/submit",
        fields={"execution_mode": execution_mode},
    )


def push(args):
    archive = make_bundle(Path(args.path).expanduser().resolve())
    try:
        result = multipart_upload(archive)
    finally:
        shutil.rmtree(archive.parent, ignore_errors=True)
    bundle = result["bundle"]
    print(f"Task ready: {bundle['task_name']}")
    print(f"Bundle: {bundle['id']}  Size: {format_bytes(bundle['size_bytes'])}")
    if getattr(args, "json", False):
        print(json.dumps(result, indent=2))
    return bundle


def tasks(_args):
    rows = api_request("GET", "/v1/tasks")["bundles"]
    if not rows:
        print("No uploaded tasks.")
        return
    for row in rows:
        print(f"{row['id']}  {row['state']:<8}  {row['task_name']}  {format_bytes(row['size_bytes'])}")


def run(args):
    if args.mode == "harbor":
        runtime_info = api_request("GET", "/v1/runtime")
        if not runtime_info["modes"]["harbor"]["enabled"]:
            raise SystemExit("Harbor model-log execution is disabled by the operator.")
    bundle_id = args.bundle
    if args.path:
        task_path = Path(args.path).expanduser().resolve()
        print(f"Preparing task: {task_path}")
        archive = make_bundle(task_path)
        try:
            submitted = multipart_submit(archive, args.mode)
        finally:
            shutil.rmtree(archive.parent, ignore_errors=True)
        result = submitted["run"]
        resolved = submitted["resource_resolution"]
        print(f"Task accepted: {result['task_name']}")
        print(
            f"TOML [{resolved['section']}]: {resolved['cpu']} CPU / "
            f"{resolved['memory_mb']} MB / {resolved['disk_gb']} GB / "
            f"timeout {resolved['timeout_seconds']}s"
        )
        print(f"Run queued: {result['id']}  parent={result['parent_sandbox_id']}")
        if args.follow:
            return follow_logs(argparse.Namespace(run_id=result["id"]))
        return result
    if not bundle_id:
        raise SystemExit("Provide a task folder or --bundle.")
    result = api_request(
        "POST",
        "/v1/runs",
        body={"task_bundle_id": bundle_id, "execution_mode": args.mode},
    )
    print(f"Run queued: {result['id']}")
    print(f"Child spec: {result['cpu']} CPU / {result['memory_mb']} MB / {result['disk_gb']} GB")
    if args.follow:
        return follow_logs(argparse.Namespace(run_id=result["id"]))
    return result


def runs(_args):
    rows = api_request("GET", "/v1/runs")["runs"]
    if not rows:
        print("No runs yet.")
        return
    for row in rows:
        passed = "PASS" if row["passed"] else "FAIL" if row["passed"] is False else "-"
        print(f"{row['id']}  {row['state']:<18} {passed:<4} {format_duration(row['duration_seconds']):>7}  {row['task_name']}")


def status(args):
    print(json.dumps(api_request("GET", f"/v1/runs/{args.run_id}"), indent=2))


def logs(args):
    if args.follow:
        follow_logs(args)
        return
    for item in api_request("GET", f"/v1/runs/{args.run_id}/logs")["logs"]:
        print(item["line"])


def follow_logs(args):
    seen = 0
    while True:
        for event in api_request("GET", f"/v1/runs/{args.run_id}/events")["events"]:
            if event["sequence_number"] <= seen:
                continue
            seen = event["sequence_number"]
            print(f"{event['sequence_number']:03d}  {event['type']:<24} {event.get('message') or ''}")
        current = api_request("GET", f"/v1/runs/{args.run_id}")
        if current["state"] in TERMINAL_STATES:
            result_label = "PASS" if current["passed"] is True else "FAIL" if current["passed"] is False else "-"
            print(f"\n{current['state']}  result={result_label}  elapsed={format_duration(current['duration_seconds'])}")
            if current["artifact_count"]:
                print(f"Download: runnerctl download {current['id']}")
            return current
        time.sleep(1)


def artifacts(args):
    print(json.dumps(api_request("GET", f"/v1/runs/{args.run_id}/artifacts"), indent=2))


def download(args):
    rows = api_request("GET", f"/v1/runs/{args.run_id}/artifacts")["artifacts"]
    if not rows:
        raise SystemExit("This run has no result package yet.")
    artifact = rows[0]
    data = api_request("GET", artifact["download_url"], raw=True)
    output = Path(args.output or artifact["path"]).expanduser().resolve()
    if output.exists() and output.is_dir():
        output = output / artifact["path"]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    print(f"Downloaded {format_bytes(len(data))} to {output}")
    return output


def install_outputs(args):
    task_path = Path(args.task_path).expanduser().resolve()
    if not task_path.is_dir() or not (task_path / "task.toml").exists():
        raise SystemExit(f"Target must be a task folder containing task.toml: {task_path}")
    archive = download(argparse.Namespace(run_id=args.run_id, output=str(task_path)))
    temp_root = Path(tempfile.mkdtemp(prefix="aegisrun-result-"))
    allowed_roots = {"execution_logs", "logs", "results", "artifacts"}
    try:
        with tarfile.open(archive, "r:gz") as tar:
            for member in tar.getmembers():
                parts = Path(member.name).parts
                if not parts or parts[0] not in allowed_roots:
                    raise SystemExit(f"Result package contains an unexpected path: {member.name}")
                if member.issym() or member.islnk():
                    raise SystemExit(f"Result package contains a link: {member.name}")
                if not (member.isfile() or member.isdir()):
                    raise SystemExit(f"Result package contains an unsupported entry: {member.name}")
                target = (temp_root / member.name).resolve()
                try:
                    target.relative_to(temp_root.resolve())
                except ValueError:
                    raise SystemExit(f"Result package contains an unsafe path: {member.name}")
            tar.extractall(temp_root)
        installed = []
        for name in sorted(allowed_roots):
            source = temp_root / name
            if not source.exists():
                continue
            target = task_path / name
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
            shutil.copytree(source, target)
            installed.append(name)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
    print(f"Installed run outputs into {task_path}: {', '.join(installed) or 'none'}")
    return archive


def stop(args):
    api_request("POST", f"/v1/runs/{args.run_id}/cancel")
    print(f"Cancellation requested for {args.run_id}.")


def retry(args):
    result = api_request("POST", f"/v1/runs/{args.run_id}/retry")
    print(f"Retry queued: {result['id']}")


def format_duration(value) -> str:
    if value is None:
        return "-"
    minutes, seconds = divmod(int(value), 60)
    return f"{minutes}m {seconds:02d}s" if minutes else f"{seconds}s"


def format_bytes(value) -> str:
    size = float(value or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} GB"


def clear_screen():
    if sys.stdout.isatty():
        os.system("clear")


def pause():
    if sys.stdin.isatty():
        input("\nPress Enter to return...")


def choose_run() -> dict | None:
    rows = api_request("GET", "/v1/runs")["runs"][:20]
    if not rows:
        print("No runs yet.")
        return None
    for index, row in enumerate(rows, 1):
        print(f"{index:>2}. {row['state']:<18} {row['task_name'][:54]}")
    value = input("\nSelect run: ").strip()
    if not value.isdigit() or not 1 <= int(value) <= len(rows):
        print("Invalid selection.")
        return None
    return rows[int(value) - 1]


def print_header(workspace_data: dict):
    config = load_config()
    parent = workspace_data["parent"]
    quota = workspace_data["quota"]
    runtime_info = api_request("GET", "/v1/runtime")
    print("+--------------------------------------------------------------------+")
    print("| AEGISRUN  Trainer workspace                                        |")
    print("+--------------------------------------------------------------------+")
    print(f"  {config['user']['display_name']}  @{config['user']['username']}")
    print(f"  Parent {parent['id']}  {parent['state']}  {parent['cpu']} CPU / {parent['memory_mb']} MB")
    print(f"  Runs {quota['active_runs']}/{quota['max_active_runs']} active  |  Harbor {'ready' if runtime_info['modes']['harbor']['enabled'] else 'disabled'}")


def inspect_result_menu():
    selected = choose_run()
    if not selected:
        return
    while True:
        current = api_request("GET", f"/v1/runs/{selected['id']}")
        print(f"\n{current['task_name']}\n{current['id']}  {current['state']}  {format_duration(current['duration_seconds'])}")
        print("1. Follow events" if current["state"] in ACTIVE_STATES else "1. View event log")
        print("2. Download result package")
        print("3. Stop run" if current["state"] in ACTIVE_STATES else "3. Retry run")
        print("0. Back")
        choice = input("Select: ").strip()
        if choice == "1":
            follow_logs(argparse.Namespace(run_id=current["id"])) if current["state"] in ACTIVE_STATES else logs(argparse.Namespace(run_id=current["id"], follow=False))
        elif choice == "2":
            output = input("Download path [current folder]: ").strip() or None
            download(argparse.Namespace(run_id=current["id"], output=output))
        elif choice == "3":
            if current["state"] in ACTIVE_STATES:
                stop(argparse.Namespace(run_id=current["id"]))
            else:
                retry(argparse.Namespace(run_id=current["id"]))
        elif choice == "0":
            return
        else:
            print("Invalid selection.")


def tui(args):
    if not load_config().get("token"):
        raise SystemExit("Run runnerctl connect to sign in.")
    execution_mode = getattr(args, "mode", "harbor")
    while True:
        clear_screen()
        data = api_request("GET", "/v1/workspace")
        print_header(data)
        print("\n1. Start a task from this computer")
        print("2. My runs")
        print("3. Inspect, stop, retry, or download")
        print("4. Workspace status")
        print("0. Exit")
        choice = input("\nSelect: ").strip()
        try:
            if choice == "1":
                path = input("Task folder path: ").strip()
                if not path:
                    raise SystemExit("Task folder path is required.")
                task_path = Path(path).expanduser().resolve()
                current = run(argparse.Namespace(path=str(task_path), bundle=None, mode=execution_mode, follow=True))
                if current and current.get("artifact_count"):
                    print("\n1. Install run outputs into this task folder")
                    print("2. Download the result archive only")
                    print("3. Leave it in the parent workspace")
                    answer = input("Select [1]: ").strip() or "1"
                    if answer == "1":
                        install_outputs(argparse.Namespace(run_id=current["id"], task_path=str(task_path)))
                    elif answer == "2":
                        download(argparse.Namespace(run_id=current["id"], output=str(task_path)))
                pause()
            elif choice == "2":
                runs(argparse.Namespace())
                pause()
            elif choice == "3":
                inspect_result_menu()
                pause()
            elif choice == "4":
                print(json.dumps(data, indent=2))
                print()
                terminal(argparse.Namespace())
                pause()
            elif choice == "0":
                return
            else:
                print("Invalid selection.")
                pause()
        except (KeyboardInterrupt, SystemExit) as exc:
            print(f"\n{exc or 'Interrupted.'}")
            pause()


def main():
    parser = argparse.ArgumentParser(prog="runnerctl", description="AegisRun trainer terminal")
    sub = parser.add_subparsers(dest="command", required=True)

    command = sub.add_parser("login")
    command.add_argument("--endpoint", default="http://localhost:18080")
    command.add_argument("--user", required=True, help="AegisRun username or email")
    command.add_argument("--password")
    command.set_defaults(func=login)

    sub.add_parser("whoami").set_defaults(func=whoami)
    sub.add_parser("workspace").set_defaults(func=workspace)
    sub.add_parser("runtime").set_defaults(func=runtime)
    sub.add_parser("terminal").set_defaults(func=terminal)
    command = sub.add_parser("connect", help="Sign in and open the single-window trainer interface")
    command.add_argument("--endpoint")
    command.add_argument("--user")
    command.add_argument("--password")
    command.add_argument("--reauth", action="store_true")
    command.add_argument("--mode", choices=["harbor", "probe"], default="harbor", help=argparse.SUPPRESS)
    command.add_argument("--ssh", action="store_true", help="Open the raw SSH staged-task interface")
    command.set_defaults(func=connect)
    sub.add_parser("tasks").set_defaults(func=tasks)

    command = sub.add_parser("push")
    command.add_argument("path")
    command.add_argument("--json", action="store_true")
    command.set_defaults(func=push)

    command = sub.add_parser("run")
    command.add_argument("path", nargs="?")
    command.add_argument("--bundle")
    command.add_argument("--mode", choices=["probe", "harbor"], default="harbor")
    command.add_argument("--follow", "--tail", action="store_true")
    command.set_defaults(func=run)

    sub.add_parser("runs").set_defaults(func=runs)
    command = sub.add_parser("status")
    command.add_argument("run_id")
    command.set_defaults(func=status)
    command = sub.add_parser("logs")
    command.add_argument("run_id")
    command.add_argument("--follow", action="store_true")
    command.set_defaults(func=logs)
    command = sub.add_parser("artifacts")
    command.add_argument("run_id")
    command.set_defaults(func=artifacts)
    command = sub.add_parser("download")
    command.add_argument("run_id")
    command.add_argument("-o", "--output")
    command.set_defaults(func=download)
    command = sub.add_parser("install", help="Download and install run outputs into a task folder")
    command.add_argument("run_id")
    command.add_argument("task_path")
    command.set_defaults(func=install_outputs)
    command = sub.add_parser("stop")
    command.add_argument("run_id")
    command.set_defaults(func=stop)
    command = sub.add_parser("retry")
    command.add_argument("run_id")
    command.set_defaults(func=retry)
    command = sub.add_parser("tui")
    command.add_argument("--mode", choices=["harbor", "probe"], default="harbor", help=argparse.SUPPRESS)
    command.set_defaults(func=tui)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
