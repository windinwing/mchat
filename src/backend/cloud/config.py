"""Cloud edition settings (Portal, studio memory, templates)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class CloudSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    studio_memory_enabled: bool = True
    studio_workspace_dir: str = "../../data/studio"
    studio_memory_bootstrap_max_chars: int = 8000
    studio_memory_daily_bootstrap_days: int = 2
    studio_memory_timezone: str = "UTC"

    @property
    def studio_workspace_path(self) -> Path:
        from cloud.utils.studio_paths import resolve_studio_workspace_root

        return resolve_studio_workspace_root(self.studio_workspace_dir)


cloud_settings = CloudSettings()
