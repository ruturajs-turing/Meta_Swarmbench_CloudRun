import pytest
from fastapi import HTTPException

from app.toml_validator import validate_task_toml


VALID_TASK_TOML = """version = 1

[run]
name = "local-smoke-task"
command = "python eval.py"
working_dir = "/run/task"
timeout_seconds = 120
result_file = "results/summary.json"

[resources]
profile = "small"
cpu = 2
memory_gb = 4
disk_gb = 20
gpu = "none"

[image]
registry = "local"
repository = "python"
tag = "3.12-slim"
digest = "sha256:local-dev-placeholder"

[inputs]
include = ["task.toml", "eval.py"]
exclude = [".git/**", "__pycache__/**"]
max_upload_mb = 32

[outputs]
include = ["results/**", "artifacts/**"]
max_output_mb = 64

[env]
PYTHONUNBUFFERED = "1"

[secrets]

[network]
egress = "allowlist"
allow = ["pypi.org"]

[limits]
max_cost_usd = 1.00
max_retries = 1
"""


def test_local_smoke_task_validates():
    normalized = validate_task_toml(VALID_TASK_TOML, max_runtime_seconds=7200)

    assert normalized.task_name == "local-smoke-task"
    assert normalized.spec["resources"]["profile"] == "small"
    assert normalized.spec["run"]["working_dir"] == "/run/task"


def test_rejects_unpinned_image_digest():
    task_toml = VALID_TASK_TOML.replace("sha256:local-dev-placeholder", "latest")

    with pytest.raises(HTTPException) as exc:
        validate_task_toml(task_toml, max_runtime_seconds=7200)

    assert exc.value.status_code == 400
    assert "Image digest" in exc.value.detail


def test_swarmbench_harbor_task_validates():
    task_toml = """[task]
name = "swarmbench/abc123-SWARMBENCH-HIERARCHICAL-CREATIVEVIZ-DEMO"
description = "Demo SwarmBench task."

[metadata]
verifier_type = "executable"
coordination_pattern = "hierarchical"
dag_depth = 3
dag_width = 20
network_enabled = false

[agent]
timeout_sec = 7200

[verifier]
timeout_sec = 1800
requires_network = true

[environment]
cpus = 6
memory_mb = 8192
build_timeout_sec = 1200
"""

    normalized = validate_task_toml(task_toml, max_runtime_seconds=7200)

    assert normalized.task_name == "swarmbench/abc123-SWARMBENCH-HIERARCHICAL-CREATIVEVIZ-DEMO"
    assert normalized.spec["_aegisrun"]["task_type"] == "swarmbench-harbor"
    assert normalized.spec["resources"]["cpu"] == 6
    assert normalized.spec["resources"]["memory_gb"] == 8
    assert normalized.spec["resources"]["profile"] == "large"
    assert normalized.spec["_aegisrun"]["resource_source"]["section"] == "environment"
    assert normalized.spec["network"]["egress"] == "allowlist"
    assert "swarm-opencode-single" in normalized.spec["_aegisrun"]["harbor_commands"]["single"]
    assert "fireworks_ai/accounts/fireworks/models/kimi-k2p6" in normalized.spec["_aegisrun"]["harbor_commands"]["multi"]


def test_swarmbench_resources_are_read_exactly_from_environment():
    task_toml = """[task]
name = "swarmbench/abc123-SWARMBENCH-HIERARCHICAL-RESOURCE-DEMO"

[metadata]
verifier_type = "executable"
coordination_pattern = "hierarchical"
dag_depth = 2
dag_width = 20
network_enabled = true

[agent]
timeout_sec = 5400

[verifier]
timeout_sec = 1200

[environment]
cpus = 15
memory_mb = 24576
storage_mb = 65536
"""

    normalized = validate_task_toml(task_toml, max_runtime_seconds=7200)
    resources = normalized.spec["resources"]

    assert resources == {
        "profile": "xlarge",
        "cpu": 15,
        "memory_gb": 24,
        "disk_gb": 64,
        "gpu": "none",
    }
    assert normalized.spec["run"]["timeout_seconds"] == 5400
    assert normalized.spec["_aegisrun"]["resource_source"] == {
        "format": "swarmbench",
        "section": "environment",
        "cpu_field": "cpus",
        "memory_field": "memory_mb",
        "disk_field": "storage_mb",
    }


def test_swarmbench_resources_above_child_limit_are_rejected():
    task_toml = """[task]
name = "swarmbench/abc123-SWARMBENCH-HIERARCHICAL-RESOURCE-DEMO"

[metadata]
verifier_type = "executable"
coordination_pattern = "hierarchical"
dag_depth = 2
dag_width = 20

[environment]
cpus = 17
memory_mb = 8192
"""

    with pytest.raises(HTTPException) as exc:
        validate_task_toml(task_toml, max_runtime_seconds=7200)

    assert "16 CPU / 32 GB" in exc.value.detail
