from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderCapability:
    name: str
    parent_sandbox: bool
    execution_sandbox: bool
    ssh: bool
    pause_resume: bool
    max_cpu: int
    max_memory_gb: int
    status: str


PROVIDER_CAPABILITIES = {
    "local-docker": ProviderCapability(
        name="local-docker",
        parent_sandbox=True,
        execution_sandbox=True,
        ssh=False,
        pause_resume=False,
        max_cpu=8,
        max_memory_gb=16,
        status="implemented-for-dev",
    ),
    "e2b": ProviderCapability(
        name="e2b",
        parent_sandbox=True,
        execution_sandbox=True,
        ssh=True,
        pause_resume=True,
        max_cpu=8,
        max_memory_gb=16,
        status="adapter-contract-ready",
    ),
    "daytona": ProviderCapability(
        name="daytona",
        parent_sandbox=True,
        execution_sandbox=True,
        ssh=True,
        pause_resume=True,
        max_cpu=4,
        max_memory_gb=8,
        status="adapter-contract-ready",
    ),
}


class SandboxProvider:
    def create_parent_sandbox(self, spec: dict) -> dict:
        raise NotImplementedError

    def resume_parent_sandbox(self, parent_id: str) -> None:
        raise NotImplementedError

    def pause_parent_sandbox(self, parent_id: str) -> None:
        raise NotImplementedError

    def destroy_parent_sandbox(self, parent_id: str) -> None:
        raise NotImplementedError

    def create_execution_sandbox(self, run_spec: dict) -> dict:
        raise NotImplementedError

    def stream_logs(self, execution_id: str):
        raise NotImplementedError

    def kill_execution_sandbox(self, execution_id: str) -> None:
        raise NotImplementedError
