from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./aegisrun.db"
    storage_root: str = "./storage"
    runner_image: str = "python:3.12-slim"
    harbor_runner_image: str = "aegisrun/harbor-runner:local"
    parent_image: str = "aegisrun/harbor-runner:local"
    parent_template_version: str = "harbor-opencode-2026.07.10"
    harbor_runtime_enabled: bool = False
    cors_origins: str = "http://localhost:5177,http://127.0.0.1:5177"
    run_cost_per_minute: float = 0.025
    parent_cost_per_hour: float = 0.08
    parent_idle_minutes: int = 15
    parent_refresh_hours: int = 24
    session_hours: int = 12
    ssh_public_host: str = "localhost"
    ssh_public_port: int = 2222


settings = Settings()
