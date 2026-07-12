import tomllib
from dataclasses import dataclass
from math import ceil

from fastapi import HTTPException


RESOURCE_LIMITS = {
    "small": {"cpu": 2, "memory_gb": 4, "disk_gb": 20},
    "medium": {"cpu": 4, "memory_gb": 8, "disk_gb": 40},
    "large": {"cpu": 8, "memory_gb": 16, "disk_gb": 80},
    "xlarge": {"cpu": 16, "memory_gb": 32, "disk_gb": 160},
}


@dataclass(frozen=True)
class NormalizedTask:
    task_name: str
    spec: dict


def validate_task_toml(task_toml: str, max_runtime_seconds: int) -> NormalizedTask:
    try:
        spec = tomllib.loads(task_toml)
    except tomllib.TOMLDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid TOML: {exc}") from exc

    if "task" in spec and "metadata" in spec and "environment" in spec:
        return _validate_swarmbench_toml(spec, max_runtime_seconds)

    required_sections = ["run", "resources", "image", "inputs", "outputs", "network", "limits"]
    for section in required_sections:
        if section not in spec or not isinstance(spec[section], dict):
            raise HTTPException(status_code=400, detail=f"Missing [{section}] section")

    run = spec["run"]
    for field in ["name", "command", "working_dir", "timeout_seconds", "result_file"]:
        if field not in run:
            raise HTTPException(status_code=400, detail=f"Missing [run].{field}")
    if not str(run["working_dir"]).startswith("/run/task"):
        raise HTTPException(status_code=400, detail="[run].working_dir must start with /run/task")
    if int(run["timeout_seconds"]) > max_runtime_seconds:
        raise HTTPException(status_code=400, detail="Run timeout exceeds quota")

    resources = spec["resources"]
    profile = resources.get("profile")
    if profile not in RESOURCE_LIMITS:
        raise HTTPException(status_code=400, detail=f"Unsupported resource profile: {profile}")
    limits = RESOURCE_LIMITS[profile]
    if int(resources.get("cpu", 0)) > limits["cpu"]:
        raise HTTPException(status_code=400, detail="Requested CPU exceeds profile limit")
    if int(resources.get("memory_gb", 0)) > limits["memory_gb"]:
        raise HTTPException(status_code=400, detail="Requested memory exceeds profile limit")
    if int(resources.get("disk_gb", 0)) > limits["disk_gb"]:
        raise HTTPException(status_code=400, detail="Requested disk exceeds profile limit")

    image = spec["image"]
    if not str(image.get("digest", "")).startswith("sha256:"):
        raise HTTPException(status_code=400, detail="Image digest must be pinned with sha256:")

    secrets = spec.get("secrets", {})
    for key, value in secrets.items():
        if not str(value).startswith("vault://"):
            raise HTTPException(status_code=400, detail=f"Secret {key} must be a vault:// reference")

    outputs = spec["outputs"]
    if not outputs.get("include"):
        raise HTTPException(status_code=400, detail="[outputs].include must not be empty")

    spec["version"] = int(spec.get("version", 1))
    spec.setdefault("_aegisrun", {})["resource_source"] = {
        "format": "aegisrun",
        "section": "resources",
        "cpu_field": "cpu",
        "memory_field": "memory_gb",
        "disk_field": "disk_gb",
    }
    return NormalizedTask(task_name=str(run["name"]), spec=spec)


def _validate_swarmbench_toml(spec: dict, max_runtime_seconds: int) -> NormalizedTask:
    task = spec["task"]
    metadata = spec["metadata"]
    environment = spec["environment"]
    agent = spec.get("agent", {})
    verifier = spec.get("verifier", {})
    name = str(task.get("name", ""))
    if not name.startswith("swarmbench/"):
        raise HTTPException(status_code=400, detail="[task].name must start with swarmbench/")
    for field in ["verifier_type", "coordination_pattern", "dag_depth", "dag_width"]:
        if field not in metadata:
            raise HTTPException(status_code=400, detail=f"Missing [metadata].{field}")
    cpus = int(environment.get("cpus", 0))
    memory_mb = int(environment.get("memory_mb", 0))
    if cpus <= 0 or memory_mb <= 0:
        raise HTTPException(status_code=400, detail="[environment].cpus and memory_mb are required")
    timeout = int(agent.get("timeout_sec", 7200))
    if timeout > max_runtime_seconds:
        raise HTTPException(status_code=400, detail="Agent timeout exceeds quota")

    memory_gb = max(1, (memory_mb + 1023) // 1024)
    if cpus <= 2 and memory_gb <= 4:
        profile = "small"
    elif cpus <= 4 and memory_gb <= 8:
        profile = "medium"
    elif cpus <= 8 and memory_gb <= 16:
        profile = "large"
    elif cpus <= 16 and memory_gb <= 32:
        profile = "xlarge"
    else:
        raise HTTPException(status_code=400, detail="Requested resources exceed the 16 CPU / 32 GB child limit")

    storage_mb = int(environment.get("storage_mb", 20480))
    if storage_mb <= 0:
        raise HTTPException(status_code=400, detail="[environment].storage_mb must be positive")
    if ceil(storage_mb / 1024) > RESOURCE_LIMITS[profile]["disk_gb"]:
        raise HTTPException(status_code=400, detail=f"Requested disk exceeds {profile} profile limit")
    network_enabled = bool(metadata.get("network_enabled") or verifier.get("requires_network"))
    normalized = {
        "version": 1,
        "run": {
            "name": name,
            "command": "python .aegisrun_swarmbench_probe.py",
            "working_dir": "/run/task",
            "timeout_seconds": min(timeout, max_runtime_seconds),
            "result_file": "results/summary.json",
        },
        "resources": {
            "profile": profile,
            "cpu": cpus,
            "memory_gb": memory_gb,
            "disk_gb": max(1, ceil(storage_mb / 1024)),
            "gpu": "none",
        },
        "image": {
            "registry": "harbor-runtime",
            "repository": "swarmbench-runner",
            "tag": "template-managed",
            "digest": "sha256:template-managed",
        },
        "inputs": {"include": ["instruction.md", "task.toml", "decomposition.yaml", "environment/**", "tests/**"], "exclude": ["execution_logs/**", ".DS_Store"], "max_upload_mb": 2048},
        "outputs": {"include": ["execution_logs/**", "logs/**", "results/**", "artifacts/**"], "max_output_mb": 4096},
        "env": {"PYTHONUNBUFFERED": "1"},
        "secrets": {},
        "network": {
            "egress": "allowlist" if network_enabled else "deny",
            "allow": ["api.fireworks.ai", "api.stackexchange.com"] if network_enabled else [],
        },
        "limits": {"max_cost_usd": 25.0, "max_retries": 1},
        "_aegisrun": {
            "task_type": "swarmbench-harbor",
            "original_task_toml": spec,
            "resource_source": {
                "format": "swarmbench",
                "section": "environment",
                "cpu_field": "cpus",
                "memory_field": "memory_mb",
                "disk_field": "storage_mb" if "storage_mb" in environment else "platform_default",
            },
            "harbor_commands": {
                "oracle": "harbor run -p /workspace/task -a oracle --job-name oracle --jobs-dir /workspace/task/execution_logs --ve FIREWORKS_API_KEY=$FIREWORKS_API_KEY",
                "single": "harbor run -p /workspace/task -a swarm-opencode-single -m fireworks_ai/accounts/fireworks/models/kimi-k2p6 -k 1 -n 1 --job-name single-opencode-agent --jobs-dir /workspace/task/execution_logs --ve FIREWORKS_API_KEY=$FIREWORKS_API_KEY --ae FIREWORKS_API_KEY=$FIREWORKS_API_KEY --quiet",
                "multi": "harbor run -p /workspace/task -a swarm-opencode-multi -m fireworks_ai/accounts/fireworks/models/kimi-k2p6 -k 1 -n 1 --job-name multi-opencode-agent --jobs-dir /workspace/task/execution_logs --ve FIREWORKS_API_KEY=$FIREWORKS_API_KEY --ae FIREWORKS_API_KEY=$FIREWORKS_API_KEY --quiet",
            },
        },
    }
    return NormalizedTask(task_name=name, spec=normalized)
